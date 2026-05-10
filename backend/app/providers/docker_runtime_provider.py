"""Docker runtime — simulated (fake) and real Docker SDK backends."""

from __future__ import annotations

import ipaddress
import os
import re
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
    RuntimeNetworkRecord,
)
from app.services.deployment_planner import DeploymentPlan


def topology_network_name(topology_id: UUID) -> str:
    short = str(topology_id).replace("-", "")[:12]
    return f"cns-topology-{short}"


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


def _container_labels(topology_id: UUID, node_id: UUID) -> dict[str, str]:
    labels = _base_labels(topology_id)
    labels["cns.node_id"] = str(node_id)
    return labels


def _default_command(image_ref: str) -> list[str] | None:
    img = image_ref.lower()
    if "nginx" in img:
        return None
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
            (DeploymentEventLevel.INFO, "Virtual network creation scheduled"),
        ]
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

    def resolve_node_ipv4(self, topology_id: UUID, node_id: UUID) -> str | None:
        _ = (topology_id, node_id)
        return "10.200.0.10"


class DockerRuntimeProvider(RuntimeProvider):
    """Real Docker engine orchestration for bridge networks + containers."""

    def __init__(self, client: docker.DockerClient | None = None) -> None:
        self._client = client or docker.from_env()

    def deploy(self, plan: DeploymentPlan) -> list[ProviderEvent]:
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
                    _container_labels(plan.topology_id, pn.id),
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

        net_name = topology_network_name(topology_id)
        try:
            net = self._client.networks.get(net_name)
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Removing Docker network: {net_name}",
                )
            )
            net.remove()
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Docker network removed: {net_name}",
                )
            )
        except NotFound:
            events.append(
                (
                    DeploymentEventLevel.INFO,
                    f"Docker network not found (already removed): {net_name}",
                )
            )
        except APIError as exc:
            events.append(
                (
                    DeploymentEventLevel.WARNING,
                    f"Docker network removal issue: {exc.explanation}",
                )
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
                _disconnect_default_bridge(self._client, c.id)
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

    def resolve_node_ipv4(self, topology_id: UUID, node_id: UUID) -> str | None:
        ctr = _find_managed_container(self._client, topology_id, node_id)
        if ctr is None:
            return None
        try:
            ctr.reload()
        except APIError:
            pass
        labeled_ids = _labeled_topology_network_ids(self._client, topology_id)
        nets = (ctr.attrs.get("NetworkSettings") or {}).get("Networks") or {}
        return _pick_cns_ipv4(nets, topology_id, labeled_ids)


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

    name = attrs.get("Name") or ""
    if isinstance(name, str) and name.startswith("/"):
        name = name[1:]
    image_tag = cfg.get("Image") or attrs.get("Image") or getattr(ctr, "image", None)
    if hasattr(image_tag, "tags") and image_tag.tags:
        image_tag = image_tag.tags[0]
    image_s = str(image_tag or "")
    running = bool(st.get("Running"))
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


def _rollback_topology_deploy(client: docker.DockerClient, topology_id: UUID) -> None:
    """Best-effort removal of CNS-labeled containers and topology network after a failed deploy."""
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
    _remove_network_if_exists(client, topology_network_name(topology_id))


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
