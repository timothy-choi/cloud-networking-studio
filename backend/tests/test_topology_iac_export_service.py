"""Unit tests for topology IaC export generation."""

from __future__ import annotations

from uuid import uuid4

from app.services.node_runtime_config import extract_node_runtime_config
from app.services.topology_iac_export_service import (
    DOCKER_COMPOSE_FILENAME,
    KUBERNETES_FILENAME,
    ExportLink,
    ExportNode,
    TopologyExportBundle,
    build_ansible_zip,
    build_iac_archive,
    build_terraform_zip,
    generate_docker_compose,
    generate_kubernetes_yaml,
    validate_topology_export,
)


def _sample_bundle() -> TopologyExportBundle:
    nid = uuid4()
    runtime = extract_node_runtime_config(
        {
            "role_label": "web",
            "command": "nginx -g 'daemon off;'",
            "ports": [{"port": 8080, "target_port": 80}],
            "env": {"LAB": "1"},
            "health_check": {"check_type": "http", "port": 80, "path": "/"},
        }
    )
    node = ExportNode(
        id=nid,
        name="web",
        node_type="generic",
        image="nginx:alpine",
        ip_address=None,
        service_name="web-abc12345",
        runtime=runtime,
        health_check=runtime.health_check,
    )
    link = ExportLink(
        id=uuid4(),
        source_name="web",
        target_name="web",
        network_name="lab-net",
        cidr="10.0.0.0/24",
        gateway="10.0.0.1",
        vlan_tag=None,
    )
    tid = uuid4()
    return TopologyExportBundle(
        topology_id=tid,
        topology_name="lab",
        description="test",
        runtime_target="docker",
        networking_mode="docker_bridge",
        nodes=(node,),
        links=(link,),
        networks=("lab-net",),
    )


def test_docker_compose_export_is_yaml_like():
    text = generate_docker_compose(_sample_bundle())
    assert "version:" not in text.split("services:", 1)[0]
    assert "services:" in text
    assert "nginx:alpine" in text
    assert "lab-net" in text
    assert "CNS does not execute" in text


def test_kubernetes_export_is_yaml_like():
    text = generate_kubernetes_yaml(_sample_bundle())
    assert "kind: Deployment" in text
    assert "kind: Service" in text
    assert "nginx:alpine" in text
    assert "health_check" in text


def test_terraform_zip_has_expected_files():
    payload = build_terraform_zip(_sample_bundle())
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = set(zf.namelist())
    assert names == {"main.tf", "variables.tf", "outputs.tf", "README.md"}


def test_ansible_zip_has_expected_files():
    payload = build_ansible_zip(_sample_bundle())
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = set(zf.namelist())
    assert names == {"inventory.ini", "playbook.yml", "README.md"}


def test_archive_contains_all_artifacts():
    payload = build_iac_archive(_sample_bundle())
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = set(zf.namelist())
    assert DOCKER_COMPOSE_FILENAME in names
    assert KUBERNETES_FILENAME in names
    assert "terraform/main.tf" in names
    assert "ansible/playbook.yml" in names


def test_validate_warnings_incomplete_node():
    nid = uuid4()
    runtime = extract_node_runtime_config({})
    node = ExportNode(
        id=nid,
        name="blank",
        node_type="host",
        image=None,
        ip_address=None,
        service_name="blank-abc",
        runtime=runtime,
        health_check=None,
    )
    bundle = TopologyExportBundle(
        topology_id=uuid4(),
        topology_name="t",
        description=None,
        runtime_target="docker",
        networking_mode="docker_bridge",
        nodes=(node,),
        links=(),
        networks=("cns-network",),
    )
    warnings, _unsupported, todos = validate_topology_export(bundle)
    codes = {w["code"] for w in warnings}
    assert "missing_image" in codes
    assert "no_ports_configured" in codes
    assert any("skeleton" in t.lower() for t in todos)
