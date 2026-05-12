"""Unit tests for Docker inspection / reconcile with mocked SDK."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import docker

from app.providers.docker_runtime_provider import (
    DockerRuntimeProvider,
    topology_network_name,
)


def test_inspect_topology_filters_labels_and_returns_records():
    mock_client = MagicMock()
    tid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    nid = uuid.UUID("11111111-1111-1111-1111-111111111111")

    mock_net = MagicMock()
    mock_net.attrs = {
        "Id": "abc123full",
        "Name": topology_network_name(tid),
        "Driver": "bridge",
        "Scope": "local",
        "Labels": {"cns.topology_id": str(tid), "cns.managed": "true"},
        "IPAM": {"Driver": "default", "Config": [{"Subnet": "10.1.0.0/24"}]},
    }
    mock_client.networks.list.return_value = [mock_net]

    net_key = topology_network_name(tid)
    mock_ctr = MagicMock()
    mock_ctr.status = "running"
    mock_ctr.exec_run.return_value = (
        0,
        (
            b"FWD:0\nROUTES\ndefault via 10.1.0.1 dev eth0\nINTERFACES\n1: lo\n",
            b"",
        ),
    )
    mock_ctr.attrs = {
        "Id": "deadbeef0011223344556677889900",
        "Name": "/cns-node-test",
        "Image": "sha256:nope",
        "Config": {
            "Image": "alpine:latest",
            "Labels": {
                "cns.topology_id": str(tid),
                "cns.node_id": str(nid),
                "cns.managed": "true",
            },
        },
        "State": {"Running": True, "Status": "running", "StartedAt": "2020-01-01"},
        "Created": "2020-01-01",
        "NetworkSettings": {
            "Networks": {
                net_key: {
                    "IPAddress": "10.1.0.5",
                    "NetworkID": "abc123full",
                },
                "bridge": {
                    "IPAddress": "172.17.0.3",
                    "NetworkID": "bridgelegacy",
                },
            }
        },
    }
    mock_client.containers.list.return_value = [mock_ctr]

    prov = DockerRuntimeProvider(client=mock_client)
    snap = prov.inspect_topology_runtime(tid)

    mock_client.networks.list.assert_called()
    mock_client.containers.list.assert_called_once()
    flt = mock_client.containers.list.call_args.kwargs["filters"]
    assert "cns.topology_id=" in flt["label"][0]
    assert "cns.managed=true" in flt["label"]

    assert len(snap.networks) == 1
    assert snap.networks[0].subnet_hints == ("10.1.0.0/24",)
    assert len(snap.containers) == 1
    assert snap.containers[0].node_id == nid
    assert snap.containers[0].ipv4_by_network.get(net_key) == "10.1.0.5"
    assert "bridge" not in snap.containers[0].ipv4_by_network


def test_inspect_topology_returns_static_style_cns_subnet_ips():
    mock_client = MagicMock()
    tid = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    nid = uuid.UUID("22222222-2222-2222-2222-222222222222")

    mock_net = MagicMock()
    mock_net.attrs = {
        "Id": "net80full00",
        "Name": topology_network_name(tid),
        "Driver": "bridge",
        "Labels": {"cns.topology_id": str(tid), "cns.managed": "true"},
        "IPAM": {"Driver": "default", "Config": [{"Subnet": "10.80.0.0/24"}]},
    }
    mock_client.networks.list.return_value = [mock_net]

    net_key = topology_network_name(tid)
    mock_ctr = MagicMock()
    mock_ctr.status = "running"
    mock_ctr.exec_run.return_value = (
        0,
        (
            b"FWD:0\nROUTES\ndefault via 10.80.0.1 dev eth0\nINTERFACES\n1: lo\n",
            b"",
        ),
    )
    mock_ctr.attrs = {
        "Config": {
            "Labels": {
                "cns.topology_id": str(tid),
                "cns.node_id": str(nid),
                "cns.managed": "true",
            },
        },
        "State": {"Running": True},
        "NetworkSettings": {
            "Networks": {
                net_key: {
                    "IPAddress": "10.80.0.10",
                    "NetworkID": "net80full00",
                },
            }
        },
    }
    mock_client.containers.list.return_value = [mock_ctr]

    snap = DockerRuntimeProvider(client=mock_client).inspect_topology_runtime(tid)

    assert snap.containers[0].ipv4_by_network.get(net_key) == "10.80.0.10"
    assert snap.networks[0].subnet_hints == ("10.80.0.0/24",)


def test_fetch_logs_returns_none_when_missing_container():
    mock_client = MagicMock()
    mock_client.containers.list.return_value = []
    prov = DockerRuntimeProvider(client=mock_client)
    tid = uuid.uuid4()
    nid = uuid.uuid4()
    assert prov.fetch_logs_for_node(tid, nid, 50) is None


def test_reconcile_detects_missing_network_and_nodes():
    mock_client = MagicMock()
    mock_client.networks.list.return_value = []
    mock_client.containers.list.return_value = []

    prov = DockerRuntimeProvider(client=mock_client)
    tid = uuid.uuid4()
    n1 = uuid.uuid4()
    n2 = uuid.uuid4()
    res = prov.reconcile_runtime(tid, frozenset({n1, n2}))

    assert res.missing_network is True
    assert set(res.missing_node_ids) == {n1, n2}
    assert res.stopped_containers == ()


def test_reconcile_detects_stopped_container():
    mock_client = MagicMock()
    mock_net = MagicMock()
    mock_client.networks.list.return_value = [mock_net]

    tid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    nid = uuid.UUID("11111111-1111-1111-1111-111111111111")

    mock_ctr = MagicMock()
    mock_ctr.status = "exited"
    mock_ctr.attrs = {
        "Id": "abcdef00112233445566778899001234567890",
        "Name": "/dead",
        "Config": {
            "Image": "alpine:latest",
            "Labels": {
                "cns.topology_id": str(tid),
                "cns.node_id": str(nid),
                "cns.managed": "true",
            },
        },
        "State": {"Running": False, "Status": "exited"},
        "NetworkSettings": {"Networks": {}},
    }

    mock_client.containers.list.return_value = [mock_ctr]

    prov = DockerRuntimeProvider(client=mock_client)
    res = prov.reconcile_runtime(tid, frozenset({nid}))

    assert res.missing_network is False
    assert res.missing_node_ids == ()
    assert len(res.stopped_containers) == 1
    assert "dead" in res.stopped_containers[0][1]


def test_inspect_handles_api_errors_gracefully():
    mock_client = MagicMock()
    mock_client.networks.list.side_effect = docker.errors.APIError("boom")
    mock_client.containers.list.side_effect = docker.errors.APIError("boom")

    prov = DockerRuntimeProvider(client=mock_client)
    snap = prov.inspect_topology_runtime(uuid.uuid4())
    assert snap.networks == ()
    assert snap.containers == ()


def test_stats_maps_cpu_memory_network():
    mock_client = MagicMock()
    tid = uuid.uuid4()
    nid = uuid.uuid4()

    ctr = MagicMock()
    ctr.stats.return_value = {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200},
            "system_cpu_usage": 100000000000,
            "online_cpus": [0, 1],
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 99999900000,
        },
        "memory_stats": {"usage": 1024, "limit": 2048},
        "networks": {"eth0": {"rx_bytes": 10, "tx_bytes": 20}},
    }
    mock_client.containers.list.return_value = [ctr]

    prov = DockerRuntimeProvider(client=mock_client)
    stats = prov.fetch_stats_for_node(tid, nid)

    assert stats is not None
    assert stats.memory_usage_bytes == 1024
    assert stats.memory_limit_bytes == 2048
    assert stats.network_rx_bytes == 10
    assert stats.network_tx_bytes == 20
    assert stats.cpu_percent is not None
