"""Failure injection API tests — fake Docker only (no daemon)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.models.failure_injection import FailureInjectionFailureType, FailureInjectionStatus
from app.models.topology import NodeType
from app.providers.docker_runtime_provider import FakeDockerRuntimeProvider

TOPO = {
    "name": "Failure Lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _topology_and_two_nodes(client):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "svc-a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "svc-b",
            "node_type": NodeType.HOST.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()
    return tid, uuid.UUID(na["id"]), uuid.UUID(nb["id"])


def test_stop_node_creates_record(client):
    tid, na, nb = _topology_and_two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")

    r = client.post(
        f"/topologies/{tid}/failures/stop-node",
        json={"target_node_id": str(nb), "description": "chaos stop"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["topology_id"] == tid
    assert body["failure_type"] == FailureInjectionFailureType.STOP_CONTAINER.value
    assert body["status"] == FailureInjectionStatus.SUCCEEDED.value
    assert body["target_node_id"] == str(nb)
    assert body["description"] == "chaos stop"


def test_restart_node_creates_record(client):
    tid, na, nb = _topology_and_two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")

    r = client.post(
        f"/topologies/{tid}/failures/restart-node",
        json={"target_node_id": str(na)},
    )
    assert r.status_code == 201
    assert r.json()["failure_type"] == FailureInjectionFailureType.RESTART_CONTAINER.value
    assert r.json()["status"] == FailureInjectionStatus.SUCCEEDED.value


def test_kill_node_creates_record(client):
    tid, na, nb = _topology_and_two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")

    r = client.post(
        f"/topologies/{tid}/failures/kill-node",
        json={"target_node_id": str(nb)},
    )
    assert r.status_code == 201
    assert r.json()["failure_type"] == FailureInjectionFailureType.KILL_CONTAINER.value


def test_missing_topology_returns_404(client):
    missing = uuid.uuid4()
    r = client.post(
        f"/topologies/{missing}/failures/stop-node",
        json={"target_node_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


def test_missing_node_returns_404(client):
    tid, na, _ = _topology_and_two_nodes(client)
    bad = uuid.uuid4()
    r = client.post(
        f"/topologies/{tid}/failures/stop-node",
        json={"target_node_id": str(bad)},
    )
    assert r.status_code == 404


def test_missing_runtime_container_returns_failed_record(client, monkeypatch):
    tid, na, nb = _topology_and_two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")

    monkeypatch.setattr(
        FakeDockerRuntimeProvider,
        "find_container_id_for_node",
        lambda self, topology_id, node_id: None,
    )

    r = client.post(
        f"/topologies/{tid}/failures/stop-node",
        json={"target_node_id": str(nb)},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == FailureInjectionStatus.FAILED.value
    assert body["result_message"] is not None
    assert "runtime container not found" in body["result_message"].lower()


def test_list_failures_for_topology(client):
    tid, na, nb = _topology_and_two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")
    client.post(
        f"/topologies/{tid}/failures/stop-node",
        json={"target_node_id": str(na)},
    )

    lst = client.get(f"/topologies/{tid}/failures")
    assert lst.status_code == 200
    rows = lst.json()
    assert len(rows) >= 1
    assert rows[0]["topology_id"] == tid


def test_get_failure_by_id(client):
    tid, na, nb = _topology_and_two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")
    pr = client.post(
        f"/topologies/{tid}/failures/kill-node",
        json={"target_node_id": str(nb)},
    )
    fid = pr.json()["id"]

    one = client.get(f"/failures/{fid}")
    assert one.status_code == 200
    assert one.json()["id"] == fid


def test_provider_methods_invoked(client, monkeypatch):
    tid, na, nb = _topology_and_two_nodes(client)
    client.post(f"/topologies/{tid}/deploy")

    calls: list[str] = []

    def stop(self, topology_id, node_id):
        calls.append("stop")

    def restart(self, topology_id, node_id):
        calls.append("restart")

    def kill(self, topology_id, node_id):
        calls.append("kill")

    monkeypatch.setattr(FakeDockerRuntimeProvider, "stop_node_container", stop)
    monkeypatch.setattr(FakeDockerRuntimeProvider, "restart_node_container", restart)
    monkeypatch.setattr(FakeDockerRuntimeProvider, "kill_node_container", kill)

    client.post(f"/topologies/{tid}/failures/stop-node", json={"target_node_id": str(na)})
    client.post(
        f"/topologies/{tid}/failures/restart-node",
        json={"target_node_id": str(nb)},
    )
    client.post(f"/topologies/{tid}/failures/kill-node", json={"target_node_id": str(na)})

    assert calls == ["stop", "restart", "kill"]


def test_docker_provider_failure_methods_call_engine():
    """Direct DockerRuntimeProvider unit test with mocked SDK (no daemon)."""
    from docker.errors import APIError

    from app.providers.docker_runtime_provider import DockerRuntimeProvider

    mock_client = MagicMock()
    mock_ctr = MagicMock()
    mock_client.containers.list.return_value = [mock_ctr]

    prov = DockerRuntimeProvider(client=mock_client)
    tid = uuid.uuid4()
    nid = uuid.uuid4()

    prov.stop_node_container(tid, nid)
    mock_ctr.stop.assert_called_once()

    prov.restart_node_container(tid, nid)
    mock_ctr.restart.assert_called_once()

    prov.kill_node_container(tid, nid)
    mock_ctr.kill.assert_called_once()

    mock_client.containers.list.return_value = []
    with pytest.raises(LookupError, match="runtime container not found"):
        prov.kill_node_container(tid, nid)

    mock_client.containers.list.return_value = [mock_ctr]
    mock_ctr.kill.side_effect = APIError("boom")
    with pytest.raises(RuntimeError):
        prov.kill_node_container(tid, nid)
