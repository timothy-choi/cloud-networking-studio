"""Persist API base URL and bearer token for ``cns``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


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
    return (
        (cli_override or "").strip()
        or (os.environ.get("CNS_API_BASE_URL") or "").strip().rstrip("/")
        or (load_config().get("api_base") or "").strip().rstrip("/")
        or "http://127.0.0.1:8000"
    )


def effective_token(cli_override: str | None) -> str | None:
    t = (cli_override or "").strip() or (os.environ.get("CNS_TOKEN") or "").strip()
    if t:
        return t
    return (load_config().get("token") or "").strip() or None
