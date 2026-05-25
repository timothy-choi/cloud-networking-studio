"""SSH/SCP runtime checks for remote_docker external deployments."""

from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)

SSH_CLIENT_STARTUP_MESSAGE = (
    "SSH client is not installed in backend container. Install openssh-client."
)
SSH_CLIENT_MISSING_MESSAGE = "SSH/SCP client is missing from backend container"
SSH_PERMISSION_DENIED_MESSAGE = (
    "SSH permission denied. Check public key is installed for ssh_user on target host."
)


def ssh_client_status() -> tuple[bool, str | None]:
    """Return (ok, error_message). Never raises."""
    missing: list[str] = []
    if shutil.which("ssh") is None:
        missing.append("ssh")
    if shutil.which("scp") is None:
        missing.append("scp")
    if missing:
        return False, SSH_CLIENT_STARTUP_MESSAGE
    return True, None


def log_remote_ssh_runtime_status() -> None:
    """Log SSH client availability at startup without failing unrelated routes."""
    ok, message = ssh_client_status()
    if ok:
        logger.info("remote_docker SSH runtime ready (ssh and scp available)")
        return
    logger.warning("%s Remote Docker validate/apply will fail until openssh-client is installed.", message)


def ensure_ssh_client_installed() -> None:
    """Raise ValueError when ssh/scp binaries are unavailable."""
    ok, message = ssh_client_status()
    if not ok:
        raise ValueError(SSH_CLIENT_MISSING_MESSAGE)


def raise_for_ssh_failure(result, *, context: str = "SSH") -> None:
    """Map subprocess SSH/SCP failures to actionable job errors."""
    if result.ok:
        return
    combined = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
    if "permission denied" in combined:
        raise ValueError(SSH_PERMISSION_DENIED_MESSAGE)
    raise ValueError(f"Remote check failed ({context}): exit {result.exit_code}")
