"""Resolve credentials_ref to server-side SSH key paths (Step 57B)."""

from __future__ import annotations

import os


def resolve_ssh_key_path(credentials_ref: str | None) -> str:
    """
    Resolve credentials_ref without loading secret material into DB or logs.

    Supported (dev/local):
    - ``env:VAR_NAME`` — path read from environment variable VAR_NAME
    - ``dev:default`` — uses CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH
    """
    ref = (credentials_ref or "").strip()
    if not ref:
        raise ValueError("credentials_ref is required for remote_docker targets")

    if ref.startswith("env:"):
        var_name = ref[4:].strip()
        if not var_name:
            raise ValueError("credentials_ref env: requires a variable name")
        path = (os.environ.get(var_name) or "").strip()
        if not path:
            raise ValueError(f"credentials_ref env:{var_name} is not set on the server")
        if not os.path.isfile(path):
            raise ValueError(f"SSH key path from env:{var_name} does not exist")
        return path

    if ref == "dev:default":
        path = (os.environ.get("CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH") or "").strip()
        if not path:
            raise ValueError(
                "credentials_ref dev:default requires CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH on the server"
            )
        if not os.path.isfile(path):
            raise ValueError("CNS_EXTERNAL_DEPLOY_SSH_KEY_PATH does not point to an existing file")
        return path

    raise ValueError(
        "Unsupported credentials_ref. Use env:VAR_NAME (server-side key path) or dev:default."
    )
