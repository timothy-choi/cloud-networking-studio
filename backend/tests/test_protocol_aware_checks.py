"""Protocol-aware health checks and traffic tests."""

from __future__ import annotations

from app.models.topology import NodeType
from app.services.node_runtime_config import (
    extract_node_runtime_config,
    health_probe_payload_for_node,
    normalize_health_check,
)

TOPO = {
    "name": "proto-lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def test_nginx_health_defaults_http(client):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "web",
            "node_type": NodeType.GENERIC.value,
            "image": "nginx:alpine",
            "config": {"health_check": {"check_type": "http", "port": 80, "path": "/"}},
        },
    )
    node = client.get(f"/topologies/{tid}/nodes").json()[0]
    runtime = extract_node_runtime_config(node["config"])
    probe = health_probe_payload_for_node(image=node["image"], runtime=runtime)
    assert probe["check_type"] == "http"
    assert probe["port"] == 80


def test_ubuntu_runtime_check(client):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "box",
            "node_type": NodeType.HOST.value,
            "image": "ubuntu:22.04",
            "config": {
                "command": "sleep infinity",
                "health_check": {"check_type": "runtime"},
            },
        },
    )
    node = client.get(f"/topologies/{tid}/nodes").json()[0]
    runtime = extract_node_runtime_config(node["config"])
    probe = health_probe_payload_for_node(image=node["image"], runtime=runtime)
    assert probe["check_type"] == "runtime"


def test_redis_tcp_check_normalized():
    hc = normalize_health_check({"check_type": "tcp", "port": 6379}, image="redis:7", primary_port=6379)
    assert hc is not None
    assert hc["check_type"] == "tcp"
    assert hc["port"] == 6379


def test_legacy_path_string_becomes_http():
    hc = normalize_health_check({"path": "/"}, image="nginx:alpine", primary_port=80)
    assert hc is not None
    assert hc["check_type"] == "http"
    assert hc["path"] == "/"


def test_custom_node_defaults_runtime_probe(client):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "custom",
            "node_type": NodeType.HOST.value,
            "image": "ubuntu:22.04",
            "config": {"command": "sleep infinity"},
        },
    )
    node = client.get(f"/topologies/{tid}/nodes").json()[0]
    runtime = extract_node_runtime_config(node["config"])
    probe = health_probe_payload_for_node(image=node["image"], runtime=runtime)
    assert probe["check_type"] == "runtime"


def test_ubuntu_without_http_server_defaults_runtime_not_http():
    runtime = extract_node_runtime_config({"command": "sleep infinity"})
    probe = health_probe_payload_for_node(image="ubuntu:22.04", runtime=runtime)
    assert probe["check_type"] == "runtime"


def test_postgres_inferred_tcp_when_no_explicit_check():
    hc = normalize_health_check(None, image="postgres:16", primary_port=0, has_explicit_ports=False)
    assert hc is not None
    assert hc["check_type"] == "tcp"
    assert hc["port"] == 5432


def test_none_health_check():
    hc = normalize_health_check({"check_type": "none"}, image="alpine:latest", primary_port=80)
    assert hc is not None
    assert hc["check_type"] == "none"
