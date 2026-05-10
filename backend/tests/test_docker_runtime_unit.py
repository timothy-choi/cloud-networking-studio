"""Unit tests for Docker runtime provider with mocked Docker SDK (no daemon required)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.models.deployment import DeploymentEventLevel
from app.providers.docker_runtime_provider import DockerRuntimeProvider, topology_network_name
from app.services.deployment_planner import DeploymentPlan, PlanNode


def _sample_plan() -> DeploymentPlan:
    tid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    n1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    n2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
    return DeploymentPlan(
        topology_id=tid,
        runtime_target="docker",
        networking_mode="bridge",
        steps=(),
        nodes=(
            PlanNode(id=n1, name="host-a", image=None, ip_address="10.200.0.10"),
            PlanNode(id=n2, name="svc-b", image="nginx:latest", ip_address=None),
        ),
        node_names=("host-a", "svc-b"),
        links=(("host-a", "svc-b", "net0"),),
        subnet_cidr="10.200.0.0/24",
    )


def test_topology_network_name_stable():
    tid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    short = str(tid).replace("-", "")[:12]
    assert topology_network_name(tid) == f"cns-topology-{short}"


def test_docker_deploy_creates_network_and_containers():
    mock_client = MagicMock()
    mock_net_api = MagicMock()
    mock_ctr_api = MagicMock()

    mock_client.networks = mock_net_api
    mock_client.containers = mock_ctr_api
    mock_client.images = MagicMock()

    ctr_obj = MagicMock()
    mock_ctr_api.create.return_value = ctr_obj

    provider = DockerRuntimeProvider(client=mock_client)
    plan = _sample_plan()

    events = provider.deploy(plan)

    mock_net_api.create.assert_called_once()
    _args, kwargs = mock_net_api.create.call_args
    assert kwargs["name"] == topology_network_name(plan.topology_id)
    assert kwargs["driver"] == "bridge"
    assert kwargs["labels"]["cns.project"] == "cloud-networking-studio"

    assert mock_ctr_api.create.call_count == 2
    ctr_obj.start.assert_called()

    msgs = [m for _, m in events]
    assert any("Docker network created" in m for m in msgs)
    assert any("Deployment completed successfully" in m for m in msgs)


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


def test_fake_provider_returns_tuple_events():
    from app.providers.docker_runtime_provider import FakeDockerRuntimeProvider

    fp = FakeDockerRuntimeProvider()
    plan = _sample_plan()
    rows = fp.deploy(plan)
    assert rows and all(isinstance(r, tuple) and len(r) == 2 for r in rows)
