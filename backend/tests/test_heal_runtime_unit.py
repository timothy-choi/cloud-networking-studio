"""Unit tests for Docker heal_restart_stopped (mocked engine)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.providers.docker_runtime_provider import DockerRuntimeProvider


def test_heal_restart_stopped_calls_start_on_exited_container():
    tid = uuid.uuid4()
    nid = uuid.uuid4()

    mock_ctr = MagicMock()
    mock_ctr.status = "exited"
    mock_ctr.attrs = {
        "Id": "aaabbbcccdddeeefff0011223344556677889900",
        "Name": "/test-c",
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

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [mock_ctr]

    prov = DockerRuntimeProvider(client=mock_client)
    result = prov.heal_restart_stopped(tid)

    mock_ctr.start.assert_called_once()
    assert len(result.restarted) == 1
    assert result.errors == ()
