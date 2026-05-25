"""Resolve credentials_ref to server-side SSH key paths (Step 57B)."""

from __future__ import annotations

import os


def _resolve_env_var_path(var_name: str, credentials_ref: str) -> str:
    path = (os.environ.get(var_name) or "").strip()
    if not path:
        raise ValueError(f"credentials_ref {credentials_ref} is not set on the server")
    if not os.path.isfile(path):
        raise ValueError("SSH key path is configured but not readable by backend container")
    if not os.access(path, os.R_OK):
        raise ValueError("SSH key path is configured but not readable by backend container")
    return path


def resolve_ssh_key_path(credentials_ref: str | None) -> str:
    """
    Resolve credentials_ref without loading secret material into DB or logs.

    Supported (dev/local):
    - ``env:VAR_NAME`` — path read from environment variable VAR_NAME
    - ``dev:default`` — uses CNS_REMOTE_DOCKER_SSH_KEY_PATH or CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH
    """
    ref = (credentials_ref or "").strip()
    if not ref:
        raise ValueError("credentials_ref is required for remote_docker targets")

    if ref.startswith("env:"):
        var_name = ref[4:].strip()
        if not var_name:
            raise ValueError("credentials_ref env: requires a variable name")
        return _resolve_env_var_path(var_name, f"env:{var_name}")

    if ref == "dev:default":
        for var_name in ("CNS_REMOTE_DOCKER_SSH_KEY_PATH", "CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH"):
            path = (os.environ.get(var_name) or "").strip()
            if path:
                return _resolve_env_var_path(var_name, "dev:default")
        raise ValueError("credentials_ref dev:default is not set on the server")

    raise ValueError(
        "Unsupported credentials_ref. Use env:VAR_NAME (server-side key path) or dev:default."
    )
