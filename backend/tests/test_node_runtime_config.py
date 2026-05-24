"""Tests for freeform node runtime config extraction."""

from __future__ import annotations

from app.services.node_runtime_config import (
    extract_node_runtime_config,
    primary_port,
    resolve_effective_ports,
    runtime_access_ports_payload,
    runtime_metadata_from_node,
)


def test_extract_empty_config_defaults():
    rc = extract_node_runtime_config(None)
    assert rc.role_label is None
    assert rc.command is None
    assert rc.ports == ()
    assert rc.terminal_enabled is None


def test_extract_custom_fields_from_config():
    rc = extract_node_runtime_config(
        {
            "editor_position": {"x": 1, "y": 2},
            "role_label": "api",
            "command": ["sleep", "infinity"],
            "ports": [{"port": 8080, "target_port": 8080}],
            "env": {"APP": "lab"},
            "terminal_enabled": False,
            "health_check": {"path": "/health", "port": 8080},
            "description": "notes",
        }
    )
    assert rc.role_label == "api"
    assert rc.command == ["sleep", "infinity"]
    assert len(rc.ports) == 1
    assert rc.ports[0].port == 8080
    assert rc.env == {"APP": "lab"}
    assert rc.terminal_enabled is False
    assert rc.health_check == {"path": "/health", "port": 8080}
    assert rc.description == "notes"


def test_command_string_parsed_with_shlex():
    rc = extract_node_runtime_config({"command": "sh -c 'sleep infinity'"})
    assert rc.command == ["sh", "-c", "sleep infinity"]


def test_ports_default_when_missing():
    rc = extract_node_runtime_config({})
    assert primary_port(rc) == 80
    assert resolve_effective_ports(rc)[0].port == 80
    assert runtime_access_ports_payload(rc) == [
        {"port": 80, "target_port": 80, "protocol": "TCP"}
    ]


def test_validate_image_reference_rejects_unsafe():
    import pytest

    from app.services.node_runtime_config import NodeConfigValidationError, validate_image_reference

    with pytest.raises(NodeConfigValidationError):
        validate_image_reference("bad image name!!")


def test_validate_and_normalize_ports():
    from app.services.node_runtime_config import validate_and_normalize_node_config

    out = validate_and_normalize_node_config(
        {"ports": [{"port": 8080, "target_port": 8080, "protocol": "TCP"}]}
    )
    assert out is not None
    assert out["ports"][0]["port"] == 8080


def test_runtime_metadata_includes_image_and_command():
    rc = extract_node_runtime_config({"role_label": "web", "command": "nginx"})
    meta = runtime_metadata_from_node(image="nginx:alpine", ip_address="10.0.0.2", runtime=rc)
    assert meta["role_label"] == "web"
    assert meta["image"] == "nginx:alpine"
    assert meta["command"] == "nginx"
    assert meta["intended_ip"] == "10.0.0.2"


def test_runtime_metadata_includes_env():
    from app.services.node_runtime_config import extract_node_runtime_config, runtime_metadata_from_node

    rc = extract_node_runtime_config({"env": {"LAB": "1"}})
    meta = runtime_metadata_from_node(image="alpine:latest", ip_address=None, runtime=rc)
    assert '"LAB"' in meta.get("env", "")


def test_resolve_deploy_node_image_defaults():
    from app.services.node_runtime_config import resolve_deploy_node_image

    assert resolve_deploy_node_image(None, "generic") == "nginx:alpine"
    assert resolve_deploy_node_image(None, "host") == "alpine:latest"
    assert resolve_deploy_node_image("busybox:latest", "host") == "busybox:latest"


def test_resolve_deploy_node_image_rejects_blank():
    import pytest

    from app.services.node_runtime_config import NodeConfigValidationError, resolve_deploy_node_image

    with pytest.raises(NodeConfigValidationError, match="Node image is required"):
        resolve_deploy_node_image("", "host")
    with pytest.raises(NodeConfigValidationError, match="Node image is required"):
        resolve_deploy_node_image("   ", "host")
