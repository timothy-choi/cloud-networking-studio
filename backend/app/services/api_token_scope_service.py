"""Route-to-scope mapping and enforcement for API tokens (Step 53D)."""

from __future__ import annotations

import re

from fastapi import HTTPException, status

from app.core.api_token_scopes import token_has_scope

# Routes that must use interactive JWT (not personal API tokens).
_JWT_ONLY: tuple[tuple[str, str], ...] = (
    ("POST", "/api-tokens"),
    ("DELETE", "/api-tokens"),
)

_PUBLIC_PREFIXES = (
    "/health",
    "/auth/register",
    "/auth/login",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def is_public_path(path: str) -> bool:
    p = path.split("?", 1)[0]
    return any(p == prefix or p.startswith(prefix + "/") for prefix in _PUBLIC_PREFIXES if prefix != "/health") or p == "/health"


def is_jwt_only_route(method: str, path: str) -> bool:
    p = path.split("?", 1)[0].rstrip("/") or "/"
    m = method.upper()
    for req_m, prefix in _JWT_ONLY:
        if m == req_m and (p == prefix or p.startswith(prefix + "/")):
            return True
    return False


def required_scope_for_route(method: str, path: str) -> str | None:
    """Return the scope an API token must hold, or ``None`` if unrestricted."""
    p = path.split("?", 1)[0].rstrip("/") or "/"
    m = method.upper()

    if is_public_path(p):
        return None
    if p == "/auth/me":
        return None

    if is_jwt_only_route(m, p):
        return None

    if "/members" in p and m in ("POST", "PATCH", "DELETE"):
        return "admin:project"
    if m == "DELETE" and re.fullmatch(r"/projects/[^/]+", p):
        return "admin:project"
    if m == "PATCH" and re.fullmatch(r"/projects/[^/]+", p):
        return "admin:project"

    if m in ("POST", "DELETE") and any(
        seg in p for seg in ("/exec", "/terminal", "/terminal-sessions", "/restart", "/expose")
    ):
        return "runtime:operate"

    if m == "POST" and p.endswith("/deploy"):
        return "deploy:deployments"
    if m == "POST" and "/destroy" in p:
        return "deploy:deployments"

    export_markers = (
        "/integration-outputs",
        "/topology-exports",
        "/iac-export",
        "/integration",
    )
    if m == "GET" and any(marker in p for marker in export_markers):
        return "exports:read"

    if p.startswith("/topologies") and m in ("POST", "PATCH", "PUT", "DELETE"):
        return "write:topologies"

    if p.startswith("/topologies") and m == "GET":
        return "read:projects"

    if p.startswith("/projects") and m == "GET":
        return "read:projects"
    if p == "/projects" and m == "POST":
        return "read:projects"

    if p.startswith("/deployments") and m == "GET":
        return "read:projects"

    if m in ("POST", "PUT", "PATCH", "DELETE"):
        if p.startswith("/deployments") or "/traffic-tests" in p or "/failure" in p:
            return "deploy:deployments"
        if p.startswith("/topologies"):
            return "write:topologies"
        return "read:projects"

    if m == "GET":
        return "read:projects"

    return None


def ensure_api_token_scope(
    *,
    auth_method: str,
    token_scopes: set[str] | None,
    method: str,
    path: str,
) -> None:
    if auth_method != "api_token":
        return
    if is_jwt_only_route(method, path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "This route requires interactive login (JWT), not an API token.",
            },
        )
    required = required_scope_for_route(method, path)
    if required is None:
        return
    if not token_has_scope(token_scopes, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": f"API token lacks required scope: {required}",
            },
        )
