"""Accept ``/api/...`` when clients hit FastAPI directly (no reverse-proxy rewrite).

Caddy ``handle_path /api/*`` and the Vite dev proxy strip the ``/api`` prefix before
forwarding to this app. Tools that call ``http://<host>:8000/api/deployments/...``
would otherwise 404 because routes are registered at ``/deployments/...``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

ASGIApp = Callable[[dict[str, Any], Any, Any], Awaitable[None]]


class StripApiPrefixMiddleware:
    """Rewrite ``/api`` + remainder to ``/`` + remainder for HTTP and WebSocket scopes."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        new_scope = scope
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path") or ""
            if path.startswith("/api/") or path == "/api":
                new_scope = dict(scope)
                if path.startswith("/api/"):
                    new_scope["path"] = path[4:]
                else:
                    new_scope["path"] = "/"
                if not new_scope["path"].startswith("/"):
                    new_scope["path"] = "/" + new_scope["path"]
                raw = new_scope.get("raw_path")
                if isinstance(raw, (bytes, bytearray, memoryview)):
                    new_scope["raw_path"] = new_scope["path"].encode("latin-1")
        await self.app(new_scope, receive, send)
