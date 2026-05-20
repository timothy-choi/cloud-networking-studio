"""Step 49: terminal sessions and integration endpoints."""

from __future__ import annotations

import asyncio
import select as selectors
import uuid
from uuid import UUID

import pytest

from app.db.session import SessionLocal
from app.models.topology import NodeType
from app.services.deployment_runtime_resource_service import replace_runtime_resources_from_payload

TOPO = {
    "name": "Terminal lab",
    "description": "",
    "runtime_target": "docker",
    "networking_mode": "docker_bridge",
}


def _topology_with_service(client):
    tid = client.post("/topologies", json=TOPO).json()["id"]
    n = client.post(
        f"/topologies/{tid}/nodes",
        json={
            "name": "web",
            "node_type": NodeType.HOST.value,
            "image": "alpine:latest",
            "ip_address": None,
            "config": None,
        },
    ).json()
    client.post(
        f"/topologies/{tid}/links",
        json={
            "source_node_id": n["id"],
            "target_node_id": n["id"],
            "network_name": "net0",
            "cidr": "10.0.0.0/24",
            "config": None,
        },
    )
    dep = client.post(f"/topologies/{tid}/deploy").json()
    return tid, dep["id"], n["id"]


def _reg(client_strict, prefix: str) -> tuple[str, dict[str, str]]:
    email = f"{prefix}{uuid.uuid4().hex[:8]}@example.com"
    r = client_strict.post(
        "/auth/register",
        json={"email": email, "password": "password123", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _lab_service_row(client_strict):
    _, ha = _reg(client_strict, "termo")
    eb, hb = _reg(client_strict, "termv")
    pid = client_strict.get("/projects", headers=ha).json()[0]["id"]
    assert (
        client_strict.post(
            f"/projects/{pid}/members/invite",
            headers=ha,
            json={"email": eb, "role": "viewer"},
        ).status_code
        == 201
    )
    tid = client_strict.post(
        "/topologies",
        headers=ha,
        json={**TOPO, "project_id": pid},
    ).json()["id"]
    nid = client_strict.post(
        f"/topologies/{tid}/nodes",
        headers=ha,
        json={
            "name": "web",
            "node_type": NodeType.HOST.value,
            "image": None,
            "ip_address": None,
            "config": None,
        },
    ).json()["id"]
    did = client_strict.post(f"/topologies/{tid}/deploy", headers=ha).json()["id"]
    with SessionLocal() as db:
        replace_runtime_resources_from_payload(
            db,
            UUID(did),
            {
                "runtime_provider": "docker",
                "resources": [
                    {
                        "type": "service",
                        "service_id": nid,
                        "name": "web",
                        "runtime_name": "cns-node-web",
                        "internal_url": "http://cns-node-web:80",
                    },
                ],
            },
        )
        db.commit()
    rid = client_strict.get(f"/deployments/{did}/runtime/services", headers=ha).json()["services"][0]["id"]
    return ha, hb, did, rid


def test_integration_endpoint_returns_snippets(client):
    _, did, _ = _topology_with_service(client)
    r = client.get(f"/deployments/{did}/runtime/integration")
    assert r.status_code == 200
    body = r.json()
    assert body["deployment_id"] == did
    assert len(body["snippets"]) >= 1
    assert body["env_vars"]["CNS_DEPLOYMENT_ID"] == did


def test_mapping_endpoint_returns_rows(client):
    _, did, nid = _topology_with_service(client)
    r = client.get(f"/deployments/{did}/runtime/mapping")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert len(rows) >= 1
    assert any(str(row.get("topology_node_id")) == nid for row in rows)


def test_viewer_cannot_open_terminal(client_strict):
    ha, hb, did, rid = _lab_service_row(client_strict)
    r = client_strict.post(
        f"/deployments/{did}/runtime/services/{rid}/terminal",
        headers=hb,
    )
    assert r.status_code == 403


def test_member_can_create_terminal_session(client_strict):
    ha, _, did, rid = _lab_service_row(client_strict)
    r = client_strict.post(
        f"/deployments/{did}/runtime/services/{rid}/terminal",
        headers=ha,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["session_id"]
    assert body["websocket_path"].startswith("/terminal-sessions/")
    close = client_strict.delete(f"/terminal-sessions/{body['session_id']}", headers=ha)
    assert close.status_code == 200


def test_readable_recv_uses_stdlib_select_not_sqlalchemy(monkeypatch):
    """Regression: sqlalchemy.select must not shadow stdlib select in the bridge."""
    from sqlalchemy import select as sa_select

    from app.services import runtime_terminal_service as tsvc

    assert sa_select is not selectors
    select_calls: list[object] = []

    def _fake_select(rlist, _wlist, _xlist, _timeout):
        select_calls.extend(rlist)
        return rlist, [], []

    monkeypatch.setattr(
        "app.services.runtime_terminal_service.selectors.select",
        _fake_select,
    )

    class _Sock:
        def recv(self, _n: int) -> bytes:
            return b"ok"

    assert tsvc._readable_recv(_Sock(), 4096, 1.0) == b"ok"
    assert select_calls


def test_bridge_docker_socket_startup_no_select_attribute_error(monkeypatch):
    """Bridge must start runner->browser and browser->runner without select.select crash."""
    from unittest.mock import AsyncMock

    from app.services.runtime_terminal_service import _bridge_docker_socket

    def _fake_select(rlist, _wlist, _xlist, _timeout):
        return rlist, [], []

    monkeypatch.setattr(
        "app.services.runtime_terminal_service.selectors.select",
        _fake_select,
    )

    class _Stream:
        def __init__(self) -> None:
            self._reads = 0

        def recv(self, _n: int) -> bytes:
            self._reads += 1
            if self._reads == 1:
                return b"container-hello"
            return b""

        def send(self, data: bytes) -> None:
            self.last = data

    stream = _Stream()
    sock = type("ExecSocket", (), {"_sock": stream})()

    ws = AsyncMock()
    ws.send_bytes = AsyncMock()
    ws.send_text = AsyncMock()

    # Block browser reads so runner->browser finishes first (avoids CI race where
    # client_close wins before container output is forwarded).
    browser_blocked = asyncio.Event()

    async def _receive():
        await browser_blocked.wait()

    ws.receive = _receive

    reason = asyncio.run(
        _bridge_docker_socket(
            ws,
            sock,
            idle_seconds=300,
            max_duration_seconds=3600,
            session_id=uuid.uuid4(),
        )
    )

    assert reason == "container_eof"
    assert reason != "bridge_error"
    ws.send_bytes.assert_called_once_with(b"container-hello")


def test_terminal_websocket_stays_open_under_fake_docker(client_strict):
    """WebSocket should not close immediately in simulated (CI) mode."""
    ha, _, did, rid = _lab_service_row(client_strict)
    r = client_strict.post(
        f"/deployments/{did}/runtime/services/{rid}/terminal",
        headers=ha,
    )
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    token = ha["Authorization"].split(" ", 1)[1]
    with client_strict.websocket_connect(
        f"/terminal-sessions/{sid}/ws?token={token}"
    ) as ws:
        banner = ws.receive_text()
        assert "Simulated" in banner
        ws.send_text("hello")
        reply = ws.receive_text()
        if reply.strip().startswith("{"):
            import json

            body = json.loads(reply)
            if body.get("type") == "terminal_data":
                reply = str(body.get("data") or "")
        assert "simulated" in reply.lower()
        ws.send_text('{"type":"ping"}')
        pong = ws.receive_text()
        assert '"pong"' in pong
        ws.send_text("exit")
    close = client_strict.delete(f"/terminal-sessions/{sid}", headers=ha)
    assert close.status_code == 200
