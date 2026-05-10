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

        API_VER = getattr(
            __import__("docker.constants", fromlist=["DEFAULT_DOCKER_API_VERSION"]),
            "DEFAULT_DOCKER_API_VERSION",
            "1.43",
        )
        from docker.types import EndpointConfig, NetworkingConfig

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

            ep_cfg = (
                EndpointConfig(API_VER, ipv4_address=pn.ip_address.strip())
                if pn.ip_address
                else EndpointConfig(API_VER)
            )
            net_cfg = NetworkingConfig({net_name: ep_cfg})

            try:
                container = self._client.containers.create(
                    image=image_ref,
                    name=cname,
                    command=cmd,
                    detach=True,
                    labels=_container_labels(plan.topology_id, pn.id),
                    networking_config=net_cfg,
                )
                events.append(
                    (
                        DeploymentEventLevel.INFO,
                        f"Creating container: {cname}",
                    )
                )
                if pn.ip_address:
                    events.append(
                        (
                            DeploymentEventLevel.INFO,
                            f"Assigned IP: {pn.ip_address} -> {cname}",
                        )
                    )
            except APIError as exc:
                if pn.ip_address:
                    events.append(
                        (
                            DeploymentEventLevel.WARNING,
                            f"Create with static IP failed for {cname}, retrying "
                            f"without fixed address: {exc.explanation}",
                        )
                    )
                    fallback_cfg = NetworkingConfig(
                        {net_name: EndpointConfig(API_VER)}
                    )
                    container = self._client.containers.create(
                        image=image_ref,
                        name=cname,
                        command=cmd,
                        detach=True,
                        labels=_container_labels(plan.topology_id, pn.id),
                        networking_config=fallback_cfg,
                    )
                    events.append(
                        (
                            DeploymentEventLevel.INFO,
                            f"Creating container: {cname}",
                        )
                    )
                else:
                    events.append(
                        (
                            DeploymentEventLevel.ERROR,
                            f"Container create failed for {cname}: {exc.explanation}",
                        )
                    )
                    raise

            try:
                container.start()
                events.append(
                    (
                        DeploymentEventLevel.INFO,
                        f"Container started: {cname}",
                    )
                )
            except APIError as exc:
                events.append(
                    (
                        DeploymentEventLevel.ERROR,
                        f"Container start failed for {cname}: {exc.explanation}",
                    )
                )
                raise

        events.append(
            (
                DeploymentEventLevel.INFO,
                "Deployment completed successfully",
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
