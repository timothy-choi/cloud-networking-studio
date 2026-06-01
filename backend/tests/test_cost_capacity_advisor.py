"""Tests for cost and capacity advisor (Step 62)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.models.topology import NodeType
from app.services import cost_capacity_advisor_service as cost_capacity_svc


def _sample_plan(machine_type: str = "e2-micro") -> dict:
    return {
        "provider": "gcp",
        "recommended_machine_type": machine_type,
        "recommended_host_count": 1,
        "hosts": [
            {
                "host_index": 1,
                "machine_type": machine_type,
                "cpu_used": 0.75,
                "cpu_capacity": 2,
                "memory_used_mb": 768,
                "memory_capacity_mb": 1024,
                "disk_used_gb": 10,
                "disk_capacity_gb": 30,
                "assigned_nodes": ["cli-edge", "svc-origin"],
            }
        ],
    }


def test_gcp_cost_estimate_uses_static_table_and_disk_allocation():
    estimate = cost_capacity_svc.estimate_monthly_cost(
        provider="gcp",
        machine_type="e2-micro",
        host_count=1,
        disk_allocation_gb=30,
    )
    assert estimate == {
        "provider": "gcp",
        "machine_type": "e2-micro",
        "host_count": 1,
        "estimated_monthly_cost": {"low": 8, "high": 12, "currency": "USD"},
    }


def test_aws_cost_estimate_uses_static_table():
    estimate = cost_capacity_svc.estimate_monthly_cost(
        provider="aws",
        machine_type="t3.small",
        host_count=2,
        disk_allocation_gb=60,
    )
    assert estimate["provider"] == "aws"
    assert estimate["machine_type"] == "t3.small"
    assert estimate["host_count"] == 2
    assert estimate["estimated_monthly_cost"]["currency"] == "USD"
    assert estimate["estimated_monthly_cost"]["low"] > 0


def test_capacity_and_headroom_calculations():
    plan = _sample_plan()
    assert cost_capacity_svc.analyze_capacity(plan) == {
        "cpu_utilization_percent": 38,
        "memory_utilization_percent": 75,
        "disk_utilization_percent": 33,
    }
    assert cost_capacity_svc.analyze_headroom(plan) == {
        "cpu_headroom_percent": 62,
        "memory_headroom_percent": 25,
        "disk_headroom_percent": 67,
        "remaining_cpu": 1.25,
        "remaining_memory_mb": 256,
        "remaining_disk_gb": 20,
    }


def test_scaling_risk_classification_and_reasons():
    assert cost_capacity_svc.assess_scaling_risk(
        {
            "cpu_utilization_percent": 38,
            "memory_utilization_percent": 75,
            "disk_utilization_percent": 33,
        }
    ) == {
        "scaling_risk": "MEDIUM",
        "reasons": ["Memory utilization exceeds 75%"],
    }
    assert cost_capacity_svc.assess_scaling_risk(
        {
            "cpu_utilization_percent": 90,
            "memory_utilization_percent": 40,
            "disk_utilization_percent": 20,
        }
    )["scaling_risk"] == "HIGH"
    assert cost_capacity_svc.assess_scaling_risk(
        {
            "cpu_utilization_percent": 20,
            "memory_utilization_percent": 40,
            "disk_utilization_percent": 20,
        }
    )["scaling_risk"] == "LOW"


def test_alternative_recommendations():
    analysis = cost_capacity_svc.build_cost_capacity_analysis(_sample_plan())
    assert analysis["alternatives"] == {
        "cheaper_alternative": None,
        "safer_alternative": "e2-small",
    }

    low_usage_plan = _sample_plan("e2-small")
    low_usage_plan["hosts"][0]["memory_capacity_mb"] = 2048
    low_usage_plan["hosts"][0]["memory_used_mb"] = 512
    cheaper = cost_capacity_svc.build_cost_capacity_analysis(low_usage_plan)
    assert cheaper["alternatives"]["cheaper_alternative"] == "e2-micro"
    assert cheaper["alternatives"]["safer_alternative"] is None


def test_cost_capacity_analysis_api(client_strict, engine_db):
    email = f"costcap{uuid.uuid4().hex[:8]}@example.com"
    reg = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "CostCap"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    project_id = client_strict.get("/projects", headers=headers).json()[0]["id"]
    topo = client_strict.post(
        "/topologies",
        headers=headers,
        json={
            "name": "cost-capacity-lab",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
            "project_id": project_id,
        },
    )
    assert topo.status_code == 201, topo.text
    topo_id = topo.json()["id"]
    node = client_strict.post(
        f"/topologies/{topo_id}/nodes",
        headers=headers,
        json={
            "name": "app",
            "node_type": "host",
            "image": "nginx",
            "config": {"resource_cpu": 0.75, "resource_memory_mb": 768, "resource_disk_gb": 10, "replicas": 1},
        },
    )
    assert node.status_code == 201, node.text

    resp = client_strict.get(f"/topologies/{topo_id}/cost-capacity-analysis", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cost_estimate"]["provider"] == "gcp"
    assert body["cost_estimate"]["estimated_monthly_cost"]["currency"] == "USD"
    assert "cpu_utilization_percent" in body["capacity"]
    assert "memory_headroom_percent" in body["headroom"]
    assert body["scaling_risk"]["scaling_risk"] in {"LOW", "MEDIUM", "HIGH"}


def test_ai_context_includes_cost_capacity_analysis():
    from app.services import ai_infrastructure_advisor_service as advisor_svc

    topology = SimpleNamespace(
        id=uuid.uuid4(),
        name="ai-cost-context",
        project_id=uuid.uuid4(),
        nodes=[
            SimpleNamespace(
                id=uuid.uuid4(),
                name="app",
                node_type=NodeType.HOST,
                image="nginx",
                config={"resource_cpu": 0.75, "resource_memory_mb": 768, "resource_disk_gb": 10},
            )
        ],
    )

    context = advisor_svc.build_advisor_context(topology)  # type: ignore[arg-type]
    cost_capacity = context["cost_capacity_analysis"]
    assert cost_capacity["cost_estimate"]["estimated_monthly_cost"]["currency"] == "USD"
    assert "memory_utilization_percent" in cost_capacity["capacity"]
    assert cost_capacity["scaling_risk"]["scaling_risk"] in {"LOW", "MEDIUM", "HIGH"}
