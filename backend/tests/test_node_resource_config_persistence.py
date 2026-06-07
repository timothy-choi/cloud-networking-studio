"""Tests for node resource config persistence (Feature 63A)."""

from __future__ import annotations

from app.api.topologies import _merge_json_dict
from app.services.node_runtime_config import validate_and_normalize_node_config
from app.services import topology_placement_planner_service as placement_svc
from types import SimpleNamespace
import uuid

from app.models.topology import NodeType


def _node(*, name: str = "web", config: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        node_type=NodeType.HOST,
        image="nginx:latest",
        config=config or {},
    )


def _topology(*nodes) -> SimpleNamespace:
    return SimpleNamespace(nodes=list(nodes), name="lab-topology", id=uuid.uuid4(), project_id=uuid.uuid4())


def test_merge_json_dict_deep_merges_resources():
    base = {
        "editor_position": {"x": 10, "y": 20},
        "health_check": {"path": "/"},
        "resources": {"cpu": 0.5, "memory_mb": 512, "disk_gb": 5, "replicas": 1},
    }
    patch = {"resources": {"cpu": 1.5, "memory_mb": 1024}}
    merged = _merge_json_dict(base, patch)
    assert merged["editor_position"] == {"x": 10, "y": 20}
    assert merged["health_check"] == {"path": "/"}
    assert merged["resources"] == {
        "cpu": 1.5,
        "memory_mb": 1024,
        "disk_gb": 5,
        "replicas": 1,
    }


def test_validate_persists_nested_resources_block():
    cfg = validate_and_normalize_node_config(
        {
            "editor_position": {"x": 1, "y": 2},
            "health_check": {"path": "/"},
            "resources": {"cpu": 1.5, "memory_mb": 1024, "disk_gb": 10, "replicas": 1},
            "exposure": "private",
            "stateful": False,
            "required_ports": [80],
        }
    )
    assert cfg is not None
    assert cfg["resources"] == {
        "cpu": 1.5,
        "memory_mb": 1024,
        "disk_gb": 10.0,
        "replicas": 1,
    }
    assert cfg["exposure"] == "private"
    assert cfg["stateful"] is False
    assert cfg["required_ports"] == [80]
    assert cfg["editor_position"] == {"x": 1, "y": 2}
    assert cfg["health_check"]["path"] == "/"


def test_resolve_prefers_nested_resources_over_stale_top_level():
    from app.services.node_resource_metadata import _resolve_resource_value

    config = {
        "resource_cpu": 0.5,
        "resource_memory_mb": 512,
        "resources": {"cpu": 2, "memory_mb": 2048, "disk_gb": 20, "replicas": 1},
    }
    assert _resolve_resource_value(config, "resource_cpu") == 2
    assert _resolve_resource_value(config, "resource_memory_mb") == 2048


def test_estimate_uses_saved_nested_resources():
    topo = _topology(
        _node(
            config={
                "resources": {"cpu": 2, "memory_mb": 900, "disk_gb": 5, "replicas": 1},
            }
        ),
        _node(
            name="peer",
            config={
                "resources": {"cpu": 2, "memory_mb": 900, "disk_gb": 5, "replicas": 1},
            },
        ),
    )
    plan = placement_svc.build_placement_plan(topo, machine_type="e2-micro")  # type: ignore[arg-type]
    assert plan["recommended_host_count"] >= 2
