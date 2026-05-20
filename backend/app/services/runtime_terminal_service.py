"""Interactive terminal sessions (Docker TTY attach; Kubernetes guidance loop)."""

from __future__ import annotations

import asyncio
import json
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

_PING_INTERVAL_SECONDS = 25


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


def _session_expired(row: DeploymentRuntimeTerminalSession) -> bool:
    opened = row.opened_at
    if opened is None:
        return False
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=UTC)
    return (datetime.now(UTC) - opened).total_seconds() > _max_duration_seconds()


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
    _log.info(
        "terminal session created session_id=%s deployment_id=%s user_id=%s provider=%s",
        row.id,
        deployment_id,
        user_id,
        prov_name,
    )

    msg = None
    if prov_name == "kubernetes":
        msg = (
            "Kubernetes: interactive attach is not available in this build. "
            "Use kubectl exec from the Use deployment tab, or Safe exec for allowlisted commands."
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
    row.status = "expired" if reason in ("idle_timeout", "max_duration") else "closed"
    row.closed_at = datetime.now(UTC)
    row.close_reason = reason
    _append_audit_event(
        db,
        row.deployment_id,
        f"Terminal session closed session_id={row.id} reason={reason}",
    )
    _log.info(
        "terminal session ended session_id=%s reason=%s status=%s",
        row.id,
        reason,
        row.status,
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


def _docker_exec_socket(container_id: str, shell: str) -> tuple[docker.DockerClient, object, str]:
    client = docker.from_env()
    api = client.api
    exec_id = api.exec_create(container_id, [shell], stdin=True, tty=True)
    sock = api.exec_start(exec_id, detach=False, tty=True, socket=True)
    return client, sock, exec_id


async def _send_error_and_close(
    websocket: WebSocket, message: str, *, code: int = 1011
) -> None:
    payload = json.dumps({"type": "error", "message": message})
    try:
        await websocket.send_text(payload)
        await websocket.send_text(f"\r\n{message}\r\n")
    except Exception:
        pass
    await websocket.close(code=code, reason=message[:120])


async def _handle_control_message(
    websocket: WebSocket,
    raw: str,
    *,
    api: object | None,
    exec_id: str | None,
) -> bool:
    """Returns True if message was handled (caller should not forward to shell)."""
    stripped = raw.strip()
    if not stripped.startswith("{"):
        return False
    try:
        ctrl = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    if not isinstance(ctrl, dict):
        return False
    kind = str(ctrl.get("type") or "").lower()
    if kind == "ping":
        await websocket.send_text(json.dumps({"type": "pong"}))
        return True
    if kind == "resize" and api is not None and exec_id:
        cols = int(ctrl.get("cols") or 80)
        rows = int(ctrl.get("rows") or 24)
        cols = max(1, min(cols, 500))
        rows = max(1, min(rows, 200))
        try:
            api.exec_resize(exec_id, height=rows, width=cols)  # type: ignore[attr-defined]
        except Exception as exc:
            _log.debug("terminal resize failed session exec_id=%s: %s", exec_id, exc)
        return True
    return False


async def _bridge_docker_socket(
    websocket: WebSocket,
    sock: object,
    *,
    idle_seconds: int,
    max_duration_seconds: int,
    session_id: UUID,
    api: object | None = None,
    exec_id: str | None = None,
    db: Session | None = None,
    row: DeploymentRuntimeTerminalSession | None = None,
    user_id: UUID | None = None,
) -> str:
    """Bidirectional bridge between WebSocket and docker exec socket. Returns close reason."""
    stream = sock
    if hasattr(stream, "_sock"):
        stream = stream._sock  # type: ignore[attr-defined]
    if not hasattr(stream, "recv"):
        await websocket.send_text("Terminal backend could not attach to container socket.\r\n")
        return "attach_failed"

    loop = asyncio.get_running_loop()
    last_activity = datetime.now(UTC)
    opened = last_activity
    close_reason = "disconnect"

    async def pump_out() -> None:
        nonlocal last_activity, close_reason
        while True:
            if (datetime.now(UTC) - opened).total_seconds() > max_duration_seconds:
                await websocket.send_text("\r\n[max session duration]\r\n")
                close_reason = "max_duration"
                break
            ready, _, _ = await loop.run_in_executor(
                None, lambda: select.select([stream], [], [], 1.0)
            )
            if ready:
                chunk = await loop.run_in_executor(None, stream.recv, 4096)
                if not chunk:
                    close_reason = "container_eof"
                    break
                last_activity = datetime.now(UTC)
                if row is not None and db is not None:
                    row.last_activity_at = last_activity
                await websocket.send_bytes(
                    chunk if isinstance(chunk, bytes) else bytes(chunk)
                )
            elif (datetime.now(UTC) - last_activity).total_seconds() > idle_seconds:
                await websocket.send_text("\r\n[idle timeout]\r\n")
                close_reason = "idle_timeout"
                break

    async def pump_in() -> None:
        nonlocal last_activity, close_reason
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                close_reason = "client_close"
                break
            last_activity = datetime.now(UTC)
            if row is not None and db is not None:
                row.last_activity_at = last_activity
                db.commit()
            if msg.get("bytes"):
                data = msg["bytes"]
            else:
                text = msg.get("text") or ""
                if await _handle_control_message(
                    websocket, text, api=api, exec_id=exec_id
                ):
                    continue
                data = text.encode()
            if data:
                await loop.run_in_executor(None, stream.send, data)

    async def pump_server_ping() -> None:
        while True:
            await asyncio.sleep(_PING_INTERVAL_SECONDS)
            try:
                await websocket.send_text(json.dumps({"type": "ping"}))
            except Exception:
                break

    tasks = [
        asyncio.create_task(pump_out()),
        asyncio.create_task(pump_in()),
        asyncio.create_task(pump_server_ping()),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        exc = t.exception()
        if exc and not isinstance(exc, WebSocketDisconnect):
            _log.warning("terminal bridge task error session=%s: %s", session_id, exc)
    return close_reason


async def _interactive_guidance_loop(
    websocket: WebSocket,
    *,
    intro: str,
    idle_seconds: int,
    max_duration_seconds: int,
) -> str:
    """Keep WebSocket open with guidance text (Kubernetes / unsupported paths)."""
    await websocket.send_text(intro)
    opened = datetime.now(UTC)
    last_activity = opened
    close_reason = "disconnect"
    try:
        while True:
            if (datetime.now(UTC) - opened).total_seconds() > max_duration_seconds:
                await websocket.send_text("\r\n[max session duration]\r\n")
                close_reason = "max_duration"
                break
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=float(_PING_INTERVAL_SECONDS))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
                continue
            if msg["type"] == "websocket.disconnect":
                close_reason = "client_close"
                break
            last_activity = datetime.now(UTC)
            text = ""
            if msg.get("text"):
                text = msg["text"]
                if await _handle_control_message(websocket, text, api=None, exec_id=None):
                    continue
            elif msg.get("bytes"):
                text = msg["bytes"].decode(errors="replace")
            if text.strip().lower() in ("exit", "quit"):
                close_reason = "client_close"
                break
            if text.strip():
                await websocket.send_text(
                    "\r\n[interactive shell unavailable — use Safe exec for allowlisted commands]\r\n"
                )
            if (datetime.now(UTC) - last_activity).total_seconds() > idle_seconds:
                await websocket.send_text("\r\n[idle timeout]\r\n")
                close_reason = "idle_timeout"
                break
    except WebSocketDisconnect:
        close_reason = "client_close"
    return close_reason


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
    if _session_expired(row):
        row.status = "expired"
        row.close_reason = "max_duration"
        row.closed_at = datetime.now(UTC)
        db.commit()
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

    await websocket.accept()
    _log.info("terminal websocket connected session_id=%s user_id=%s", session_id, user_id)

    if wid is None:
        close_reason = "error"
        await _send_error_and_close(
            websocket, "No workload node mapped to this service."
        )
        return

    row.status = "active"
    row.last_activity_at = datetime.now(UTC)
    db.commit()

    prov = (row.runtime_provider or "docker").strip().lower()
    idle = _idle_seconds()
    max_dur = _max_duration_seconds()
    close_reason = "disconnect"

    try:
        if prov == "kubernetes":
            intro = (
                "Kubernetes interactive terminal is not attached in-process.\r\n"
                "Use kubectl exec / port-forward snippets under Use deployment.\r\n"
                "Safe exec supports allowlisted diagnostics when RUNTIME_EXECUTOR=go.\r\n"
                "Type exit or quit to close.\r\n"
            )
            close_reason = await _interactive_guidance_loop(
                websocket,
                intro=intro,
                idle_seconds=idle,
                max_duration_seconds=max_dur,
            )
            return

        if os.environ.get("CNS_USE_FAKE_DOCKER", "").lower() in ("1", "true", "yes"):
            cname = container_name(wid, res.name)
            await websocket.send_text(
                f"Simulated terminal for {cname} (fake Docker — no socket).\r\n"
                "Type 'help' or use Safe exec for diagnostics. Type exit to close.\r\n"
            )
            _log.info("terminal exec attached (simulated) session_id=%s", session_id)
            try:
                opened = datetime.now(UTC)
                while True:
                    if (datetime.now(UTC) - opened).total_seconds() > max_dur:
                        await websocket.send_text("\r\n[max session duration]\r\n")
                        close_reason = "max_duration"
                        break
                    try:
                        msg = await asyncio.wait_for(
                            websocket.receive(), timeout=float(_PING_INTERVAL_SECONDS)
                        )
                    except asyncio.TimeoutError:
                        await websocket.send_text(json.dumps({"type": "ping"}))
                        continue
                    if msg["type"] == "websocket.disconnect":
                        close_reason = "client_close"
                        break
                    text = msg.get("text") or ""
                    if msg.get("bytes"):
                        text = msg["bytes"].decode(errors="replace")
                    if await _handle_control_message(websocket, text, api=None, exec_id=None):
                        continue
                    row.last_activity_at = datetime.now(UTC)
                    db.commit()
                    if text.strip().lower() in ("exit", "quit"):
                        close_reason = "client_close"
                        break
                    await websocket.send_text(f"simulated> echo {text}\r\n")
            except WebSocketDisconnect:
                close_reason = "client_close"
            return

        cid = _resolve_docker_container_id(dep, topo, wid)
        if not cid:
            await _send_error_and_close(
                websocket,
                "Container not found for this node. Is the deployment still running? "
                "Try Safe exec for allowlisted diagnostics.",
            )
            close_reason = "error"
            return

        client = None
        exec_id = None
        try:
            client, sock, exec_id = _docker_exec_socket(cid, row.shell)
            _log.info(
                "terminal exec attached session_id=%s container_id=%s exec_id=%s",
                session_id,
                cid[:12],
                exec_id,
            )
            await websocket.send_text(
                f"\r\nConnected to {res.runtime_name} ({cid[:12]}).\r\n"
            )
            close_reason = await _bridge_docker_socket(
                websocket,
                sock,
                idle_seconds=idle,
                max_duration_seconds=max_dur,
                session_id=session_id,
                api=client.api if client else None,
                exec_id=exec_id,
                db=db,
                row=row,
                user_id=user_id,
            )
        except WebSocketDisconnect:
            close_reason = "client_close"
        except (docker.errors.APIError, OSError, socket.error) as exc:
            _log.warning("terminal bridge error session=%s: %s", session_id, exc)
            close_reason = "error"
            try:
                await _send_error_and_close(
                    websocket,
                    f"Terminal error: {exc}. Use Safe exec if the shell is unavailable.",
                    code=1011,
                )
            except Exception:
                pass
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
    finally:
        _log.info(
            "terminal websocket closed session_id=%s reason=%s",
            session_id,
            close_reason,
        )
        close_terminal_session(db, user_id, session_id, reason=close_reason)
        db.commit()
