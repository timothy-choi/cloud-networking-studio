"""Request-scoped context (correlation ID)."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def new_request_id() -> str:
    return uuid.uuid4().hex
