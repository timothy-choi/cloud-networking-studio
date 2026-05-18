"""Persist API base URL and bearer token for ``cns``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_API_BASE = "http://localhost/api"


def default_config_path() -> Path:
    override = (os.environ.get("CNS_CONFIG") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "cns" / "config.json"


def load_config() -> dict[str, Any]:
    p = default_config_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(data: dict[str, Any]) -> None:
    p = default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def effective_base_url(cli_override: str | None) -> str:
    """
    API root precedence:

    1. ``--base-url``
    2. ``CNS_BASE_URL`` (``CNS_API_BASE_URL`` accepted as legacy alias)
    3. saved config ``api_base``
    4. default ``http://localhost/api`` (Docker Compose + Caddy)
    """
    return (
        (cli_override or "").strip()
        or (
            os.environ.get("CNS_BASE_URL")
            or os.environ.get("CNS_API_BASE_URL")
            or ""
        )
        .strip()
        .rstrip("/")
        or (load_config().get("api_base") or "").strip().rstrip("/")
        or DEFAULT_API_BASE
    )


def effective_token(cli_override: str | None) -> str | None:
    t = (cli_override or "").strip() or (os.environ.get("CNS_TOKEN") or "").strip()
    if t:
        return t
    return (load_config().get("token") or "").strip() or None
