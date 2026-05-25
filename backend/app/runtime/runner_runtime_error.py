"""Structured last-runtime-error state for backend → Go runner observability."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

_PROBE_OPERATIONS = frozenset({"status", "runtime_status", "runner_status", "health", "version"})
_STALE_AFTER = timedelta(minutes=5)

_lock = threading.Lock()
_last_error: RunnerRuntimeError | None = None


@dataclass(frozen=True)
class RunnerRuntimeError:
    operation: str
    message: str
    timestamp: datetime
    request_id: str | None = None
    status_code: int | None = None

    def to_dict(self, *, now: datetime | None = None) -> dict[str, Any]:
        at = now or datetime.now(UTC)
        age = at - self.timestamp
        historical = age > _STALE_AFTER
        return {
            "operation": self.operation,
            "request_id": self.request_id,
            "status_code": self.status_code,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "historical": historical,
        }

    def format_summary(self, *, now: datetime | None = None) -> str:
        detail = self.to_dict(now=now)
        parts = [f"Last failed operation: {detail['operation']}"]
        if detail.get("status_code") is not None:
            parts.append(f"returned {detail['status_code']}")
        if detail.get("message"):
            parts.append(f"— {detail['message']}")
        if detail.get("request_id"):
            parts.append(f"— request_id {detail['request_id']}")
        if detail.get("historical"):
            parts.append("(historical)")
        return " ".join(parts)


def set_runtime_error(
    *,
    operation: str,
    message: str,
    request_id: str | None = None,
    status_code: int | None = None,
    timestamp: datetime | None = None,
) -> None:
    global _last_error
    msg = (message or "unknown error").strip()[:500]
    rec = RunnerRuntimeError(
        operation=(operation or "unknown").strip() or "unknown",
        message=msg,
        request_id=(request_id or "").strip() or None,
        status_code=status_code,
        timestamp=timestamp or datetime.now(UTC),
    )
    with _lock:
        _last_error = rec


def clear_runtime_error() -> None:
    global _last_error
    with _lock:
        _last_error = None


def clear_runtime_error_after_probe_success(operation: str) -> None:
    """Drop stale probe errors once status/health/runtime_status succeeds."""
    global _last_error
    op = (operation or "").strip()
    if op not in _PROBE_OPERATIONS:
        return
    with _lock:
        if _last_error is not None and _last_error.operation in _PROBE_OPERATIONS:
            _last_error = None


def clear_runtime_error_if_operation_succeeded(operation: str) -> None:
    """Clear the last error only when the same operation succeeds."""
    global _last_error
    op = (operation or "").strip()
    if not op:
        return
    with _lock:
        if _last_error is not None and _last_error.operation == op:
            _last_error = None


def get_runtime_error(*, include_historical: bool = True) -> dict[str, Any] | None:
    with _lock:
        err = _last_error
    if err is None:
        return None
    payload = err.to_dict()
    if not include_historical and payload.get("historical"):
        return None
    return payload


def get_runtime_error_summary(*, include_historical: bool = True) -> str | None:
    with _lock:
        err = _last_error
    if err is None:
        return None
    payload = err.to_dict()
    if not include_historical and payload.get("historical"):
        return None
    return err.format_summary()
