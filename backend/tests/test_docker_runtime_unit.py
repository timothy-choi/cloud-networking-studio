"""Unit tests for Docker runtime provider with mocked Docker SDK (no daemon required)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from docker.errors import NotFound

from app.models.deployment import DeploymentEventLevel
from app.providers.docker_runtime_provider import (
    DockerProviderAttachmentError,
    DockerRuntimeProvider,
    _leaf_default_route_apply_script,
    _pick_docker_bridge_gateway_ip,
    _pick_target_ipv4_for_traffic,
    _segment_reserved_endpoint_ips,
    _validate_leaf_default_route,
    _verify_cns_network_attachment,
    topology_network_name,
)
from app.services.deployment_planner import DeploymentPlan, PlanLinkDetail, PlanNode


def _sample_plan() -> DeploymentPlan:
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
                image=None,
                ip_address="10.200.0.10",
                node_type="host",
            ),
            PlanNode(
                id=n2,
                name="svc-b",
                image="nginx:latest",
                ip_address=None,
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
                cidr="10.200.0.0/24",
                gateway=None,
                vlan_tag=None,
                source_ip="10.200.0.10",
                target_ip=None,
            ),
        ),
        segmented_networks=False,
        subnet_cidr="10.200.0.0/24",
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


def test_topology_network_name_stable():
    tid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    short = str(tid).replace("-", "")[:12]
    assert topology_network_name(tid) == f"cns-topology-{short}"


def test_docker_deploy_uses_api_create_container_and_static_endpoint():
    plan = _sample_plan()
    net_name = topology_network_name(plan.topology_id)

    mock_client = MagicMock()
    mock_api = MagicMock()
    mock_client.api = mock_api
    mock_client.containers = MagicMock()
    mock_client.images = MagicMock()
    mock_client.networks = mock_client_networks = MagicMock()

    mock_api.create_endpoint_config.side_effect = lambda **kw: {"EndpointConfig": kw}
    mock_api.create_networking_config.side_effect = lambda d: {"NetworkingConfig": d}
    mock_api.create_container.side_effect = [{"Id": "aaa111"}, {"Id": "bbb222"}]
    mock_api.start = MagicMock()

    ctr_a = _make_container_mock("10.200.0.10", net_name)
    ctr_b = _make_container_mock("10.200.0.11", net_name)

    def get_by_id(cid):
        if cid == "aaa111":
            return ctr_a
        if cid == "bbb222":
            return ctr_b
        raise NotFound("no such container")

    mock_client.containers.get.side_effect = get_by_id

    mock_labeled_net = MagicMock()
    mock_labeled_net.attrs = {"Id": "nid001", "Labels": {"cns.topology_id": str(plan.topology_id)}}
    mock_client_networks.list.return_value = [mock_labeled_net]

    provider = DockerRuntimeProvider(client=mock_client)

    events = provider.deploy(plan).events

    mock_client_networks.create.assert_called_once()
    _args, kwargs = mock_client_networks.create.call_args
    assert kwargs["name"] == net_name
    assert kwargs["driver"] == "bridge"
    assert kwargs["labels"]["cns.project"] == "cloud-networking-studio"

    assert mock_api.create_container.call_count == 2
    for call in mock_api.create_container.call_args_list:
        assert "networking_config" in call.kwargs
        assert call.kwargs.get("network") is None
        assert call.kwargs.get("network_mode") is None

    mock_api.start.assert_any_call("aaa111")
    mock_api.start.assert_any_call("bbb222")

    ep_calls = mock_api.create_endpoint_config.call_args_list
    assert ep_calls[0].kwargs.get("ipv4_address") == "10.200.0.10"
    assert ep_calls[1].kwargs.get("ipv4_address") is None

    nc_calls = mock_api.create_networking_config.call_args_list
    for nc in nc_calls:
        mapping = nc[0][0]
        assert net_name in mapping

    msgs = [m for _, m in events]
    assert any("Docker network created" in m for m in msgs)
    assert any("Verified CNS IP" in m for m in msgs)
    assert any("Deployment completed successfully" in m for m in msgs)
    assert not any("Assigned IP" in m for m in msgs)

    create_idx = next(i for i, m in enumerate(msgs) if "Creating container on" in m)
    verified_idx = next(i for i, m in enumerate(msgs) if "Verified CNS IP" in m)
    assert create_idx < verified_idx


def test_docker_deploy_no_premature_assigned_ip_event():
    """Do not use legacy 'Assigned IP' messaging; attachment is confirmed via inspect first."""
    plan = _sample_plan()
    net_name = topology_network_name(plan.topology_id)

    mock_client = MagicMock()
    mock_client.api.create_endpoint_config.return_value = {}
    mock_client.api.create_networking_config.return_value = {}
    mock_client.api.create_container.side_effect = [{"Id": "a1"}, {"Id": "b1"}]
    mock_client.api.start = MagicMock()
    ca = _make_container_mock("10.200.0.10", net_name)
    cb = _make_container_mock("10.200.0.11", net_name)

    def get_by_id(cid):
        if cid == "a1":
            return ca
        if cid == "b1":
            return cb
        raise NotFound("no such container")

    mock_client.containers.get.side_effect = get_by_id
    mock_client.networks.list.return_value = [
        MagicMock(
            attrs={
                "Id": "nid001",
                "Labels": {"cns.topology_id": str(plan.topology_id)},
            }
        )
    ]

    events = DockerRuntimeProvider(client=mock_client).deploy(plan).events
    msgs = [m for _, m in events]
    assert not any("Assigned IP" in m for m in msgs)
    create_i = next(i for i, m in enumerate(msgs) if "Creating container on" in m)
    attached_i = next(i for i, m in enumerate(msgs) if m.startswith("CNS network attached:"))
    assert create_i < attached_i


def test_verify_cns_network_attachment_requires_network_and_ip():
    with pytest.raises(DockerProviderAttachmentError):
        _verify_cns_network_attachment({}, "cns-topology-abc", None)
    with pytest.raises(DockerProviderAttachmentError):
        _verify_cns_network_attachment(
            {"cns-topology-abc": {"IPAddress": ""}},
            "cns-topology-abc",
            None,
        )
    assert (
        _verify_cns_network_attachment(
            {"cns-topology-abc": {"IPAddress": "10.60.0.20"}},
            "cns-topology-abc",
            "10.60.0.20",
        )
        == "10.60.0.20"
    )


def test_verify_fails_when_inspect_ip_differs_from_requested_static():
    with pytest.raises(DockerProviderAttachmentError, match="10.80.0.2"):
        _verify_cns_network_attachment(
            {"cns-topology-xx": {"IPAddress": "10.80.0.2"}},
            "cns-topology-xx",
            "10.80.0.10",
        )


def test_docker_deploy_create_failure_raises_attachment_error():
    plan = _sample_plan()
    net_name = topology_network_name(plan.topology_id)

    mock_client = MagicMock()
    api_err = __import__("docker.errors", fromlist=["APIError"]).APIError("create boom")
    mock_client.api.create_endpoint_config.return_value = {}
    mock_client.api.create_networking_config.return_value = {}
    mock_client.api.create_container.side_effect = api_err

    provider = DockerRuntimeProvider(client=mock_client)

    with pytest.raises(DockerProviderAttachmentError):
        provider.deploy(plan)


def test_docker_deploy_failure_calls_rollback(monkeypatch):
    plan = _sample_plan()
    mock_client = MagicMock()
    mock_client.api.create_endpoint_config.return_value = {}
    mock_client.api.create_networking_config.return_value = {}
    mock_client.api.create_container.side_effect = RuntimeError("create boom")

    rolled_back: list[UUID] = []

    def capture_rollback(client, topology_id):
        rolled_back.append(topology_id)

    monkeypatch.setattr(
        "app.providers.docker_runtime_provider._rollback_topology_deploy",
        capture_rollback,
    )

    prov = DockerRuntimeProvider(client=mock_client)
    with pytest.raises(RuntimeError, match="create boom"):
        prov.deploy(plan)

    assert rolled_back == [plan.topology_id]


def test_docker_deploy_failure_on_network_create():
    mock_client = MagicMock()
    api_err = __import__("docker.errors", fromlist=["APIError"]).APIError("boom")
    mock_client.networks.create.side_effect = api_err

    provider = DockerRuntimeProvider(client=mock_client)

    with pytest.raises(Exception):
        provider.deploy(_sample_plan())


def test_docker_destroy_removes_labeled_resources():
    mock_client = MagicMock()
    ctr = MagicMock()
    ctr.name = "/cns-node-test"
    mock_client.containers.list.return_value = [ctr]

    mock_net = MagicMock()
    mock_net.name = "cns-topology-aaaaaaaaaaaa"
    mock_net.attrs = {"Name": "/cns-topology-aaaaaaaaaaaa"}
    mock_client.networks.list.return_value = [mock_net]

    net = MagicMock()
    mock_client.networks.get.return_value = net

    provider = DockerRuntimeProvider(client=mock_client)
    tid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    did = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    events = provider.destroy(tid, did)

    ctr.stop.assert_called_once()
    ctr.remove.assert_called_once()
    net.remove.assert_called_once()
    assert any(lvl == DeploymentEventLevel.INFO for lvl, _ in events)


def test_pick_docker_bridge_gateway_avoids_reserved_container_ips():
    assert _pick_docker_bridge_gateway_ip("10.72.0.0/24", {"10.72.0.1", "10.72.0.10"}) == "10.72.0.254"


def test_segment_reserved_endpoint_ips_collects_plan_link_addresses():
    n1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    n2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
    lid = uuid.UUID("33333333-3333-3333-3333-333333333333")
    pl = PlanLinkDetail(
        link_id=lid,
        source_node_id=n1,
        target_node_id=n2,
        source_name="host-a",
        target_name="router-1",
        network_name="net-a",
        cidr="10.72.0.0/24",
        gateway="10.72.0.1",
        vlan_tag=None,
        source_ip="10.72.0.10",
        target_ip="10.72.0.1",
    )
    assert _segment_reserved_endpoint_ips([pl]) == {"10.72.0.10", "10.72.0.1"}


def test_pick_target_ipv4_prefers_shared_docker_network():
    src = {"cns-topology-xxx-net-a": "10.72.0.10"}
    tgt = {
        "cns-topology-xxx-net-a": "10.72.0.1",
        "cns-topology-xxx-net-b": "10.73.0.1",
    }
    assert _pick_target_ipv4_for_traffic(src, tgt) == "10.72.0.1"


def test_pick_target_ipv4_cross_segment_uses_remote_subnet():
    src = {"cns-topology-xxx-net-a": "10.72.0.10"}
    tgt = {"cns-topology-xxx-net-b": "10.73.0.20"}
    assert _pick_target_ipv4_for_traffic(src, tgt) == "10.73.0.20"


def test_pick_target_ipv4_reverse_cross_segment():
    src = {"cns-topology-xxx-net-b": "10.73.0.20"}
    tgt = {"cns-topology-xxx-net-a": "10.72.0.10"}
    assert _pick_target_ipv4_for_traffic(src, tgt) == "10.72.0.10"


def test_pick_target_ipv4_router_to_service_shared_net_b():
    src = {
        "cns-topology-xxx-net-a": "10.72.0.1",
        "cns-topology-xxx-net-b": "10.73.0.1",
    }
    tgt = {"cns-topology-xxx-net-b": "10.73.0.20"}
    assert _pick_target_ipv4_for_traffic(src, tgt) == "10.73.0.20"


def test_validate_leaf_default_route_accepts_ip_route_style():
    text = "default via 10.72.0.1 dev eth0 \n10.72.0.0/24 dev eth0 proto kernel scope link src 10.72.0.10\n"
    ok, msgs = _validate_leaf_default_route(text, "10.72.0.1")
    assert ok and msgs == []


def test_validate_leaf_default_route_rejects_docker254():
    text = "default via 10.72.0.254 dev eth0 \n"
    ok, msgs = _validate_leaf_default_route(text, "10.72.0.1")
    assert not ok
    assert any("10.72.0.254" in m for m in msgs)


def test_validate_leaf_default_route_route_n_style():
    text = """Kernel IP routing table
Destination     Gateway         Genmask         Flags Metric Ref    Use Iface
0.0.0.0         10.73.0.1       0.0.0.0         UG    0      0        0 eth0
"""
    ok, msgs = _validate_leaf_default_route(text, "10.73.0.1")
    assert ok and msgs == []


def test_leaf_default_route_script_substitutes_gateway():
    s = _leaf_default_route_apply_script("10.72.0.1")
    assert "__CNS_GW__" not in s
    assert "GW='10.72.0.1'" in s
    assert "ip -4 route add default via \"$GW\" dev \"$DEV\"" in s


def test_fake_provider_returns_tuple_events():
    from app.providers.docker_runtime_provider import FakeDockerRuntimeProvider

    fp = FakeDockerRuntimeProvider()
    plan = _sample_plan()
    rows = fp.deploy(plan).events
    assert rows and all(isinstance(r, tuple) and len(r) == 2 for r in rows)
