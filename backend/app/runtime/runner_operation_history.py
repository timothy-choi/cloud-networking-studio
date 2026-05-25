"""In-memory ring buffer of backend → Go runner delegations."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

_MAX_RECORDS = 100

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization|token|password|secret|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"Bearer\s+\S+", re.I),
)


@dataclass(frozen=True)
class RunnerOperationRecord:
    operation: str
    provider: str
    status: str
    duration_ms: int
    request_id: str | None
    deployment_id: str | None
    topology_id: str | None
    error_message: str | None
    created_at: datetime


_lock = threading.Lock()
_records: list[RunnerOperationRecord] = []


def _mask_error(message: str | None) -> str | None:
    if not message:
        return None
    out = message.strip()
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[redacted]", out)
    out = re.sub(r"\[redacted\](?:\s+\S+)?", "[redacted]", out)
    return out[:500] if out else None


def record_runner_operation(
    *,
    operation: str,
    provider: str,
    status: str,
    duration_ms: int,
    request_id: str | None = None,
    deployment_id: UUID | str | None = None,
    topology_id: UUID | str | None = None,
    error_message: str | None = None,
) -> None:
    dep = str(deployment_id) if deployment_id is not None else None
    topo = str(topology_id) if topology_id is not None else None
    rec = RunnerOperationRecord(
        operation=operation,
        provider=provider or "unknown",
        status=status,
        duration_ms=max(0, int(duration_ms)),
        request_id=(request_id or "").strip() or None,
        deployment_id=dep,
        topology_id=topo,
        error_message=_mask_error(error_message),
        created_at=datetime.now(UTC),
    )
    with _lock:
        _records.append(rec)
        if len(_records) > _MAX_RECORDS:
            del _records[: len(_records) - _MAX_RECORDS]


def list_recent_runner_operations(limit: int = 20) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 50))
    with _lock:
        rows = list(_records[-lim:])
    rows.reverse()
    return [
        {
            "operation": r.operation,
            "provider": r.provider,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "request_id": r.request_id,
            "deployment_id": r.deployment_id,
            "topology_id": r.topology_id,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
