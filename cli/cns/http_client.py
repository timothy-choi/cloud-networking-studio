"""Minimal HTTP JSON client (stdlib only)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any


def request_json(
    method: str,
    url: str,
    *,
    token: str | None,
    body: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = None
    if url.lower().startswith("https://"):
        ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            code = resp.getcode()
            raw = resp.read().decode("utf-8") or ""
            if code == 204 or not raw.strip():
                return code, None
            return code, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        try:
            payload = json.loads(raw) if raw.strip() else {"detail": e.reason}
        except json.JSONDecodeError:
            payload = {"detail": raw or e.reason}
        raise ApiHttpError(e.code, payload) from e


class ApiHttpError(Exception):
    def __init__(self, status: int, payload: Any) -> None:
        super().__init__(f"HTTP {status}: {payload}")
        self.status = status
        self.payload = payload
