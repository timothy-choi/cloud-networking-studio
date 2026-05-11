"""Unit tests for CNS vs default-bridge IP resolution (no Docker daemon)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.providers.docker_runtime_provider import (
    DockerRuntimeProvider,
    _pick_cns_ipv4,
    _runtime_ipv4_display_map,
    topology_network_name,
)


def test_pick_cns_ipv4_prefers_topology_network_over_bridge():
    tid = uuid.uuid4()
    pref = topology_network_name(tid)
    labeled = frozenset({"netsfullid001"})
    nets = {
        "bridge": {"IPAddress": "172.17.0.2", "NetworkID": "bridgeid"},
        pref: {"IPAddress": "10.80.0.20", "NetworkID": "netsfullid001"},
    }
    assert _pick_cns_ipv4(nets, tid, labeled) == "10.80.0.20"


def test_pick_cns_ipv4_returns_none_when_only_bridge():
    tid = uuid.uuid4()
    labeled = frozenset({"netsfullid001"})
    nets = {"bridge": {"IPAddress": "172.17.0.2", "NetworkID": "bridgeid"}}
    assert _pick_cns_ipv4(nets, tid, labeled) is None


def test_runtime_ipv4_display_map_drops_bridge_when_cns_present():
    tid = uuid.uuid4()
    pref = topology_network_name(tid)
    labeled = frozenset({"nid001"})
    nets = {
        "bridge": {"IPAddress": "172.17.0.2", "NetworkID": "brid"},
        pref: {"IPAddress": "10.80.0.10", "NetworkID": "nid001"},
    }
    m = _runtime_ipv4_display_map(nets, tid, labeled)
    assert m[pref] == "10.80.0.10"
    assert "bridge" not in m


def test_resolve_node_ipv4_never_returns_17217_when_cns_exists():
    tid = uuid.uuid4()
    nid = uuid.uuid4()
    pref = topology_network_name(tid)

    mock_ctr = MagicMock()
    mock_ctr.attrs = {
        "NetworkSettings": {
            "Networks": {
                pref: {"IPAddress": "10.80.0.20", "NetworkID": "xyz"},
                "bridge": {"IPAddress": "172.17.0.3", "NetworkID": "bridge"},
            }
        }
    }

    mock_labeled_net = MagicMock()
    mock_labeled_net.attrs = {"Id": "xyz", "Labels": {"cns.topology_id": str(tid)}}

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [mock_ctr]
    mock_client.networks.list.return_value = [mock_labeled_net]

    prov = DockerRuntimeProvider(client=mock_client)
    assert prov.resolve_node_ipv4(tid, nid) == "10.80.0.20"


def test_ping_command_from_service_targets_cns_ip(client, monkeypatch):
    """Traffic layer builds argv using resolved IP only (mock resolver)."""
    from app.models.topology import NodeType
    from app.providers.docker_runtime_provider import FakeDockerRuntimeProvider

    def fake_resolve(self, topology_id, node_id):
        _ = (self, topology_id, node_id)
        return "10.80.0.20"

    monkeypatch.setattr(FakeDockerRuntimeProvider, "resolve_node_ipv4", fake_resolve)

    tid = client.post(
        "/topologies",
        json={
            "name": "cns",
            "description": "",
            "runtime_target": "docker",
            "networking_mode": "docker_bridge",
        },
    ).json()["id"]
    na = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "a",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()["id"]
    nb = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "b",
            "node_type": NodeType.GENERIC.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()["id"]
    client.post(f"/topologies/{tid}/deploy")
    r = client.post(
        f"/topologies/{tid}/traffic-tests/ping",
        json={"source_node_id": na, "target_node_id": nb, "count": 2},
    )
    assert r.status_code == 201
    cmd = r.json()["command"]
    assert "10.80.0.20" in cmd
    assert "172.17" not in cmd
