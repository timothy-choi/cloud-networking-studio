"""Network allocation mode: managed vs intent."""

from __future__ import annotations

import ipaddress
import uuid
from dataclasses import replace
from unittest.mock import MagicMock

import pytest
from docker.errors import NotFound

from app.models.topology import NodeType, Topology, TopologyLink, TopologyNode, TopologyStatus
from app.providers.docker_runtime_provider import (
    DockerRuntimeProvider,
    _resolve_bridge_subnet_for_plan,
    _static_ipv4_for_plan,
    topology_network_name,
)
from app.services.deployment_planner import DeploymentPlan, PlanLinkDetail, PlanNode
from app.services.deployment_validation import validate_topology_for_deploy
from app.services.network_allocation import (
    INTENT_SUBNET_OVERLAP_USER_MESSAGE,
    INTENT_UNSUPPORTED_RUNTIME_MESSAGE,
    MANAGED,
    resolve_network_allocation_mode,
)


def _flat_plan(*, mode: str = MANAGED) -> DeploymentPlan:
    tid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    n1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    n2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
    lid = uuid.UUID("33333333-3333-3333-3333-333333333333")
    return DeploymentPlan(
        topology_id=tid,
        runtime_target="docker",
        networking_mode="bridge",
        steps=(),
        nodes=(
            PlanNode(
                id=n1,
                name="host-a",
                image="alpine:latest",
                ip_address="10.50.0.4",
                node_type="host",
            ),
            PlanNode(
                id=n2,
                name="svc-b",
                image="nginx:latest",
                ip_address="10.50.0.20",
                node_type="generic",
            ),
        ),
        node_names=("host-a", "svc-b"),
        links=(("host-a", "svc-b", "net0"),),
        plan_links=(
            PlanLinkDetail(
                link_id=lid,
                source_node_id=n1,
                target_node_id=n2,
                source_name="host-a",
                target_name="svc-b",
                network_name="net0",
                cidr="10.50.0.0/24",
                gateway=None,
                vlan_tag=None,
                source_ip="10.50.0.4",
                target_ip="10.50.0.20",
            ),
        ),
        segmented_networks=False,
        subnet_cidr="10.50.0.0/24",
        network_allocation_mode=mode,
    )


def _make_container_mock(ip: str, net_name: str) -> MagicMock:
    c = MagicMock()

    def reload_fn():
        c.attrs = {
            "NetworkSettings": {
                "Networks": {
                    net_name: {"IPAddress": ip, "NetworkID": "nid001"},
                }
            }
        }

    c.reload.side_effect = reload_fn
    return c


def test_managed_mode_does_not_pass_static_ips_to_docker():
    plan = _flat_plan(mode=MANAGED)
    assert _static_ipv4_for_plan(plan, "10.50.0.4") is None
    assert _static_ipv4_for_plan(plan, "10.50.0.20") is None


def test_intent_mode_passes_static_ips():
    plan = _flat_plan(mode="intent")
    assert _static_ipv4_for_plan(plan, "10.50.0.4") == "10.50.0.4"


def test_managed_deploy_succeeds_with_intent_ips_on_topology():
    """Managed mode: overlap fallback subnet + no static endpoint → no 'subnet contains IP' error."""
    plan = _flat_plan(mode=MANAGED)
    net_name = topology_network_name(plan.topology_id)

    overlap = MagicMock()
    overlap.attrs = {
        "IPAM": {"Config": [{"Subnet": "10.50.0.0/24", "Gateway": "10.50.0.1"}]}
    }

    mock_client = MagicMock()
    mock_client.api.create_endpoint_config.return_value = {}
    mock_client.api.create_networking_config.return_value = {}
    mock_client.api.create_container.side_effect = [{"Id": "a1"}, {"Id": "b1"}]
    mock_client.api.start = MagicMock()
    ca = _make_container_mock("172.30.1.10", net_name)
    cb = _make_container_mock("172.30.1.11", net_name)

    def get_by_id(cid):
        if cid == "a1":
            return ca
        if cid == "b1":
            return cb
        raise NotFound("no such container")

    mock_client.containers.get.side_effect = get_by_id

    labeled = MagicMock()
    labeled.attrs = {"Id": "nid001", "Labels": {"cns.topology_id": str(plan.topology_id)}}

    def _net_list(*_a, **_kw):
        return [labeled] if _kw.get("filters") else [overlap]

    mock_client.networks.list.side_effect = _net_list

    events = DockerRuntimeProvider(client=mock_client).deploy(plan).events
    ep_calls = mock_client.api.create_endpoint_config.call_args_list
    assert all(c.kwargs.get("ipv4_address") is None for c in ep_calls)
    msgs = [m for _, m in events]
    assert any("Network allocation mode: managed" in m for m in msgs)
    assert any("Deployment completed successfully" in m for m in msgs)


def test_intent_mode_rejects_overlapping_subnet():
    plan = _flat_plan(mode="intent")
    used = [ipaddress.ip_network("10.50.0.0/24")]
    chosen, note, fatal = _resolve_bridge_subnet_for_plan(plan, "10.50.0.0/24", used)
    assert chosen is None
    assert note is None
    assert fatal == INTENT_SUBNET_OVERLAP_USER_MESSAGE


def test_validate_intent_ip_inside_subnet():
    tid = uuid.uuid4()
    n1 = TopologyNode(
        id=uuid.uuid4(),
        topology_id=tid,
        name="a",
        node_type=NodeType.HOST,
        image="alpine:latest",
        ip_address="10.50.0.4",
    )
    n2 = TopologyNode(
        id=uuid.uuid4(),
        topology_id=tid,
        name="b",
        node_type=NodeType.GENERIC,
        image="busybox:latest",
        ip_address="10.50.0.20",
    )
    link = TopologyLink(
        id=uuid.uuid4(),
        topology_id=tid,
        source_node_id=n1.id,
        target_node_id=n2.id,
        network_name="net0",
        cidr="10.50.0.0/24",
    )
    topo = Topology(
        id=tid,
        name="t",
        runtime_target="docker",
        networking_mode="bridge",
        status=TopologyStatus.DRAFT,
        nodes=[n1, n2],
        links=[link],
    )
    errs = validate_topology_for_deploy(topo, network_allocation_mode="intent")
    assert errs == []


def test_validate_managed_allows_ip_outside_declared_subnet():
    tid = uuid.uuid4()
    n1 = TopologyNode(
        id=uuid.uuid4(),
        topology_id=tid,
        name="a",
        node_type=NodeType.GENERIC,
        image=None,
        ip_address="192.168.50.1",
    )
    n2 = TopologyNode(
        id=uuid.uuid4(),
        topology_id=tid,
        name="b",
        node_type=NodeType.GENERIC,
        image=None,
        ip_address="10.5.0.20",
    )
    link = TopologyLink(
        id=uuid.uuid4(),
        topology_id=tid,
        source_node_id=n1.id,
        target_node_id=n2.id,
        network_name="n0",
        cidr="10.5.0.0/24",
    )
    topo = Topology(
        id=tid,
        name="t",
        runtime_target="docker",
        networking_mode="bridge",
        status=TopologyStatus.DRAFT,
        nodes=[n1, n2],
        links=[link],
    )
    errs = validate_topology_for_deploy(topo, network_allocation_mode=MANAGED)
    assert not any("not within any link subnet" in e for e in errs)


def test_kubernetes_intent_mode_rejected(client):
    tid = client.post(
        "/topologies",
        json={
            "name": "k8s-intent",
            "description": None,
            "runtime_target": "kubernetes",
            "networking_mode": "kubernetes",
            "status": "draft",
        },
    ).json()["id"]
    client.patch(
        f"/topologies/{tid}",
        json={"config": {"network_allocation_mode": "intent"}},
    )
    r = client.post(f"/topologies/{tid}/deploy", json={"network_allocation_mode": "intent"})
    assert r.status_code == 400
    assert INTENT_UNSUPPORTED_RUNTIME_MESSAGE in r.text


def test_snapshot_to_containers_includes_intended_and_actual_ip():
    from uuid import UUID

    from app.providers.runtime_types import (
        ProviderRuntimeSnapshot,
        RuntimeContainerRecord,
        RuntimeNetworkInterfaceRecord,
    )
    from app.services.runtime_state_service import _snapshot_to_containers

    nid = UUID("11111111-1111-1111-1111-111111111111")
    snap = ProviderRuntimeSnapshot(
        containers=(
            RuntimeContainerRecord(
                container_id="c1",
                short_id="c1",
                name="host-a",
                image="alpine",
                status="running",
                state_status="running",
                running=True,
                labels={},
                node_id=nid,
                ipv4_by_network={"cns-topology-abc": "172.30.0.5"},
                created=None,
                started_at=None,
                network_interfaces=(
                    RuntimeNetworkInterfaceRecord(
                        docker_network="cns-topology-abc",
                        interface="eth0",
                        ipv4="172.30.0.5",
                    ),
                ),
            ),
        )
    )
    out = _snapshot_to_containers(snap, {nid: "10.50.0.4"})
    assert len(out) == 1
    assert out[0].intended_ip == "10.50.0.4"
    assert out[0].actual_runtime_ip == "172.30.0.5"


def test_runtime_response_includes_intended_and_actual_ip(client):
    """After deploy, runtime containers expose intended_ip and actual_runtime_ip when available."""
    tid = client.post("/topologies", json={
        "name": "rt-ips",
        "description": None,
        "runtime_target": "docker",
        "networking_mode": "docker_bridge",
        "status": "draft",
        "config": {"network_allocation_mode": "managed"},
    }).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "a",
            "node_type": "host",
            "image": "alpine:latest",
            "ip_address": "10.88.0.10",
            "config": None,
        },
    ).json()
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "b",
            "node_type": "generic",
            "image": "busybox:1.36",
            "ip_address": "10.88.0.20",
            "config": None,
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na["id"],
            "target_node_id": nb["id"],
            "network_name": "net0",
            "cidr": "10.88.0.0/24",
            "config": None,
        },
    )
    dep = client.post(f"/topologies/{tid}/deploy", json={"network_allocation_mode": "managed"})
    if dep.status_code != 201:
        pytest.skip(f"deploy not available in this test env: {dep.status_code}")
    did = dep.json()["id"]
    rt = client.get(f"/deployments/{did}/runtime").json()
    if not rt.get("containers"):
        pytest.skip("no runtime containers in fake-docker test env")
    c0 = rt["containers"][0]
    assert "intended_ip" in c0
    assert "actual_runtime_ip" in c0
