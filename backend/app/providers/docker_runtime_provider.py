"""Docker runtime — simulated (fake) and real Docker SDK backends."""

from __future__ import annotations

import ipaddress
import os
import re
from collections import defaultdict
from uuid import UUID

import docker
from docker.errors import APIError, ImageNotFound, NotFound

from app.models.deployment import DeploymentEventLevel
from app.providers.runtime_provider import ProviderEvent, RuntimeProvider
from app.providers.runtime_types import (
    ProviderExecResult,
    ProviderHealingResult,
    ProviderReconciliationResult,
    ProviderRuntimeSnapshot,
    ProviderRuntimeStats,
    RuntimeContainerRecord,
    RuntimeNetworkInterfaceRecord,
    RuntimeNetworkRecord,
)
from app.services.deployment_planner import DeploymentPlan


def topology_network_name(topology_id: UUID) -> str:
    short = str(topology_id).replace("-", "")[:12]
    return f"cns-topology-{short}"


# Applied at ``create_host_config`` for segment routers when the engine allows it;
# ``enable_router_forwarding`` still runs post-attach for runtime verification.
_SEGMENT_ROUTER_SYSCTLS: dict[str, str] = {
    "net.ipv4.ip_forward": "1",
    "net.ipv4.conf.all.rp_filter": "0",
    "net.ipv4.conf.default.rp_filter": "0",
}


def _segmented_sysctl_hostconfig_rejected(exc: APIError) -> bool:
    blob = f"{getattr(exc, 'explanation', None) or ''} {exc}".lower()
    return "sysctl" in blob


def _net_admin_or_policy_denied_hint(exc: APIError) -> bool:
    s = f"{getattr(exc, 'explanation', None) or ''} {exc}".lower()
    return any(
        k in s
        for k in (
            "cap_add",
            "capability",
            "operation not permitted",
            "permission denied",
            "denied",
            "privileged",
            "forbidden",
        )
    )


def segment_docker_network_name(topology_id: UUID, logical_network_name: str) -> str:
    """Deterministic Docker bridge name for a logical segment (<=63 chars)."""
    short = str(topology_id).replace("-", "")[:12]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", logical_network_name.strip().lower()).strip("-")[:22]
    slug = slug or "seg"
    base = f"cns-sg-{short}-{slug}"
    return base[:63]


def container_name(node_id: UUID, node_name: str) -> str:
    short_id = str(node_id).replace("-", "")[:12]
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "-", node_name).strip("-")[:40] or "node"
    return f"cns-node-{short_id}-{safe}"


def _base_labels(topology_id: UUID) -> dict[str, str]:
    return {
        "cns.project": "cloud-networking-studio",
        "cns.topology_id": str(topology_id),
        "cns.managed": "true",
    }


def _container_labels(
    topology_id: UUID, node_id: UUID, forwarding_role: str | None = None
) -> dict[str, str]:
    labels = _base_labels(topology_id)
    labels["cns.node_id"] = str(node_id)
    if forwarding_role:
        labels["cns.forwarding_role"] = forwarding_role
    return labels


def _default_command(image_ref: str) -> list[str] | None:
    img = image_ref.lower()
    if "nginx" in img:
        return None
    if "busybox" in img:
        return [
            "sh",
            "-c",
            "mkdir -p /www && printf 'ok\\n' >/www/index.html && exec httpd -f -p 80 -h /www",
        ]
    return ["sleep", "infinity"]


def _resolve_image(plan_node_image: str | None) -> str:
    return (plan_node_image or "").strip() or "alpine:latest"


def _default_bridge_network_name() -> str:
    """Docker's built-in bridge is always named ``bridge``."""
    return "bridge"


def _raw_ipv4_map_from_networks(nets: dict) -> dict[str, str]:
    """All non-empty IPv4 addresses keyed by Docker network attachment name."""
    out: dict[str, str] = {}
    for nname, nc in (nets or {}).items():
        if not isinstance(nc, dict):
            continue
        ip = (nc.get("IPAddress") or "").strip()
        if ip:
            out[str(nname)] = ip
    return out


def _labeled_topology_network_ids(
    client: docker.DockerClient, topology_id: UUID
) -> frozenset[str]:
    """Network IDs for bridge networks labeled as this topology."""
    try:
        nets = client.networks.list(filters=_topology_runtime_filters(topology_id))
    except APIError:
        return frozenset()
    ids: set[str] = set()
    for n in nets:
        nid = n.attrs.get("Id")
        if nid:
            ids.add(nid)
    return frozenset(ids)


def _pick_cns_ipv4(
    nets: dict,
    topology_id: UUID,
    labeled_net_ids: frozenset[str],
) -> str | None:
    """IPv4 on the CNS topology attachment — never the default ``bridge``-only IP."""
    preferred_key = topology_network_name(topology_id)
    pref_cfg = nets.get(preferred_key)
    if isinstance(pref_cfg, dict):
        ip = (pref_cfg.get("IPAddress") or "").strip()
        if ip:
            return ip

    for net_key, cfg in nets.items():
        if not isinstance(cfg, dict):
            continue
        if net_key == _default_bridge_network_name():
            continue
        nid = cfg.get("NetworkID")
        if nid and nid in labeled_net_ids:
            ip = (cfg.get("IPAddress") or "").strip()
            if ip:
                return ip
    return None


def _runtime_ipv4_display_map(
    nets: dict,
    topology_id: UUID,
    labeled_net_ids: frozenset[str],
) -> dict[str, str]:
    """Prefer CNS topology network keys for API/runtime views; omit stray bridge when possible."""
    raw = _raw_ipv4_map_from_networks(nets)
    pref = topology_network_name(topology_id)
    ordered: dict[str, str] = {}

    if pref in raw:
        ordered[pref] = raw[pref]

    for key, ip in raw.items():
        if key == pref or key == _default_bridge_network_name():
            continue
        cfg = nets.get(key)
        nid = (cfg or {}).get("NetworkID") if isinstance(cfg, dict) else None
        if nid and nid in labeled_net_ids:
            ordered[key] = ip

    if not ordered:
        # Misconfiguration: surface whatever we have (often only bridge).
        return dict(raw)
    return ordered


def _disconnect_default_bridge(
    client: docker.DockerClient, container_id: str
) -> None:
    """Detach from Docker's default bridge so containers are not dual-homed on 172.17.0.0/16."""
    try:
        bridge = client.networks.get(_default_bridge_network_name())
        bridge.disconnect(container_id, force=True)
    except NotFound:
        pass
    except APIError:
        pass


def _ipam_from_cidr(subnet_cidr: str | None):
    """Return docker.types.IPAMConfig or None."""
    if not subnet_cidr:
        return None
    try:
        from docker.types import IPAMConfig, IPAMPool

        net = ipaddress.ip_network(subnet_cidr.strip(), strict=False)
        gateway = str(net.network_address + 1)
        pool = IPAMPool(subnet=str(net.with_prefixlen), gateway=gateway)
        return IPAMConfig(driver="default", pool_configs=[pool])
    except (ValueError, TypeError):
        return None


def _ipam_from_cidr_and_gateway(subnet_cidr: str | None, gateway: str | None):
    """IPAM with explicit gateway (segmented networks)."""
    if not subnet_cidr:
        return None
    try:
        from docker.types import IPAMConfig, IPAMPool

        net = ipaddress.ip_network(subnet_cidr.strip(), strict=False)
        gw = (gateway or "").strip() or str(net.network_address + 1)
        pool = IPAMPool(subnet=str(net.with_prefixlen), gateway=gw)
        return IPAMConfig(driver="default", pool_configs=[pool])
    except (ValueError, TypeError):
        return None


def _pick_docker_bridge_gateway_ip(subnet_cidr: str, reserved_ipv4: set[str]) -> str | None:
    """
    IPv4 address for Docker IPAM ``gateway`` on a user-defined bridge.

    Docker binds this address to the **bridge** itself; it must not equal any
    static ``ipv4_address`` assigned to a container on the same network (otherwise
    ``create_container`` / ``connect`` fails with "Address already in use").

    We therefore pick a host address inside ``subnet_cidr`` that is **not** in
    ``reserved_ipv4`` (typically all link endpoint IPs on this segment). Prefer
    high addresses (e.g. ``.254``) so lab routers can keep ``.1`` as their NIC IP.
    """
    try:
        net = ipaddress.ip_network(subnet_cidr.strip(), strict=False)
    except ValueError:
        return None
    if not isinstance(net, ipaddress.IPv4Network):
        return None
    res = {str(x).strip() for x in reserved_ipv4 if x and str(x).strip()}
    hosts = list(net.hosts())
    for addr in reversed(hosts):
        s = str(addr)
        if s not in res:
            return s
    return None


def _segment_reserved_endpoint_ips(plan_links: list) -> set[str]:
    """All static IPv4 endpoints declared on these plan links (container addresses)."""
    out: set[str] = set()
    for pl in plan_links:
        for ip in (pl.source_ip, pl.target_ip):
            if ip and str(ip).strip():
                out.add(str(ip).strip())
    return out


class DockerProviderAttachmentError(RuntimeError):
    """Container was not attached to the CNS topology network or IP verification failed."""


def _verify_cns_network_attachment(
    nets: dict,
    net_name: str,
    expected_ipv4: str | None,
) -> str:
    """Verify ``docker inspect`` Networks contains the topology network and optional static IP."""
    cfg = nets.get(net_name)
    if not isinstance(cfg, dict):
        raise DockerProviderAttachmentError(
            "Failed to attach container to CNS network: "
            f"network {net_name!r} missing from inspect Networks "
            f"(have {sorted(nets)!r})"
        )
    ip = (cfg.get("IPAddress") or "").strip()
    if not ip:
        raise DockerProviderAttachmentError(
            f"Failed to attach container to CNS network: no IPv4 on {net_name!r}"
        )
    if expected_ipv4 and ip != expected_ipv4.strip():
        raise DockerProviderAttachmentError(
            "Failed to attach container to CNS network: "
            f"expected IP {expected_ipv4!r}, inspect has {ip!r} on {net_name!r}"
        )
    return ip


class FakeDockerRuntimeProvider(RuntimeProvider):
    """Timeline simulation — no Docker socket (tests / forced fake mode)."""

    def deploy(self, plan: DeploymentPlan) -> list[ProviderEvent]:
        events: list[ProviderEvent] = [
            (DeploymentEventLevel.INFO, "Deployment plan validated"),
            (
                DeploymentEventLevel.INFO,
                f"Runtime provider selected: {plan.runtime_target} (simulated)",
            ),
        ]
        if plan.segmented_networks:
            events.append(
                (DeploymentEventLevel.INFO, "Segmented multi-network mode (simulated): creating segment bridges"),
            )
            seen: set[str] = set()
            for pl in plan.plan_links:
                key = pl.network_name.strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                events.append(
                    (
                        DeploymentEventLevel.INFO,
                        f"Segment network scheduled: {pl.network_name} ({pl.cidr or 'no cidr'})",
                    )
                )
        else:
            events.append((DeploymentEventLevel.INFO, "Virtual network creation scheduled"))
        for pn in plan.nodes:
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Node container creation scheduled: {pn.name}",
                )
            )
        for src, tgt, net in plan.links:
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Link scheduled: {src} -> {tgt} ({net})",
                )
            )
        events.extend(
            [
                (DeploymentEventLevel.INFO, "Health checks scheduled"),
                (DeploymentEventLevel.INFO, "Deployment simulation completed"),
            ]
        )
        return events

    def destroy(self, topology_id: UUID, deployment_id: UUID) -> list[ProviderEvent]:
        _ = deployment_id
        return [
            (
                DeploymentEventLevel.INFO,
                f"Destroy simulated for topology {topology_id} (no Docker socket)",
            ),
        ]

    def inspect_topology_runtime(self, topology_id: UUID) -> ProviderRuntimeSnapshot:
        _ = topology_id
        return ProviderRuntimeSnapshot()

    def fetch_logs_for_node(
        self, topology_id: UUID, node_id: UUID, tail: int
    ) -> str | None:
        _ = (topology_id, node_id, tail)
        return None

    def fetch_stats_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> ProviderRuntimeStats | None:
        _ = (topology_id, node_id)
        return None

    def reconcile_runtime(
        self,
        topology_id: UUID,
        desired_node_ids: frozenset[UUID],
    ) -> ProviderReconciliationResult:
        _ = topology_id
        missing_nodes = tuple(sorted(desired_node_ids, key=lambda u: str(u)))
        lines = (
            "Simulated runtime (no Docker engine): reconciliation assumes drift.",
            f"Expected {len(missing_nodes)} node container(s) not present in engine.",
        )
        return ProviderReconciliationResult(
            missing_network=True,
            missing_node_ids=missing_nodes,
            stopped_containers=(),
            summary_lines=lines,
        )

    def heal_restart_stopped(self, topology_id: UUID) -> ProviderHealingResult:
        _ = topology_id
        return ProviderHealingResult()

    def find_container_id_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> str | None:
        _ = (topology_id, node_id)
        return "fake-container-id"

    def exec_in_node_container(
        self,
        topology_id: UUID,
        node_id: UUID,
        argv: list[str],
    ) -> ProviderExecResult | None:
        _ = (topology_id, node_id)
        cmd_s = " ".join(argv)
        return ProviderExecResult(0, f"simulated exec OK\n{cmd_s}\n", "")

    def resolve_node_ipv4(
        self, topology_id: UUID, node_id: UUID, source_node_id: UUID | None = None
    ) -> str | None:
        _ = (topology_id, node_id, source_node_id)
        return "10.200.0.10"

    def stop_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        _ = (topology_id, node_id)

    def restart_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        _ = (topology_id, node_id)

    def kill_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        _ = (topology_id, node_id)


class DockerRuntimeProvider(RuntimeProvider):
    """Real Docker engine orchestration for bridge networks + containers."""

    def __init__(self, client: docker.DockerClient | None = None) -> None:
        self._client = client or docker.from_env()

    def deploy(self, plan: DeploymentPlan) -> list[ProviderEvent]:
        if plan.segmented_networks:
            return self._deploy_segmented_multinet(plan)
        events: list[ProviderEvent] = []
        net_name = topology_network_name(plan.topology_id)

        events.append(
            (DeploymentEventLevel.INFO, "Docker provider selected (real engine)")
        )
        events.append((DeploymentEventLevel.INFO, f"Creating Docker network: {net_name}"))

        _remove_network_if_exists(self._client, net_name)

        ipam = _ipam_from_cidr(plan.subnet_cidr)
        try:
            self._client.networks.create(
                name=net_name,
                driver="bridge",
                ipam=ipam,
                labels=_base_labels(plan.topology_id),
                check_duplicate=True,
            )
            extra = f" (subnet {plan.subnet_cidr})" if plan.subnet_cidr else ""
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Docker network created: {net_name}{extra}",
                )
            )
        except APIError as exc:
            events.append(
                (
                    DeploymentEventLevel.ERROR,
                    f"Docker network creation failed: {exc.explanation}",
                )
            )
            _rollback_topology_deploy(self._client, plan.topology_id)
            raise

        try:
            deploy_events = self._deploy_nodes_on_network(plan, net_name)
        except Exception:
            _rollback_topology_deploy(self._client, plan.topology_id)
            raise
        events.extend(deploy_events)

        events.append(
            (
                DeploymentEventLevel.INFO,
                "Deployment completed successfully",
            )
        )
        return events

    def _deploy_segmented_multinet(self, plan: DeploymentPlan) -> list[ProviderEvent]:
        """One Docker bridge per logical ``network_name``; routers attach to multiple segments."""
        events: list[ProviderEvent] = []
        api = self._client.api
        tid = plan.topology_id
        events.append(
            (DeploymentEventLevel.INFO, "Docker provider selected (real engine, segmented networks)")
        )

        logical_to_docker: dict[str, str] = {}
        links_by_logical: dict[str, list] = defaultdict(list)
        for pl in plan.plan_links:
            key = pl.network_name.strip().lower()
            links_by_logical[key].append(pl)

        for key, lst in links_by_logical.items():
            logical_label = lst[0].network_name
            dname = segment_docker_network_name(tid, logical_label)
            logical_to_docker[key] = dname
            cidr = next((x.cidr for x in lst if x.cidr), None)
            user_logical_gw = next((x.gateway for x in lst if x.gateway), None)
            reserved = _segment_reserved_endpoint_ips(lst)
            docker_bridge_gw = _pick_docker_bridge_gateway_ip(cidr, reserved) if cidr else None
            _remove_network_if_exists(self._client, dname)
            if cidr and docker_bridge_gw is not None:
                ipam = _ipam_from_cidr_and_gateway(cidr, docker_bridge_gw)
            elif cidr:
                ipam = _ipam_from_cidr(cidr)
                events.append(
                    (
                        DeploymentEventLevel.WARNING,
                        f"Segment {logical_label}: could not pick a Docker bridge gateway outside "
                        f"reserved container IPs {sorted(reserved)} — using default IPAM gateway for {cidr}.",
                    )
                )
            else:
                ipam = None
            labels = dict(_base_labels(tid))
            labels["cns.logical_network"] = logical_label[:120]
            labels["cns.network_role"] = "segment"
            labels["cns.multinet"] = "true"
            try:
                self._client.networks.create(
                    name=dname,
                    driver="bridge",
                    ipam=ipam,
                    labels=labels,
                    check_duplicate=True,
                )
                events.append(
                    (
                        DeploymentEventLevel.INFO,
                        f"Segment Docker network created: {dname} (logical={logical_label}, cidr={cidr}, "
                        f"docker_bridge_gateway={docker_bridge_gw or 'default'}, "
                        f"reserved_container_ips={sorted(reserved)}, "
                        f"link_gateway_fields={user_logical_gw or 'none'} — topology default routes still use link gateway / router NIC IPs)",
                    )
                )
            except APIError as exc:
                events.append(
                    (DeploymentEventLevel.ERROR, f"Segment network {dname} failed: {exc.explanation}")
                )
                _rollback_topology_deploy(self._client, tid)
                raise

        attach: dict[UUID, list[tuple[str, str]]] = defaultdict(list)

        def _add_attach(nid: UUID, docker_net: str, ip: str | None) -> None:
            if not ip or not str(ip).strip():
                return
            ip_s = str(ip).strip()
            cur = attach[nid]
            if any(x[0] == docker_net for x in cur):
                return
            cur.append((docker_net, ip_s))

        for pl in plan.plan_links:
            key = pl.network_name.strip().lower()
            dnet = logical_to_docker[key]
            _add_attach(pl.source_node_id, dnet, pl.source_ip)
            _add_attach(pl.target_node_id, dnet, pl.target_ip)

        node_map = {n.id: n for n in plan.nodes}
        ordered_nodes = sorted(
            plan.nodes,
            key=lambda n: (n.node_type == "router", n.name),
        )

        def _attached_net_names(ctr) -> list[str]:
            try:
                ctr.reload()
            except APIError:
                return []
            nets = (ctr.attrs.get("NetworkSettings") or {}).get("Networks") or {}
            return sorted(nets.keys())

        for pn in ordered_nodes:
            atts = attach.get(pn.id) or []
            if not atts:
                events.append(
                    (
                        DeploymentEventLevel.WARNING,
                        f"Skipping node {pn.name}: no resolved segment IPs (check link endpoint IPs for multinet).",
                    )
                )
                continue

            cname = container_name(pn.id, pn.name)
            image_ref = _resolve_image(pn.image)
            is_router = pn.node_type == "router"
            events.append((DeploymentEventLevel.INFO, f"Pulling/using image: {image_ref} ({cname})"))
            _remove_container_if_exists(self._client, cname)

            if is_router:
                cmd = ["sleep", "infinity"]
            else:
                cmd = _default_command(image_ref)

            try:
                self._client.images.pull(image_ref)
            except (APIError, ImageNotFound) as exc:
                events.append(
                    (DeploymentEventLevel.WARNING, f"Image pull warning for {image_ref}: {exc}")
                )

            first_net, first_ip = atts[0]
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Segment container op=create container={cname} docker_network={first_net} "
                    f"requested_ipv4={first_ip} existing_attachments_before_create=[]",
                )
            )
            net_cfg = self._make_cns_networking_config(first_net, first_ip)
            labels = _container_labels(
                tid, pn.id, "segment_router" if is_router else "leaf"
            )
            if is_router:
                host_conf = api.create_host_config(
                    cap_add=["NET_ADMIN"],
                    sysctls=dict(_SEGMENT_ROUTER_SYSCTLS),
                )
                hc_log = (
                    "cap_add=[NET_ADMIN] "
                    f"sysctls={_SEGMENT_ROUTER_SYSCTLS!r}"
                )
            else:
                host_conf = api.create_host_config(cap_add=["NET_ADMIN"])
                hc_log = "cap_add=[NET_ADMIN]"
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Segment container host_config planned: container={cname} {hc_log}",
                )
            )

            def _segment_create_container(hc) -> str:
                r = api.create_container(
                    image_ref,
                    command=cmd,
                    name=cname,
                    labels=labels,
                    networking_config=net_cfg,
                    host_config=hc,
                    detach=True,
                )
                return r["Id"]

            try:
                cid = _segment_create_container(host_conf)
            except APIError as exc:
                if is_router and _segmented_sysctl_hostconfig_rejected(exc):
                    events.append(
                        (
                            DeploymentEventLevel.WARNING,
                            f"Segment container sysctl at create rejected for {cname} "
                            f"({exc.explanation}); retrying with cap_add=[NET_ADMIN] only "
                            "(post-start sysctl still applied via exec).",
                        )
                    )
                    try:
                        cid = _segment_create_container(
                            api.create_host_config(cap_add=["NET_ADMIN"])
                        )
                    except APIError as exc2:
                        msg = (
                            f"Segmented container create failed ({cname}) after sysctl retry: "
                            f"{exc2.explanation}"
                        )
                        if _net_admin_or_policy_denied_hint(exc2):
                            msg += (
                                " CNS segmented topologies require CAP_NET_ADMIN on each container "
                                "for routing setup; allow cap_add NET_ADMIN in Docker/engine policy."
                            )
                        events.append((DeploymentEventLevel.ERROR, msg))
                        _rollback_topology_deploy(self._client, tid)
                        raise DockerProviderAttachmentError(msg) from exc2
                else:
                    msg = f"Segmented container create failed ({cname}): {exc.explanation}"
                    if _net_admin_or_policy_denied_hint(exc):
                        msg += (
                            " CNS segmented topologies require CAP_NET_ADMIN on each container "
                            "for routing setup; allow cap_add NET_ADMIN in Docker/engine policy."
                        )
                    events.append((DeploymentEventLevel.ERROR, msg))
                    _rollback_topology_deploy(self._client, tid)
                    raise DockerProviderAttachmentError(msg) from exc
            try:
                api.start(cid)
                ctr = self._client.containers.get(cid)
            except APIError as exc:
                msg = f"Segmented container start failed ({cname}): {exc.explanation}"
                events.append((DeploymentEventLevel.ERROR, msg))
                _rollback_topology_deploy(self._client, tid)
                raise DockerProviderAttachmentError(msg) from exc

            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Segment container after_start container={cname} "
                    f"attached_networks={','.join(_attached_net_names(ctr))}",
                )
            )

            for extra_net, extra_ip in atts[1:]:
                try:
                    before_nets = ",".join(_attached_net_names(ctr))
                    events.append(
                        (
                            DeploymentEventLevel.INFO,
                            f"Segment container op=connect container={cname} docker_network={extra_net} "
                            f"requested_ipv4={extra_ip} existing_attachments=[{before_nets}]",
                        )
                    )
                    nw = self._client.networks.get(extra_net)
                    nw.connect(ctr.id, ipv4_address=extra_ip)
                    events.append(
                        (
                            DeploymentEventLevel.INFO,
                            f"Attached {cname} to segment {extra_net} as {extra_ip}",
                        )
                    )
                except APIError as exc:
                    msg = f"Secondary attach failed ({cname} -> {extra_net}): {exc.explanation}"
                    events.append((DeploymentEventLevel.ERROR, msg))
                    _rollback_topology_deploy(self._client, tid)
                    raise DockerProviderAttachmentError(msg) from exc

            try:
                ctr.reload()
            except APIError:
                pass
            events.append((DeploymentEventLevel.INFO, f"Container started (segmented): {cname}"))
            if is_router:
                enable_router_forwarding(ctr, cname, events)

        if not configure_container_routes(self._client, plan, node_map, events):
            msg = (
                "Segmented deployment failed: leaf default route was not set to the segment "
                "router IP (requires CAP_NET_ADMIN and successful ip route add). "
                "See leaf route validation events above."
            )
            events.append((DeploymentEventLevel.ERROR, msg))
            _rollback_topology_deploy(self._client, tid)
            raise DockerProviderAttachmentError(msg)
        events.append((DeploymentEventLevel.INFO, "Deployment completed successfully (segmented)"))
        return events

    def _make_cns_networking_config(self, net_name: str, ipv4: str | None):
        """Build Docker Engine networking_config for the topology bridge network."""
        api = self._client.api
        if ipv4:
            ep = api.create_endpoint_config(ipv4_address=ipv4.strip())
        else:
            ep = api.create_endpoint_config()
        return api.create_networking_config({net_name: ep})

    def _create_container_on_cns_network(
        self,
        image_ref: str,
        cname: str,
        cmd: list[str] | None,
        labels: dict[str, str],
        net_name: str,
        ipv4: str | None,
    ):
        """Create on the CNS bridge using only ``networking_config`` (low-level API).

        High-level ``containers.create(..., network=..., networking_config=...)`` sets
        ``HostConfig.NetworkMode`` to the network name, which can ignore endpoint
        ``IPv4Address``; the engine then assigns the next pool IP (e.g. ``.2``).
        """
        api = self._client.api
        net_cfg = self._make_cns_networking_config(net_name, ipv4)
        resp = api.create_container(
            image_ref,
            command=cmd,
            name=cname,
            labels=labels,
            networking_config=net_cfg,
            detach=True,
        )
        cid = resp["Id"]
        api.start(cid)
        return self._client.containers.get(cid)

    def _deploy_nodes_on_network(
        self,
        plan: DeploymentPlan,
        net_name: str,
    ) -> list[ProviderEvent]:
        """Create containers on ``net_name`` at create-time via ``networking_config``."""
        events: list[ProviderEvent] = []
        for pn in plan.nodes:
            cname = container_name(pn.id, pn.name)
            image_ref = _resolve_image(pn.image)
            events.append(
                (DeploymentEventLevel.INFO, f"Pulling/using image: {image_ref}")
            )

            _remove_container_if_exists(self._client, cname)

            cmd = _default_command(image_ref)
            try:
                self._client.images.pull(image_ref)
            except (APIError, ImageNotFound) as exc:
                events.append(
                    (
                        DeploymentEventLevel.WARNING,
                        f"Image pull warning for {image_ref}: {exc}",
                    )
                )

            try_static = bool(pn.ip_address and str(pn.ip_address).strip())
            expect_exact_ip = (
                pn.ip_address.strip() if try_static else None
            )

            ipv4_for_cfg = pn.ip_address.strip() if try_static else None

            try:
                events.append(
                    (
                        DeploymentEventLevel.INFO,
                        f"Creating container on {net_name}: {cname}",
                    )
                )
                container = self._create_container_on_cns_network(
                    image_ref,
                    cname,
                    cmd,
                    _container_labels(
                        plan.topology_id,
                        pn.id,
                        "segment_router" if pn.node_type == "router" else "leaf",
                    ),
                    net_name,
                    ipv4_for_cfg,
                )
                events.append(
                    (DeploymentEventLevel.INFO, f"Container started: {cname}"),
                )
            except APIError as exc:
                msg = (
                    "Docker networking_config / container create failed "
                    f"({net_name}, {cname}): {exc.explanation}"
                )
                events.append((DeploymentEventLevel.ERROR, msg))
                raise DockerProviderAttachmentError(msg) from exc

            try:
                container.reload()
            except APIError as exc:
                msg = (
                    "Failed to verify CNS network attachment: "
                    f"reload failed for {cname}: {exc.explanation}"
                )
                events.append((DeploymentEventLevel.ERROR, msg))
                raise DockerProviderAttachmentError(msg) from exc

            nets_post = (
                (container.attrs.get("NetworkSettings") or {}).get("Networks") or {}
            )

            try:
                verified_ip = _verify_cns_network_attachment(
                    nets_post,
                    net_name,
                    expect_exact_ip if try_static else None,
                )
            except DockerProviderAttachmentError as exc:
                events.append(
                    (DeploymentEventLevel.ERROR, str(exc)),
                )
                raise

            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"CNS network attached: {cname} -> {verified_ip}",
                )
            )
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Verified CNS IP: {verified_ip} ({cname})",
                )
            )

            labeled_ids_deploy = _labeled_topology_network_ids(
                self._client, plan.topology_id
            )
            display_ips = _runtime_ipv4_display_map(
                nets_post, plan.topology_id, labeled_ids_deploy
            )
            ip_summary = ", ".join(f"{k}={v}" for k, v in display_ips.items())
            if ip_summary:
                events.append(
                    (
                        DeploymentEventLevel.INFO,
                        f"CNS runtime IPs: {ip_summary}",
                    )
                )

        return events

    def destroy(self, topology_id: UUID, deployment_id: UUID) -> list[ProviderEvent]:
        _ = deployment_id
        events: list[ProviderEvent] = []
        tid = str(topology_id)

        containers = self._client.containers.list(
            all=True,
            filters={"label": [f"cns.topology_id={tid}"]},
        )
        for ctr in containers:
            try:
                events.append(
                    (
                        DeploymentEventLevel.INFO,
                        f"Stopping container: {ctr.name}",
                    )
                )
                ctr.stop(timeout=15)
                ctr.remove()
                events.append(
                    (
                        DeploymentEventLevel.INFO,
                        f"Removed container: {ctr.name}",
                    )
                )
            except APIError as exc:
                events.append(
                    (
                        DeploymentEventLevel.WARNING,
                        f"Container teardown issue ({ctr.name}): {exc.explanation}",
                    )
                )

        events.append(
            (DeploymentEventLevel.INFO, "Removing labeled Docker networks for topology (legacy + segments)")
        )
        _remove_all_topology_networks(self._client, topology_id)
        events.append(
            (DeploymentEventLevel.INFO, "Docker network cleanup completed (best-effort)")
        )

        events.append(
            (
                DeploymentEventLevel.INFO,
                "Runtime resources destroyed",
            )
        )
        return events

    def inspect_topology_runtime(self, topology_id: UUID) -> ProviderRuntimeSnapshot:
        flt = _topology_runtime_filters(topology_id)
        nets_raw: list = []
        ctrs_raw: list = []
        try:
            nets_raw = list(self._client.networks.list(filters=flt))
        except APIError:
            pass
        try:
            ctrs_raw = list(self._client.containers.list(all=True, filters=flt))
        except APIError:
            pass
        labeled_ids = _labeled_topology_network_ids(self._client, topology_id)
        nets = tuple(_network_record(n) for n in nets_raw)
        ctrs = tuple(
            _container_record(c, topology_id, labeled_ids) for c in ctrs_raw
        )
        return ProviderRuntimeSnapshot(networks=nets, containers=ctrs)

    def fetch_logs_for_node(
        self, topology_id: UUID, node_id: UUID, tail: int
    ) -> str | None:
        ctr = _find_managed_container(self._client, topology_id, node_id)
        if ctr is None:
            return None
        try:
            n = max(1, min(int(tail), 10000))
            raw = ctr.logs(
                tail=n,
                timestamps=True,
                stdout=True,
                stderr=True,
            )
            if isinstance(raw, bytes):
                return raw.decode("utf-8", errors="replace")
            return str(raw)
        except APIError:
            return None

    def fetch_stats_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> ProviderRuntimeStats | None:
        ctr = _find_managed_container(self._client, topology_id, node_id)
        if ctr is None:
            return None
        try:
            stats = ctr.stats(stream=False)
        except APIError:
            return None
        return _docker_stats_to_provider(stats)

    def reconcile_runtime(
        self,
        topology_id: UUID,
        desired_node_ids: frozenset[UUID],
    ) -> ProviderReconciliationResult:
        flt = _topology_runtime_filters(topology_id)
        missing_network = True
        try:
            nets = self._client.networks.list(filters=flt)
            missing_network = len(nets) == 0
        except APIError:
            missing_network = True

        try:
            ctrs = list(self._client.containers.list(all=True, filters=flt))
        except APIError:
            ctrs = []

        labeled_ids = _labeled_topology_network_ids(self._client, topology_id)

        by_node: dict[UUID, RuntimeContainerRecord] = {}
        stopped: list[tuple[str, str]] = []
        for c in ctrs:
            rec = _container_record(c, topology_id, labeled_ids)
            if rec.node_id is not None:
                by_node[rec.node_id] = rec
                if not rec.running:
                    stopped.append((rec.container_id, rec.name))

        missing_nodes: list[UUID] = []
        for nid in sorted(desired_node_ids, key=lambda u: str(u)):
            if nid not in by_node:
                missing_nodes.append(nid)

        lines: list[str] = []
        if missing_network:
            lines.append(
                "Drift: managed Docker network labeled for this topology was not found."
            )
        for nid in missing_nodes:
            lines.append(f"Missing container for desired node_id={nid}.")
        for cid, nm in stopped:
            sid = cid[:12] if cid else "?"
            lines.append(f"Stopped or non-running container detected: {nm} ({sid}).")

        if not lines:
            lines.append(
                "No drift detected: labeled network present and all desired nodes running."
            )

        return ProviderReconciliationResult(
            missing_network=missing_network,
            missing_node_ids=tuple(missing_nodes),
            stopped_containers=tuple(stopped),
            summary_lines=tuple(lines),
        )

    def heal_restart_stopped(self, topology_id: UUID) -> ProviderHealingResult:
        flt = _topology_runtime_filters(topology_id)
        restarted: list[tuple[str, str]] = []
        errors: list[str] = []
        try:
            ctrs = list(self._client.containers.list(all=True, filters=flt))
        except APIError as exc:
            return ProviderHealingResult(errors=(str(exc),))
        labeled_ids = _labeled_topology_network_ids(self._client, topology_id)
        for c in ctrs:
            rec = _container_record(c, topology_id, labeled_ids)
            if rec.node_id is None:
                continue
            if rec.running:
                continue
            try:
                c.start()
                self._post_start_routing_for_container(c)
                restarted.append((rec.container_id, rec.name))
            except APIError as exc:
                errors.append(f"{rec.name}: {exc.explanation}")
        return ProviderHealingResult(
            restarted=tuple(restarted),
            errors=tuple(errors),
        )

    def start_container_by_id(self, container_id: str) -> None:
        """Start a container by engine id (optional helper for tooling/tests)."""
        try:
            ctr = self._client.containers.get(container_id)
            ctr.start()
        except NotFound as exc:
            raise exc
        except APIError:
            raise

    def find_container_id_for_node(
        self, topology_id: UUID, node_id: UUID
    ) -> str | None:
        ctr = _find_managed_container(self._client, topology_id, node_id)
        return ctr.id if ctr else None

    def exec_in_node_container(
        self,
        topology_id: UUID,
        node_id: UUID,
        argv: list[str],
    ) -> ProviderExecResult | None:
        ctr = _find_managed_container(self._client, topology_id, node_id)
        if ctr is None:
            return None
        try:
            raw = ctr.exec_run(argv, demux=True)
        except APIError as exc:
            expl = getattr(exc, "explanation", None) or str(exc)
            return ProviderExecResult(1, "", expl)
        return _normalize_exec_run(raw)

    def resolve_node_ipv4(
        self,
        topology_id: UUID,
        node_id: UUID,
        source_node_id: UUID | None = None,
    ) -> str | None:
        tgt_ctr = _find_managed_container(self._client, topology_id, node_id)
        if tgt_ctr is None:
            return None
        try:
            tgt_ctr.reload()
        except APIError:
            pass
        tgt_nets = _container_iface_ipv4_map(
            (tgt_ctr.attrs.get("NetworkSettings") or {}).get("Networks") or {}
        )
        labeled_ids = _labeled_topology_network_ids(self._client, topology_id)
        nets = (tgt_ctr.attrs.get("NetworkSettings") or {}).get("Networks") or {}

        if source_node_id is None:
            m = _runtime_ipv4_display_map(nets, topology_id, labeled_ids)
            if m:
                return sorted(m.values())[-1]
            return _pick_cns_ipv4(nets, topology_id, labeled_ids)

        src_ctr = _find_managed_container(self._client, topology_id, source_node_id)
        if src_ctr is None:
            m = _runtime_ipv4_display_map(nets, topology_id, labeled_ids)
            if m:
                return sorted(m.values())[-1]
            return _pick_cns_ipv4(nets, topology_id, labeled_ids)
        try:
            src_ctr.reload()
        except APIError:
            pass
        src_nets = _container_iface_ipv4_map(
            (src_ctr.attrs.get("NetworkSettings") or {}).get("Networks") or {}
        )
        picked = _pick_target_ipv4_for_traffic(src_nets, tgt_nets)
        if picked:
            return picked
        if tgt_nets:
            return sorted(tgt_nets.values())[0]
        return _pick_cns_ipv4(nets, topology_id, labeled_ids)

    def _post_start_routing_for_container(self, ctr) -> None:
        """After start/restart: detach default bridge; re-apply sysctl for segment routers."""
        try:
            _disconnect_default_bridge(self._client, ctr.id)
            ctr.reload()
            cfg = ctr.attrs.get("Config") or {}
            lbls = cfg.get("Labels") or {}
            if isinstance(lbls, dict) and str(lbls.get("cns.forwarding_role") or "") == "segment_router":
                nm = ctr.name or ""
                if isinstance(nm, str) and nm.startswith("/"):
                    nm = nm[1:]
                enable_router_forwarding(ctr, nm or "segment_router", [])
        except APIError:
            pass

    def stop_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        ctr = _find_managed_container(self._client, topology_id, node_id)
        if ctr is None:
            raise LookupError("runtime container not found for node")
        try:
            ctr.stop(timeout=15)
        except APIError as exc:
            raise RuntimeError(exc.explanation or str(exc)) from exc

    def restart_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        ctr = _find_managed_container(self._client, topology_id, node_id)
        if ctr is None:
            raise LookupError("runtime container not found for node")
        try:
            ctr.restart(timeout=15)
        except APIError as exc:
            raise RuntimeError(exc.explanation or str(exc)) from exc
        self._post_start_routing_for_container(ctr)

    def kill_node_container(self, topology_id: UUID, node_id: UUID) -> None:
        ctr = _find_managed_container(self._client, topology_id, node_id)
        if ctr is None:
            raise LookupError("runtime container not found for node")
        try:
            ctr.kill()
        except APIError as exc:
            raise RuntimeError(exc.explanation or str(exc)) from exc


def _normalize_exec_run(raw) -> ProviderExecResult:
    """Normalize docker-py ``ExecResult`` or legacy tuple."""
    if hasattr(raw, "exit_code"):
        ec = raw.exit_code
        out = raw.output
    elif isinstance(raw, tuple) and len(raw) >= 2:
        ec, out = raw[0], raw[1]
    else:
        return ProviderExecResult(1, "", "unexpected exec response")

    if isinstance(out, tuple) and len(out) >= 2:
        so_b, se_b = out[0] or b"", out[1] or b""
    elif isinstance(out, tuple) and len(out) == 1:
        so_b, se_b = out[0] or b"", b""
    else:
        so_b = out if isinstance(out, (bytes, bytearray)) else b""
        se_b = b""

    def dec(x) -> str:
        if isinstance(x, (bytes, bytearray)):
            return bytes(x).decode("utf-8", errors="replace")
        return str(x) if x is not None else ""

    return ProviderExecResult(int(ec) if ec is not None else -1, dec(so_b), dec(se_b))


def _topology_runtime_filters(topology_id: UUID) -> dict[str, list[str]]:
    tid = str(topology_id)
    return {"label": [f"cns.topology_id={tid}", "cns.managed=true"]}


def _find_managed_container(
    client: docker.DockerClient,
    topology_id: UUID,
    node_id: UUID,
):
    tid = str(topology_id)
    nid = str(node_id)
    try:
        lst = client.containers.list(
            all=True,
            filters={
                "label": [
                    f"cns.topology_id={tid}",
                    f"cns.node_id={nid}",
                    "cns.managed=true",
                ]
            },
        )
        return lst[0] if lst else None
    except APIError:
        return None


def _container_iface_ipv4_map(nets: dict) -> dict[str, str]:
    """Docker network name -> container IPv4, excluding the default ``bridge``."""
    out: dict[str, str] = {}
    for k, cfg in (nets or {}).items():
        if k == _default_bridge_network_name():
            continue
        if not isinstance(cfg, dict):
            continue
        ip = (cfg.get("IPAddress") or "").strip()
        if ip:
            out[str(k)] = ip
    return out


def _ipv4_same_slash24(a: str, b: str) -> bool:
    try:
        aa = ipaddress.ip_address(a)
        bb = ipaddress.ip_address(b)
    except ValueError:
        return False
    if not isinstance(aa, ipaddress.IPv4Address) or not isinstance(bb, ipaddress.IPv4Address):
        return False
    return aa.packed[:3] == bb.packed[:3]


def _pick_target_ipv4_for_traffic(
    src_by_net: dict[str, str],
    tgt_by_net: dict[str, str],
) -> str | None:
    """
    Pick a destination IPv4 for ping/http from ``src`` to ``tgt``.

    Prefer a Docker network both endpoints share (L2 adjacent). If none (routed
    cross-segment), pick a target address not in the same /24 as any source address.
    """
    shared = sorted(set(src_by_net) & set(tgt_by_net))
    for net in shared:
        ip = tgt_by_net.get(net)
        if ip:
            return ip
    src_vals = [s for s in src_by_net.values() if s]
    for cand in sorted(tgt_by_net.values()):
        if not cand:
            continue
        if not src_vals:
            return cand
        if all(not _ipv4_same_slash24(cand, s) for s in src_vals):
            return cand
    if tgt_by_net:
        return sorted(tgt_by_net.values())[0]
    return None


def _exec_decode(exec_res) -> tuple[int, str, str]:
    if hasattr(exec_res, "exit_code"):
        ec = exec_res.exit_code
        out = exec_res.output
    else:
        ec, out = exec_res[0], exec_res[1] if len(exec_res) > 1 else b""

    if isinstance(out, tuple) and len(out) >= 2:
        so_b, se_b = out[0] or b"", out[1] or b""
    elif isinstance(out, tuple) and len(out) == 1:
        so_b, se_b = out[0] or b"", b""
    else:
        so_b = out if isinstance(out, (bytes, bytearray)) else b""
        se_b = b""

    def dec(x: bytes | bytearray) -> str:
        return bytes(x).decode("utf-8", errors="replace")

    return int(ec) if ec is not None else -1, dec(so_b), dec(se_b)


def _segment_router_forwarding_shell() -> str:
    return (
        "set +e; "
        "sysctl -w net.ipv4.ip_forward=1; "
        "for f in all default lo; do sysctl -w net.ipv4.conf.${f}.rp_filter=0; done; "
        "for iface in /sys/class/net/eth*; do "
        "  n=${iface##*/}; "
        "  sysctl -w net.ipv4.conf.${n}.rp_filter=0; "
        "done; "
        "exit 0"
    )


def enable_router_forwarding(ctr, router_display_name: str, events: list) -> None:
    """Enable IPv4 forwarding and relax rp_filter for multinet segment routers (post-attach)."""
    shell = _segment_router_forwarding_shell()
    events.append(
        (
            DeploymentEventLevel.INFO,
            f"Routing sysctl: container={router_display_name} op=exec "
            f"script={shell!r}",
        )
    )
    try:
        raw = ctr.exec_run(["/bin/sh", "-c", shell], demux=True)
        ec, so, se = _exec_decode(raw)
        tail = (so + se).strip()[:1800]
        events.append(
            (
                DeploymentEventLevel.INFO,
                f"Routing sysctl result: container={router_display_name} exit={ec} output={tail!r}",
            )
        )
        chk = ctr.exec_run(
            ["/bin/sh", "-c", "cat /proc/sys/net/ipv4/ip_forward"],
            demux=True,
        )
        _, fwd_s, _ = _exec_decode(chk)
        fwd_s = fwd_s.strip()
        events.append(
            (
                DeploymentEventLevel.INFO,
                f"Routing verify: container={router_display_name} "
                f"/proc/sys/net/ipv4/ip_forward={fwd_s!r}",
            )
        )
    except APIError as exc:
        events.append(
            (
                DeploymentEventLevel.WARNING,
                f"Routing sysctl failed: container={router_display_name}: {exc.explanation}",
            )
        )


_LEAF_GW_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")

# Placeholder must be only [0-9.] (validated before substitute).
_LEAF_RT_GW_PLACEHOLDER = "__CNS_GW__"

_LEAF_DEFAULT_ROUTE_APPLY_SH = r"""set +e
GW='__CNS_GW__'
DEV=""
extract_dev() {
  awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}' 2>/dev/null
}
if command -v ip >/dev/null 2>&1; then
  R=$(ip -4 route get "$GW" 2>/dev/null) || true
  if [ -n "$R" ]; then
    DEV=$(printf '%s\n' "$R" | extract_dev)
  fi
fi
if [ -z "$DEV" ]; then
  L0=$(ip -4 route show default 2>/dev/null | head -1) || true
  if [ -n "$L0" ]; then
    DEV=$(printf '%s\n' "$L0" | extract_dev)
  fi
fi
if [ -z "$DEV" ]; then DEV=eth0; fi

IP_OK=0
if command -v ip >/dev/null 2>&1 && ip -4 route show >/dev/null 2>&1; then
  IP_OK=1
fi

ADD_ERR=""
if [ "$IP_OK" = 1 ]; then
  n=0
  while [ "$n" -lt 12 ]; do
    L=$(ip -4 route show default 2>/dev/null | head -1) || true
    [ -z "$L" ] && break
    ip -4 route del $L 2>/dev/null || ip -4 route del default 2>/dev/null || break
    n=$((n+1))
  done
  ip -4 route del default 2>/dev/null || true
  ip -4 route del default dev "$DEV" 2>/dev/null || true
  ADD_ERR=$(ip -4 route add default via "$GW" dev "$DEV" 2>&1) || ADD_ERR="$ADD_ERR (ip_add_nonzero=$?)"
else
  n=0
  while [ "$n" -lt 12 ]; do
    route del default 2>/dev/null || break
    n=$((n+1))
  done
  if route add default gw "$GW" "$DEV" 2>/dev/null; then
    ADD_ERR=""
  elif route add default gw "$GW" dev "$DEV" 2>/dev/null; then
    ADD_ERR=""
  elif route add default gw "$GW" netmask 0.0.0.0 "$DEV" 2>/dev/null; then
    ADD_ERR=""
  else
    ADD_ERR=$(route add default gw "$GW" "$DEV" 2>&1 || echo " (route_add_failed)")
  fi
fi

printf 'CNS_LEAF_RT_STACK=ip_ok:%s dev:%s\n' "$IP_OK" "$DEV"
[ -n "$ADD_ERR" ] && printf 'CNS_LEAF_RT_ADD_MSG=%s\n' "$ADD_ERR"
ip -4 route show default 2>/dev/null || true
route -n 2>/dev/null | head -12 || true
exit 0
"""


def _leaf_default_route_apply_script(gw_ip: str) -> str:
    """
    Replace Docker-injected IPv4 default (often *.254) with default via the segment router.

    Uses explicit ``ip -4 route del`` (including full-line delete) and
    ``ip -4 route add default via GW dev DEV`` when ``ip -4 route`` works; otherwise
    BusyBox / legacy ``route`` commands. ``DEV`` is taken from ``ip route get GW`` or the
    current default route.
    """
    gw = gw_ip.strip()
    if not _LEAF_GW_IPV4.match(gw):
        raise ValueError(f"refusing unsafe gateway IP for leaf route script: {gw_ip!r}")
    if _LEAF_RT_GW_PLACEHOLDER in gw:
        raise ValueError("gateway IP collides with internal placeholder")
    return _LEAF_DEFAULT_ROUTE_APPLY_SH.replace(_LEAF_RT_GW_PLACEHOLDER, gw)


def _first_ipv4_default_route_line(route_text: str) -> str | None:
    """First IPv4 default route line from ``ip -4 route`` or ``route -n`` style output."""
    for raw in route_text.splitlines():
        line = raw.strip()
        if line.startswith("default") and "via" in line:
            return line
    for raw in route_text.splitlines():
        parts = raw.split()
        if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] != "0.0.0.0":
            return line
    return None


def _ipv4_default_gateway_from_line(line: str) -> str | None:
    m = re.match(r"default\s+via\s+(\d{1,3}(?:\.\d{1,3}){3})\b", line.strip())
    if m:
        return m.group(1)
    parts = line.split()
    if len(parts) >= 3 and parts[0] == "0.0.0.0":
        g = parts[1]
        if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", g):
            return g
    return None


def _validate_leaf_default_route(route_text: str, expected_gw: str) -> tuple[bool, list[str]]:
    """
    Check that the effective IPv4 default uses ``expected_gw`` and not a typical docker bridge
    host (*.254) from our IPAM convention.
    """
    exp = expected_gw.strip()
    msgs: list[str] = []
    line = _first_ipv4_default_route_line(route_text)
    if line is None:
        return False, ["no IPv4 default route found after apply"]
    gw_obs = _ipv4_default_gateway_from_line(line)
    if gw_obs is None:
        return False, [f"could not parse default gateway from line: {line!r}"]
    if gw_obs != exp:
        msgs.append(f"default gateway is {gw_obs!r}, expected {exp!r} (line={line!r})")
    if gw_obs.endswith(".254"):
        msgs.append(
            f"default gateway still uses *.254 ({gw_obs!r}) — likely Docker bridge, not router"
        )
    ok = gw_obs == exp and not gw_obs.endswith(".254")
    return ok, msgs


def configure_container_routes(
    client: docker.DockerClient,
    plan: DeploymentPlan,
    node_map: dict,
    events: list,
) -> bool:
    """Default routes on leaf nodes toward the adjacent router on each segment (multinet).

    Returns True only if every processed leaf ended with the expected default via the router.
    """
    all_ok = True
    for pl in plan.plan_links:
        src = node_map.get(pl.source_node_id)
        tgt = node_map.get(pl.target_node_id)
        if src is None or tgt is None:
            continue
        leaf = gw_ip = None
        if src.node_type != "router" and tgt.node_type == "router":
            leaf, gw_ip = src, pl.target_ip
        elif tgt.node_type != "router" and src.node_type == "router":
            leaf, gw_ip = tgt, pl.source_ip
        else:
            continue
        if leaf.node_type == "router" or not gw_ip:
            continue
        ctr = _find_managed_container(client, plan.topology_id, leaf.id)
        if ctr is None:
            continue
        cname = ctr.name or leaf.name
        if isinstance(cname, str) and cname.startswith("/"):
            cname = cname[1:]
        gw_s = str(gw_ip).strip()
        try:
            shell = _leaf_default_route_apply_script(gw_s)
        except ValueError as ve:
            events.append(
                (
                    DeploymentEventLevel.WARNING,
                    f"Leaf routes skipped: container={cname} reason={ve}",
                )
            )
            all_ok = False
            continue
        try:
            if_before = ctr.exec_run(
                ["/bin/sh", "-c", "ip -4 addr show 2>/dev/null || true"],
                demux=True,
            )
            _, ib_out, _ = _exec_decode(if_before)
            ib_trim = "\n".join(ib_out.splitlines()[:32])
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Leaf interfaces before: container={cname} interfaces={ib_trim!r}",
                )
            )
            before = ctr.exec_run(
                ["/bin/sh", "-c", "ip -4 route show 2>/dev/null || route -n 2>/dev/null || true"],
                demux=True,
            )
            _, b_out, _ = _exec_decode(before)
            b_trim = "\n".join(b_out.splitlines()[:24])
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Leaf routes before: container={cname} op=inspect routes={b_trim!r}",
                )
            )
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Leaf routes commands: container={cname} gw={gw_s} "
                    "primary='ip -4 route del default' (repeat + full-line delete); "
                    f"then 'ip -4 route add default via {gw_s} dev <detected>'; "
                    "fallback='route del default' then 'route add default gw <gw> <dev>' variants",
                )
            )
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Leaf routes apply: container={cname} op=exec script={shell!r}",
                )
            )
            raw = ctr.exec_run(["/bin/sh", "-c", shell], demux=True)
            ec, so, se = _exec_decode(raw)
            tail = (so + se).strip()[:1800]
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Leaf routes exec result: container={cname} exit={ec} output={tail!r}",
                )
            )
            after = ctr.exec_run(
                ["/bin/sh", "-c", "ip -4 route show default 2>/dev/null || true; ip -4 route show 2>/dev/null | head -40 || true; route -n 2>/dev/null | head -16 || true"],
                demux=True,
            )
            _, a_out, _ = _exec_decode(after)
            a_trim = "\n".join(a_out.splitlines()[:32])
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Leaf routes after: container={cname} routes={a_trim!r}",
                )
            )
            ok, vmsgs = _validate_leaf_default_route(a_out, gw_s)
            if ok:
                events.append(
                    (
                        DeploymentEventLevel.INFO,
                        f"Leaf route validation OK: container={cname} default_via={gw_s!r}",
                    )
                )
            else:
                all_ok = False
                for vm in vmsgs:
                    events.append(
                        (
                            DeploymentEventLevel.WARNING,
                            f"Leaf route validation issue: container={cname} {vm}",
                        )
                    )
                events.append(
                    (
                        DeploymentEventLevel.WARNING,
                        f"Leaf route validation FAILED: container={cname} "
                        f"expected_default_via={gw_s!r} snapshot={a_trim!r}",
                    )
                )
            ifc = ctr.exec_run(
                ["/bin/sh", "-c", "ip -4 addr show 2>/dev/null || true"],
                demux=True,
            )
            _, i_out, _ = _exec_decode(ifc)
            i_trim = "\n".join(i_out.splitlines()[:32])
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Leaf interfaces after: container={cname} interfaces={i_trim!r}",
                )
            )
        except APIError as exc:
            all_ok = False
            events.append(
                (
                    DeploymentEventLevel.WARNING,
                    f"Leaf routes failed: container={cname}: {exc.explanation}",
                )
            )
    return all_ok


def inspect_container_networking(ctr) -> tuple[tuple[str, ...], tuple[str, ...], bool | None]:
    """Exec ``ip route`` / ``ip addr`` and read ``ip_forward`` inside a running container."""
    try:
        ctr.reload()
        if not (ctr.attrs.get("State") or {}).get("Running"):
            return (), (), None
    except APIError:
        return (), (), None
    script = (
        "printf 'FWD:'; cat /proc/sys/net/ipv4/ip_forward 2>/dev/null || echo ?; "
        "printf '\\nROUTES\\n'; ip -4 route show 2>/dev/null || route -n 2>/dev/null || true; "
        "printf '\\nINTERFACES\\n'; ip -4 addr show 2>/dev/null || true"
    )
    try:
        raw = ctr.exec_run(["/bin/sh", "-c", script], demux=True)
        ec, so, se = _exec_decode(raw)
        text = (so + se).strip()
    except APIError:
        return (), (), None

    ip_fwd: bool | None = None
    routes_lines: tuple[str, ...] = ()
    iface_lines: tuple[str, ...] = ()
    if "ROUTES" in text and "INTERFACES" in text:
        head, _, _ = text.partition("ROUTES")
        m = head.replace("FWD:", "").strip()
        if m in ("0", "1"):
            ip_fwd = m == "1"
        _, mid = text.split("ROUTES", 1)
        routes_block, _, if_block = mid.partition("INTERFACES")
        routes_lines = tuple(routes_block.strip().splitlines()[:48])
        iface_lines = tuple(if_block.strip().splitlines()[:64])
    return routes_lines, iface_lines, ip_fwd


def _network_record(net) -> RuntimeNetworkRecord:
    attrs = net.attrs
    ipam = attrs.get("IPAM") or {}
    subnets: list[str] = []
    for cfg in ipam.get("Config") or []:
        sub = cfg.get("Subnet")
        if sub:
            subnets.append(sub)
    labels = attrs.get("Labels") or {}
    nid = attrs.get("Id") or ""
    name = attrs.get("Name") or ""
    if name.startswith("/"):
        name = name[1:]
    return RuntimeNetworkRecord(
        network_id=nid[:64] if nid else "",
        name=name,
        driver=str(attrs.get("Driver") or "bridge"),
        labels=dict(labels),
        scope=attrs.get("Scope"),
        ipam_driver=ipam.get("Driver"),
        subnet_hints=tuple(subnets),
    )


def _network_interface_records(nets: dict) -> tuple[RuntimeNetworkInterfaceRecord, ...]:
    out: list[RuntimeNetworkInterfaceRecord] = []
    keys = sorted(
        k
        for k in (nets or {})
        if isinstance((nets or {}).get(k), dict) and k != _default_bridge_network_name()
    )
    for i, k in enumerate(keys):
        cfg = nets.get(k) or {}
        if not isinstance(cfg, dict):
            continue
        ip = (cfg.get("IPAddress") or "").strip()
        gw = (cfg.get("Gateway") or "").strip() or None
        if not ip:
            continue
        out.append(
            RuntimeNetworkInterfaceRecord(
                docker_network=k,
                interface=f"eth{i}",
                ipv4=ip,
                gateway=gw,
                logical_network=None,
            )
        )
    return tuple(out)


def _container_record(
    ctr,
    topology_id: UUID | None = None,
    labeled_net_ids: frozenset[str] | None = None,
) -> RuntimeContainerRecord:
    attrs = ctr.attrs
    cid = attrs.get("Id") or ""
    st = attrs.get("State") or {}
    cfg = attrs.get("Config") or {}
    labels = cfg.get("Labels") or attrs.get("Labels") or {}
    if not isinstance(labels, dict):
        labels = {}
    node_uuid: UUID | None = None
    raw_nid = labels.get("cns.node_id") if isinstance(labels, dict) else None
    if raw_nid:
        try:
            node_uuid = UUID(str(raw_nid))
        except ValueError:
            node_uuid = None
    if topology_id is None:
        raw_tid = labels.get("cns.topology_id")
        if raw_tid:
            try:
                topology_id = UUID(str(raw_tid))
            except ValueError:
                topology_id = None

    nets = (attrs.get("NetworkSettings") or {}).get("Networks") or {}
    if topology_id is not None and labeled_net_ids is not None:
        ipv4_map = _runtime_ipv4_display_map(nets, topology_id, labeled_net_ids)
    else:
        ipv4_map = _raw_ipv4_map_from_networks(nets)

    ifaces = _network_interface_records(nets)

    name = attrs.get("Name") or ""
    if isinstance(name, str) and name.startswith("/"):
        name = name[1:]
    image_tag = cfg.get("Image") or attrs.get("Image") or getattr(ctr, "image", None)
    if hasattr(image_tag, "tags") and image_tag.tags:
        image_tag = image_tag.tags[0]
    image_s = str(image_tag or "")
    running = bool(st.get("Running"))
    fwd_role = None
    if isinstance(labels, dict):
        raw_role = labels.get("cns.forwarding_role")
        if raw_role is not None:
            fwd_role = str(raw_role)
    routes_lines: tuple[str, ...] = ()
    iface_lines: tuple[str, ...] = ()
    ip_fwd: bool | None = None
    if running:
        routes_lines, iface_lines, ip_fwd = inspect_container_networking(ctr)
    return RuntimeContainerRecord(
        container_id=cid,
        short_id=cid[:12] if len(cid) >= 12 else cid,
        name=name or getattr(ctr, "name", "") or "",
        image=image_s,
        status=getattr(ctr, "status", "") or st.get("Status") or "",
        state_status=st.get("Status"),
        running=running,
        labels=dict(labels),
        node_id=node_uuid,
        ipv4_by_network=dict(ipv4_map),
        created=attrs.get("Created"),
        started_at=st.get("StartedAt"),
        network_interfaces=ifaces,
        routes_lines=routes_lines,
        interface_lines=iface_lines,
        ip_forward_enabled=ip_fwd,
        forwarding_role=fwd_role,
    )


def _docker_stats_to_provider(stats: dict) -> ProviderRuntimeStats:
    cpu_p = _docker_cpu_percent(stats)
    mem_use, mem_lim = _docker_memory_usage(stats)
    rx, tx = _docker_network_totals(stats)
    return ProviderRuntimeStats(
        cpu_percent=cpu_p,
        memory_usage_bytes=mem_use,
        memory_limit_bytes=mem_lim,
        network_rx_bytes=rx,
        network_tx_bytes=tx,
    )


def _docker_cpu_percent(stats: dict) -> float | None:
    try:
        cpu_stats = stats["cpu_stats"]
        precpu = stats["precpu_stats"]
        cpu_delta = cpu_stats["cpu_usage"]["total_usage"] - precpu["cpu_usage"][
            "total_usage"
        ]
        system_delta = cpu_stats["system_cpu_usage"] - precpu["system_cpu_usage"]
        if system_delta <= 0 or cpu_delta < 0:
            return 0.0
        ncpus = len(cpu_stats.get("online_cpus") or [])
        if ncpus == 0:
            ncpus = 1
        return float((cpu_delta / system_delta) * ncpus * 100.0)
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def _docker_memory_usage(stats: dict) -> tuple[int | None, int | None]:
    try:
        mem = stats.get("memory_stats") or {}
        usage = mem.get("usage")
        limit = mem.get("limit")
        u = int(usage) if usage is not None else None
        l = int(limit) if limit is not None else None
        return u, l
    except (TypeError, ValueError):
        return None, None


def _docker_network_totals(stats: dict) -> tuple[int | None, int | None]:
    rx_total = 0
    tx_total = 0
    nets = stats.get("networks") or {}
    if not isinstance(nets, dict):
        return None, None
    any_data = False
    for _iface, data in nets.items():
        if not isinstance(data, dict):
            continue
        rx = data.get("rx_bytes")
        tx = data.get("tx_bytes")
        if rx is not None:
            rx_total += int(rx)
            any_data = True
        if tx is not None:
            tx_total += int(tx)
            any_data = True
    if not any_data:
        return None, None
    return rx_total, tx_total


def _remove_container_if_exists(client: docker.DockerClient, name: str) -> None:
    try:
        c = client.containers.get(name)
        c.stop(timeout=10)
        c.remove()
    except NotFound:
        pass
    except APIError:
        pass


def _remove_network_if_exists(client: docker.DockerClient, name: str) -> None:
    try:
        n = client.networks.get(name)
        # Disconnect endpoints if any remain
        for cid in list(n.attrs.get("Containers") or {}):
            try:
                n.disconnect(cid, force=True)
            except APIError:
                pass
        n.remove()
    except NotFound:
        pass
    except APIError:
        pass


def _remove_all_topology_networks(client: docker.DockerClient, topology_id: UUID) -> None:
    """Remove every CNS-managed bridge labeled for this topology (legacy + segment nets)."""
    tid = str(topology_id)
    try:
        nets = client.networks.list(
            filters={"label": [f"cns.topology_id={tid}", "cns.managed=true"]},
        )
    except APIError:
        return
    for n in nets:
        name = getattr(n, "name", None) or (n.attrs or {}).get("Name") or ""
        if isinstance(name, str) and name.startswith("/"):
            name = name[1:]
        if name:
            _remove_network_if_exists(client, name)


def _rollback_topology_deploy(client: docker.DockerClient, topology_id: UUID) -> None:
    """Best-effort removal of CNS-labeled containers and all topology networks after a failed deploy."""
    tid = str(topology_id)
    try:
        ctrs = client.containers.list(
            all=True,
            filters={"label": [f"cns.topology_id={tid}"]},
        )
    except APIError:
        ctrs = []
    for ctr in ctrs:
        try:
            ctr.stop(timeout=15)
            ctr.remove()
        except (APIError, NotFound):
            pass
    _remove_all_topology_networks(client, topology_id)


def runtime_provider_for_topology(runtime_target: str) -> RuntimeProvider:
    """Fake Docker for tests (``CNS_USE_FAKE_DOCKER``); real engine when ``runtime_target`` is docker."""
    use_fake = os.environ.get("CNS_USE_FAKE_DOCKER", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if use_fake:
        return FakeDockerRuntimeProvider()
    if (runtime_target or "").lower().strip() == "docker":
        return DockerRuntimeProvider()
    return FakeDockerRuntimeProvider()
