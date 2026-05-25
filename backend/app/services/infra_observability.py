"""Infrastructure deployment metrics and event timeline (Step 57C)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def append_event(events: list[dict[str, Any]], event_type: str, *, message: str = "", metadata: dict | None = None) -> list[dict[str, Any]]:
    updated = list(events or [])
    updated.append(
        {
            "type": event_type,
            "message": message,
            "metadata": metadata or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    return updated


def record_metric(metrics: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    updated = dict(metrics or {})
    updated[key] = value
    return updated


def increment_counter(metrics: dict[str, Any], key: str, amount: int = 1) -> dict[str, Any]:
    updated = dict(metrics or {})
    updated[key] = int(updated.get(key) or 0) + amount
    return updated
