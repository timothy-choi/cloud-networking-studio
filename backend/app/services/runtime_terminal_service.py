"""Interactive terminal sessions (Docker attach; Kubernetes guidance)."""

from __future__ import annotations

import asyncio
import logging
import os
import select
import socket
from datetime import UTC, datetime, timedelta
from uuid import UUID

import docker
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.deployment import Deployment, DeploymentEvent, DeploymentEventLevel
from app.models.deployment_runtime_terminal_session import DeploymentRuntimeTerminalSession
from app.models.topology import Topology
from app.providers.docker_runtime_provider import (
    DockerRuntimeProvider,
    container_name,
    runtime_provider_for_topology,
)
from app.schemas.runtime_terminal import (
    TerminalSessionCloseResponse,
    TerminalSessionCreateResponse,
)
from app.services.runtime_operations_service import get_runtime_resource_row, workload_node_id

_log = logging.getLogger(__name__)


def _idle_seconds() -> int:
    return max(60, int(getattr(settings, "terminal_idle_timeout_seconds", 300)))


def _max_duration_seconds() -> int:
    return max(120, int(getattr(settings, "terminal_max_duration_seconds", 3600)))


def _max_sessions_per_user() -> int:
    return max(1, int(getattr(settings, "terminal_max_sessions_per_user", 3)))


def _append_audit_event(db: Session, deployment_id: UUID, message: str) -> None:
    db.add(
        DeploymentEvent(
            deployment_id=deployment_id,
            level=DeploymentEventLevel.INFO,
            message=message,
        )
    )


def _count_active_sessions(db: Session, user_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(DeploymentRuntimeTerminalSession)
            .where(
                DeploymentRuntimeTerminalSession.user_id == user_id,
                DeploymentRuntimeTerminalSession.status.in_(("opening", "active")),
            )
        )
        or 0
    )


def create_terminal_session(
    db: Session,
    user_id: UUID,
    deployment_id: UUID,
    runtime_resource_id: UUID,
) -> TerminalSessionCreateResponse:
    dep = db.get(Deployment, deployment_id)
    if dep is None:
        raise ValueError("deployment not found")
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        raise ValueError("topology not found")
    res = get_runtime_resource_row(db, deployment_id, runtime_resource_id)
    if res.resource_type != "service":
        raise ValueError("terminal requires a persisted service runtime resource row")
    wid = workload_node_id(res)
    if wid is None:
        raise ValueError("runtime resource has no workload node id")

    if _count_active_sessions(db, user_id) >= _max_sessions_per_user():
        raise PermissionError("maximum concurrent terminal sessions reached")

    prov_name = (dep.runtime_target or "docker").strip().lower()
    now = datetime.now(UTC)
    expires = now + timedelta(seconds=_max_duration_seconds())

    row = DeploymentRuntimeTerminalSession(
        deployment_id=deployment_id,
        runtime_resource_id=runtime_resource_id,
        user_id=user_id,
        status="opening",
        runtime_provider=prov_name,
        shell="/bin/sh",
        audit_message=f"terminal session requested for service resource {runtime_resource_id}",
        opened_at=now,
        last_activity_at=now,
    )
    db.add(row)
    db.flush()

    _append_audit_event(
        db,
        deployment_id,
        f"Terminal session opened session_id={row.id} user_id={user_id} service_resource={runtime_resource_id}",
    )

    msg = None
    if prov_name == "kubernetes":
        msg = (
            "Kubernetes interactive attach is limited in this build; use kubectl exec snippets "
            "from the Use deployment tab, or connect via the cluster API."
        )

    return TerminalSessionCreateResponse(
        session_id=row.id,
        deployment_id=deployment_id,
        service_id=runtime_resource_id,
        status=row.status,
        websocket_path=f"/terminal-sessions/{row.id}/ws",
        expires_at=expires,
        max_duration_seconds=_max_duration_seconds(),
        idle_timeout_seconds=_idle_seconds(),
        runtime_provider=prov_name,
        message=msg,
    )


def close_terminal_session(
    db: Session, user_id: UUID, session_id: UUID, *, reason: str = "client_close"
) -> TerminalSessionCloseResponse:
    row = db.get(DeploymentRuntimeTerminalSession, session_id)
    if row is None:
        raise ValueError("session not found")
    if row.user_id != user_id:
        raise PermissionError("not your terminal session")
    if row.status in ("closed", "expired"):
        return TerminalSessionCloseResponse(
            session_id=row.id, status=row.status, close_reason=row.close_reason
        )
    row.status = "closed"
    row.closed_at = datetime.now(UTC)
    row.close_reason = reason
    _append_audit_event(
        db,
        row.deployment_id,
        f"Terminal session closed session_id={row.id} reason={reason}",
    )
    return TerminalSessionCloseResponse(
        session_id=row.id, status=row.status, close_reason=row.close_reason
    )


def _resolve_docker_container_id(
    dep: Deployment, topo: Topology, node_id: UUID
) -> str | None:
    if os.environ.get("CNS_USE_FAKE_DOCKER", "").lower() in ("1", "true", "yes"):
        return None
    prov = runtime_provider_for_topology(dep.runtime_target)
    if isinstance(prov, DockerRuntimeProvider):
        return prov.find_container_id_for_node(topo.id, node_id)
    from app.providers.go_hybrid_runtime_provider import GoHybridDockerRuntimeProvider

    if isinstance(prov, GoHybridDockerRuntimeProvider):
        return prov.find_container_id_for_node(topo.id, node_id)
    return None


def _docker_exec_socket(container_id: str, shell: str) -> tuple[object, object]:
    client = docker.from_env()
    api = client.api
    exec_id = api.exec_create(container_id, [shell], stdin=True, tty=True)
    sock = api.exec_start(exec_id, detach=False, tty=True, socket=True)
    return client, sock


async def _bridge_docker_socket(websocket: WebSocket, sock: object, idle_seconds: int) -> None:
    """Bidirectional bridge between WebSocket and docker exec socket."""
    stream = sock
    if hasattr(stream, "_sock"):
        stream = stream._sock  # type: ignore[attr-defined]
    if not hasattr(stream, "recv"):
        await websocket.send_text("Terminal backend could not attach to container socket.\r\n")
        return

    loop = asyncio.get_running_loop()
    last_activity = datetime.now(UTC)

    async def pump_out() -> None:
        nonlocal last_activity
        while True:
            ready, _, _ = await loop.run_in_executor(
                None, lambda: select.select([stream], [], [], 1.0)
            )
            if ready:
                chunk = await loop.run_in_executor(None, stream.recv, 4096)
                if not chunk:
                    break
                last_activity = datetime.now(UTC)
                await websocket.send_bytes(
                    chunk if isinstance(chunk, bytes) else bytes(chunk)
                )
            elif (datetime.now(UTC) - last_activity).total_seconds() > idle_seconds:
                await websocket.send_text("\r\n[idle timeout]\r\n")
                break

    async def pump_in() -> None:
        nonlocal last_activity
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break
            last_activity = datetime.now(UTC)
            data = msg.get("bytes") or msg.get("text", "").encode()
            if data:
                await loop.run_in_executor(None, stream.send, data)

    tasks = [asyncio.create_task(pump_out()), asyncio.create_task(pump_in())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        _ = t.exception()


async def handle_terminal_websocket(
    websocket: WebSocket,
    db: Session,
    user_id: UUID,
    session_id: UUID,
) -> None:
    row = db.get(DeploymentRuntimeTerminalSession, session_id)
    if row is None:
        await websocket.close(code=4404)
        return
    if row.user_id != user_id:
        await websocket.close(code=4403)
        return
    if row.status in ("closed", "expired"):
        await websocket.close(code=4409)
        return

    dep = db.get(Deployment, row.deployment_id)
    if dep is None:
        await websocket.close(code=4404)
        return
    topo = db.get(Topology, dep.topology_id)
    if topo is None:
        await websocket.close(code=4404)
        return

    res = get_runtime_resource_row(db, row.deployment_id, row.runtime_resource_id)
    wid = workload_node_id(res)
    if wid is None:
        await websocket.send_text("No workload node mapped to this service.\r\n")
        await websocket.close(code=1011)
        return

    await websocket.accept()
    row.status = "active"
    row.last_activity_at = datetime.now(UTC)
    db.commit()

    prov = (row.runtime_provider or "docker").strip().lower()
    if prov == "kubernetes":
        await websocket.send_text(
            "Kubernetes interactive terminal is not attached in-process.\r\n"
            "Use kubectl exec / port-forward snippets under Use deployment.\r\n"
        )
        await websocket.close(code=1000)
        return

    if os.environ.get("CNS_USE_FAKE_DOCKER", "").lower() in ("1", "true", "yes"):
        cname = container_name(wid, res.name)
        await websocket.send_text(
            f"Simulated terminal for {cname} (fake Docker — no socket).\r\n"
            "Type 'help' or use Safe exec for diagnostics.\r\n"
        )
        try:
            while True:
                msg = await websocket.receive_text()
                row.last_activity_at = datetime.now(UTC)
                if msg.strip().lower() in ("exit", "quit"):
                    break
                await websocket.send_text(f"simulated> echo {msg}\r\n")
        except WebSocketDisconnect:
            pass
        finally:
            close_terminal_session(db, user_id, session_id, reason="disconnect")
            db.commit()
        return

    cid = _resolve_docker_container_id(dep, topo, wid)
    if not cid:
        await websocket.send_text("Container not found for this node. Is the deployment still running?\r\n")
        await websocket.close(code=1011)
        return

    client = None
    try:
        client, sock = _docker_exec_socket(cid, row.shell)
        await websocket.send_text(f"Connected to {res.runtime_name} ({cid[:12]}).\r\n")
        await _bridge_docker_socket(websocket, sock, _idle_seconds())
    except WebSocketDisconnect:
        pass
    except (docker.errors.APIError, OSError, socket.error) as exc:
        _log.warning("terminal bridge error session=%s: %s", session_id, exc)
        try:
            await websocket.send_text(f"Terminal error: {exc}\r\n")
        except Exception:
            pass
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        close_terminal_session(db, user_id, session_id, reason="disconnect")
        db.commit()
