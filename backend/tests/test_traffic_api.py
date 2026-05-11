"""Traffic test API tests — fake Docker provider (no daemon)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.models.topology import NodeType
from app.providers.runtime_types import ProviderExecResult

TOPO = {
    "name": "Traffic Lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _two_nodes(client):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    a = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "host-a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    b = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "service-b",
            "node_type": NodeType.HOST.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": a["id"],
            "target_node_id": b["id"],
            "network_name": "lab-net",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )
    return tid, a["id"], b["id"]


def test_ping_traffic_test_creates_record(client):
    tid, na, nb = _two_nodes(client)
    dep = client.post(f"/topologies/{tid}/deploy")
    assert dep.status_code == 201
    did = dep.json()["id"]

    r = client.post(
        f"/topologies/{tid}/traffic-tests/ping",
        json={"source_node_id": na, "target_node_id": nb, "count": 3},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["topology_id"] == tid
    assert body["test_type"] == "ping"
    assert body["status"] == "succeeded"
    assert body["deployment_id"] == did
    assert body["result"] is not None
    assert body["result"]["success"] is True
    assert body["result"]["exit_code"] == 0

    ev = client.get(f"/deployments/{did}/events").json()
    msgs = [e["message"] for e in ev]
    assert any("Traffic test started: ping host-a -> service-b" in m for m in msgs)
    assert any("Traffic test succeeded" in m for m in msgs)


def test_http_traffic_test_creates_record(client):
    tid, na, nb = _two_nodes(client)
    dep = client.post(f"/topologies/{tid}/deploy")
    did = dep.json()["id"]

    r = client.post(
        f"/topologies/{tid}/traffic-tests/http",
        json={
            "source_node_id": na,
            "target_node_id": nb,
            "path": "/",
            "port": 80,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["test_type"] == "http"
    assert body["result"]["success"] is True

    ev = client.get(f"/deployments/{did}/events").json()
    msgs = [e["message"] for e in ev]
    assert any("HTTP traffic test started" in m for m in msgs)
    assert any("HTTP traffic test result recorded" in m for m in msgs)


def test_ping_topology_missing_404(client):
    missing = uuid.uuid4()
    r = client.post(
        f"/topologies/{missing}/traffic-tests/ping",
        json={
            "source_node_id": str(uuid.uuid4()),
            "target_node_id": str(uuid.uuid4()),
            "count": 3,
        },
    )
    assert r.status_code == 404


def test_ping_source_node_missing_404(client):
    tid, _, nb = _two_nodes(client)
    bad = uuid.uuid4()
    r = client.post(
        f"/topologies/{tid}/traffic-tests/ping",
        json={"source_node_id": str(bad), "target_node_id": nb, "count": 2},
    )
    assert r.status_code == 404


def test_ping_target_node_missing_404(client):
    tid, na, _ = _two_nodes(client)
    bad = uuid.uuid4()
    r = client.post(
        f"/topologies/{tid}/traffic-tests/ping",
        json={"source_node_id": na, "target_node_id": str(bad), "count": 2},
    )
    assert r.status_code == 404


def test_list_and_get_traffic_tests(client):
    tid, na, nb = _two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")
    pr = client.post(
        f"/topologies/{tid}/traffic-tests/ping",
        json={"source_node_id": na, "target_node_id": nb, "count": 2},
    )
    ttid = pr.json()["id"]

    lst = client.get(f"/topologies/{tid}/traffic-tests")
    assert lst.status_code == 200
    assert len(lst.json()) >= 1

    one = client.get(f"/traffic-tests/{ttid}")
    assert one.status_code == 200
    assert one.json()["id"] == ttid


def test_http_bad_path_400(client):
    tid, na, nb = _two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")
    r = client.post(
        f"/topologies/{tid}/traffic-tests/http",
        json={
            "source_node_id": na,
            "target_node_id": nb,
            "path": "/bad|inject",
            "port": 80,
        },
    )
    assert r.status_code == 400


def test_ping_exec_failure_records_failed(client, monkeypatch):
    from app.providers.docker_runtime_provider import FakeDockerRuntimeProvider

    tid, na, nb = _two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")

    def bad_exec(self, topology_id, node_id, argv):
        return ProviderExecResult(1, "", "ping failed")

    monkeypatch.setattr(
        FakeDockerRuntimeProvider,
        "exec_in_node_container",
        bad_exec,
    )

    r = client.post(
        f"/topologies/{tid}/traffic-tests/ping",
        json={"source_node_id": na, "target_node_id": nb, "count": 2},
    )
    assert r.status_code == 201
    assert r.json()["status"] == "failed"
    assert r.json()["result"]["success"] is False


def test_ping_mocks_docker_exec_unit():
    """Provider exec is mocked — DockerRuntimeProvider never contacts a real daemon."""
    from app.providers.docker_runtime_provider import DockerRuntimeProvider

    mock_client = MagicMock()
    ctr = MagicMock()
    ctr.id = "deadbeefcafe000011223344556677889900"
    exec_ret = MagicMock()
    exec_ret.exit_code = 0
    exec_ret.output = (b"PING ok\n", b"")
    ctr.exec_run.return_value = exec_ret
    mock_client.containers.list.return_value = [ctr]

    prov = DockerRuntimeProvider(client=mock_client)
    tid = uuid.uuid4()
    nid = uuid.uuid4()

    out = prov.exec_in_node_container(tid, nid, ["ping", "-c", "1", "127.0.0.1"])
    ctr.exec_run.assert_called_once()
    assert out is not None
    assert out.exit_code == 0
