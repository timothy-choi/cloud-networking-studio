"""API token scope definitions (Step 53D)."""

from __future__ import annotations

import json

ALL_API_TOKEN_SCOPES: frozenset[str] = frozenset(
    {
        "read:projects",
        "write:topologies",
        "deploy:deployments",
        "runtime:operate",
        "exports:read",
        "admin:project",
    }
)

SCOPE_LABELS: dict[str, str] = {
    "read:projects": "Read projects, topologies, and deployments",
    "write:topologies": "Create and edit topologies, nodes, and links",
    "deploy:deployments": "Deploy and destroy runtime workloads",
    "runtime:operate": "Terminal, safe exec, restart, and expose services",
    "exports:read": "Download integration outputs and topology exports",
    "admin:project": "Manage project members and settings",
}


def normalize_scopes(raw: list[str] | None) -> list[str] | None:
    """Validate and dedupe scopes. ``None`` means full access (legacy tokens)."""
    if raw is None:
        return None
    out: list[str] = []
    seen: set[str] = set()
    for s in raw:
        scope = (s or "").strip()
        if not scope or scope in seen:
            continue
        if scope not in ALL_API_TOKEN_SCOPES:
            raise ValueError(f"Unknown scope: {scope}")
        seen.add(scope)
        out.append(scope)
    if not out:
        raise ValueError("At least one scope is required when scopes are specified")
    return out


def serialize_scopes(scopes: list[str] | None) -> str | None:
    if scopes is None:
        return None
    return json.dumps(scopes)


def parse_stored_scopes(raw: str | None) -> set[str] | None:
    """Return ``None`` for full-access tokens (unset or empty in DB)."""
    if raw is None or not str(raw).strip():
        return None
    text = str(raw).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        parts = {p.strip() for p in text.split(",") if p.strip()}
        return parts or None
    if not isinstance(data, list):
        return None
    return {str(x) for x in data if str(x) in ALL_API_TOKEN_SCOPES} or None


def token_has_scope(token_scopes: set[str] | None, required: str) -> bool:
    if token_scopes is None:
        return True
    return required in token_scopes
