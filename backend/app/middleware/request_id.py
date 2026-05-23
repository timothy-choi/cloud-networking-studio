"""Attach X-Request-ID to every request and response."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import get_request_id, new_request_id, set_request_id

_log = logging.getLogger("cns.request")
_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = (request.headers.get(_HEADER) or "").strip()
        rid = incoming or new_request_id()
        set_request_id(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            _log.exception(
                "request failed method=%s path=%s request_id=%s elapsed_ms=%s",
                request.method,
                request.url.path,
                rid,
                elapsed_ms,
            )
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.headers[_HEADER] = rid
        from app.services.request_metrics import record_api_request

        record_api_request(status_code=response.status_code)
        _log.info(
            "request method=%s path=%s status=%s request_id=%s elapsed_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            rid,
            elapsed_ms,
        )
        return response
