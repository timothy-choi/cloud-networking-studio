"""Resolve CNS remote Docker SSH public key for GCP infra provisioning (Step 57E)."""

from __future__ import annotations

import os
import re

from pathlib import Path

CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_ENV = "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH"
DEFAULT_SSH_PUBLIC_KEY_PATH = "/opt/cns/secrets/gcp-remote-docker-key.pub"

_SSH_PUBLIC_KEY_PREFIXES = ("ssh-rsa ", "ssh-ed25519 ", "ecdsa-sha2-", "ssh-dss ")


def resolve_remote_docker_ssh_public_key_path() -> str:
    path = (os.environ.get(CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_ENV) or "").strip()
    if not path:
        path = DEFAULT_SSH_PUBLIC_KEY_PATH
    return path


def resolve_remote_docker_ssh_public_key() -> str:
    """
    Load the SSH public key material for Terraform instance metadata injection.
    Never log the returned value.
    """
    path = resolve_remote_docker_ssh_public_key_path()
    key_path = Path(path)
    if not key_path.is_file():
        raise ValueError("CNS remote Docker SSH public key is not configured.")
    try:
        content = key_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("CNS remote Docker SSH public key is not configured.") from exc

    line = content.strip().splitlines()[0].strip() if content.strip() else ""
    if not line or not _looks_like_ssh_public_key(line):
        raise ValueError("CNS remote Docker SSH public key is not configured.")
    return line


def _looks_like_ssh_public_key(line: str) -> bool:
    if any(line.startswith(prefix) for prefix in _SSH_PUBLIC_KEY_PREFIXES):
        return True
    return bool(re.match(r"^ssh-[a-z0-9-]+ ", line))
