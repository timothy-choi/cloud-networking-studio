"""Runtime resource persistence after deploy (Go runner + Python Docker executor)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import httpx
import pytest

from app.models.deployment import DeploymentEventLevel
from app.models.topology import NodeType
from app.runtime.go_runner_client import (
    GoRunnerClient,
    _extract_runtime_access_from_response,
)
from app.services.deployment_planner import DeploymentPlan, PlanLinkDetail, PlanNode
from app.services.deployment_runtime_resource_service import (
    list_runtime_resources,
    replace_runtime_resources_from_payload,
)
TOPO_BODY = {
    "name": "Runtime Persist Lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _minimal_plan(*, with_intent_ips: bool = True) -> DeploymentPlan:
    tid = uuid.uuid4()
    nid = uuid.uuid4()
    lid = uuid.uuid4()
    did = uuid.uuid4()
    ip = "10.50.0.4" if with_intent_ips else None
    node = PlanNode(
        id=nid,
        name="web",
        image="alpine:latest",
        ip_address=ip,
        node_type="host",
    )
    pl = PlanLinkDetail(
        link_id=lid,
        source_node_id=nid,
        target_node_id=nid,
        source_name="web",
        target_name="web",
        network_name="net0",
        cidr="10.50.0.0/24",
        gateway=None,
        vlan_tag=None,
        source_ip=ip,
        target_ip=ip,
    )
    return DeploymentPlan(
        topology_id=tid,
        runtime_target="docker",
        networking_mode="docker_bridge",
        steps=("validate_topology",),
        nodes=(node,),
        node_names=("web",),
        links=(("web", "web", "net0"),),
        plan_links=(pl,),
        segmented_networks=False,
        subnet_cidr="10.50.0.0/24",
        deployment_id=did,
        project_id=None,
        requested_by_user_id=None,
        network_allocation_mode="managed",
    )


def test_extract_runtime_access_merges_top_level_provider():
    data = {
        "status": "succeeded",
        "runtime_provider": "docker",
        "runtime_access": {
            "deployment_id": "d1",
            "resources": [{"type": "service", "name": "api", "runtime_name": "cns-node-x"}],
        },
    }
    ra = _extract_runtime_access_from_response(data)
    assert ra is not None
    assert ra["runtime_provider"] == "docker"
    assert len(ra["resources"]) == 1


def test_post_deployment_managed_mode_returns_resources_with_intent_ip_metadata():
    plan = _minimal_plan(with_intent_ips=True)
    nid = str(plan.nodes[0].id)
    ra_payload = {
        "deployment_id": str(plan.deployment_id),
        "topology_id": str(plan.topology_id),
        "status": "running",
        "runtime_provider": "docker",
        "namespace_or_network": "cns-topology-abc",
        "resources": [
            {
                "type": "service",
                "service_id": nid,
                "name": "web",
                "runtime_name": "cns-node-abc-web",
                "internal_url": "http://cns-node-abc-web:80",
                "ports": [{"port": 80, "target_port": 80, "protocol": "TCP"}],
                "metadata": {
                    "intended_ip": "10.50.0.4",
                    "actual_runtime_ip": "172.30.0.8",
                },
            }
        ],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "runtime_provider": "docker",
                "events": [{"level": "info", "message": "ok"}],
                "runtime_access": ra_payload,
            },
        )

    c = GoRunnerClient("http://runner:8090", transport=httpx.MockTransport(handler))
    _events, ra = c.post_deployment(plan)
    assert ra is not None
    svcs = [r for r in ra["resources"] if r.get("type") == "service"]
    assert len(svcs) == 1
    assert svcs[0]["metadata"]["intended_ip"] == "10.50.0.4"
    assert svcs[0]["metadata"]["actual_runtime_ip"] == "172.30.0.8"


def test_persist_resources_without_static_ip(client):
    from uuid import UUID

    from app.db.session import SessionLocal

    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "solo",
            "node_type": NodeType.HOST.value,
            "image": "alpine:latest",
            "ip_address": None,
            "config": None,
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na["id"],
            "target_node_id": na["id"],
            "network_name": "net0",
            "cidr": "10.10.0.0/24",
            "config": None,
        },
    )
    dep_id = UUID(client.post(f"/topologies/{tid}/deploy").json()["id"])
    payload = {
        "deployment_id": str(dep_id),
        "topology_id": str(tid),
        "status": "running",
        "runtime_provider": "docker",
        "namespace_or_network": "cns-topology-test",
        "resources": [
            {
                "type": "service",
                "service_id": str(uuid.uuid4()),
                "name": "app",
                "runtime_name": "cns-node-abc-app",
                "internal_url": "http://cns-node-abc-app:80",
                "ports": [{"port": 80, "target_port": 80, "protocol": "TCP"}],
                "metadata": {"actual_runtime_ip": "172.30.0.12"},
            }
        ],
    }
    with SessionLocal() as db:
        n = replace_runtime_resources_from_payload(db, dep_id, payload)
        db.commit()
        rows = list_runtime_resources(db, dep_id)
    assert n == 1
    assert len(rows) == 1
    assert rows[0].resource_type == "service"
    assert rows[0].access_metadata.get("actual_runtime_ip") == "172.30.0.12"
    assert rows[0].access_metadata.get("intended_ip") is None


def test_topology_deploy_persists_fake_runtime_services(client):
    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "a",
            "node_type": NodeType.HOST.value,
            "image": "alpine:latest",
            "ip_address": "10.88.0.10",
            "config": None,
        },
    ).json()
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "b",
            "node_type": NodeType.GENERIC.value,
            "image": "busybox:1.36",
            "ip_address": None,
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
    assert dep.status_code == 201, dep.text
    did = dep.json()["id"]
    svcs = client.get(f"/deployments/{did}/runtime/services").json()["services"]
    assert len(svcs) >= 1
    assert svcs[0].get("internal_url")


def test_go_runner_deploy_persists_services_api(client, monkeypatch):
    """When executor=go, mocked runner runtime_access rows appear on runtime/services."""
    from app.providers.docker_runtime_provider import FakeDockerRuntimeProvider
    from app.providers.go_hybrid_runtime_provider import GoHybridDockerRuntimeProvider

    mock_runner = MagicMock()

    def fake_provider(_runtime_target: str):
        return GoHybridDockerRuntimeProvider(FakeDockerRuntimeProvider(), mock_runner)

    monkeypatch.setattr(
        "app.services.topology_deploy_execution.runtime_provider_for_topology",
        fake_provider,
    )

    tid = client.post("/topologies", json=TOPO_BODY).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "svc-a",
            "node_type": NodeType.HOST.value,
            "image": "alpine:latest",
            "ip_address": "10.50.0.4",
            "config": None,
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": na["id"],
            "target_node_id": na["id"],
            "network_name": "net0",
            "cidr": "10.50.0.0/24",
            "config": None,
        },
    )

    captured: dict = {}

    def fake_post(plan: DeploymentPlan):
        nid = str(plan.nodes[0].id)
        ra = {
            "deployment_id": str(plan.deployment_id),
            "topology_id": str(plan.topology_id),
            "status": "running",
            "runtime_provider": "docker",
            "namespace_or_network": "cns-topology-x",
            "resources": [
                {
                    "type": "service",
                    "service_id": nid,
                    "name": "svc-a",
                    "runtime_name": "cns-node-x-svc-a",
                    "internal_url": "http://cns-node-x-svc-a:80",
                    "ports": [{"port": 80, "target_port": 80, "protocol": "TCP"}],
                    "metadata": {"intended_ip": "10.50.0.4", "actual_runtime_ip": "172.30.0.5"},
                }
            ],
        }
        captured["ra"] = ra
        return [(DeploymentEventLevel.INFO, "runner ok")], ra

    mock_runner.post_deployment.side_effect = fake_post

    dep = client.post(f"/topologies/{tid}/deploy", json={"network_allocation_mode": "managed"})
    assert dep.status_code == 201, dep.text
    did = dep.json()["id"]
    assert captured.get("ra")
    mock_runner.post_deployment.assert_called_once()
    svcs = client.get(f"/deployments/{did}/runtime/services").json()["services"]
    assert len(svcs) == 1
    assert svcs[0]["name"] == "svc-a"
    assert svcs[0]["metadata"].get("actual_runtime_ip") == "172.30.0.5"
