"""SSH readiness and post-configure checks for GCP infrastructure (Step 57F)."""

from __future__ import annotations

import json
import socket
import time
from typing import Any
from uuid import UUID

from app.models.infrastructure_deployment import InfrastructureDeployment
from app.services.infra_apply_safety import is_gcp_docker_vm_apply_eligible
from app.services.remote_command_runner import RemoteHostConnection, get_remote_command_runner
from app.services.remote_credentials_service import resolve_ssh_key_path
from app.services.remote_ssh_runtime import ensure_ssh_client_installed, raise_for_ssh_failure

DEFAULT_SSH_READY_TIMEOUT_SECONDS = 300
DEFAULT_SSH_RETRY_INTERVAL_SECONDS = 5

REMOTE_DOCKER_SSH_CREDENTIALS_REF = "env:CNS_REMOTE_DOCKER_SSH_KEY_PATH"


def known_hosts_path(deployment_id: UUID | str) -> str:
    return f"/tmp/cns-known-hosts-{deployment_id}"


def ansible_ssh_common_args(deployment_id: UUID | str) -> str:
    kh = known_hosts_path(deployment_id)
    return f"-o StrictHostKeyChecking=no -o UserKnownHostsFile={kh}"


def resolve_inventory_hosts(deployment: InfrastructureDeployment) -> list[dict[str, Any]]:
    """Build host dicts from Terraform outputs (hosts list or top-level GCP fields)."""
    outputs = deployment.outputs_json or {}
    hosts = outputs.get("hosts") or []
    if isinstance(hosts, str):
        try:
            hosts = json.loads(hosts)
        except json.JSONDecodeError:
            hosts = []
    if not isinstance(hosts, list):
        hosts = []

    resolved: list[dict[str, Any]] = []
    for host in hosts:
        if not isinstance(host, dict):
            continue
        addr = host.get("public_ip") or host.get("private_ip")
        if not addr:
            continue
        resolved.append(
            {
                "name": host.get("name") or "runtime-host",
                "public_ip": str(addr),
                "ssh_user": host.get("ssh_user") or outputs.get("ssh_user") or "ubuntu",
                "ssh_port": int(host.get("ssh_port") or 22),
            }
        )

    if not resolved and is_gcp_docker_vm_apply_eligible(deployment):
        public_ip = outputs.get("public_ip")
        if public_ip:
            resolved.append(
                {
                    "name": outputs.get("instance_name") or f"{deployment.name}-vm-1",
                    "public_ip": str(public_ip),
                    "ssh_user": outputs.get("ssh_user") or deployment.variables_json.get("ssh_user") or "ubuntu",
                    "ssh_port": 22,
                }
            )
    return resolved


def _remote_connection(deployment: InfrastructureDeployment, host: dict[str, Any]) -> RemoteHostConnection:
    key_path = resolve_ssh_key_path(REMOTE_DOCKER_SSH_CREDENTIALS_REF)
    return RemoteHostConnection(
        host=str(host["public_ip"]),
        user=str(host.get("ssh_user") or "ubuntu"),
        port=int(host.get("ssh_port") or 22),
        key_path=key_path,
        known_hosts_file=known_hosts_path(deployment.id),
    )


def check_tcp_port(host: str, port: int, *, timeout_seconds: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def probe_ssh_auth(conn: RemoteHostConnection, *, timeout_seconds: int = 15) -> tuple[bool, str]:
    """Return (ok, detail) for a lightweight SSH auth probe."""
    ensure_ssh_client_installed()
    runner = get_remote_command_runner()
    result = runner.run_ssh(conn, "echo cns-ssh-ready", timeout_seconds=timeout_seconds)
    if result.ok and "cns-ssh-ready" in (result.stdout or ""):
        return True, (result.stdout or "").strip()
    detail = (result.stderr or result.stdout or f"exit {result.exit_code}").strip()
    return False, detail


def wait_for_ssh_ready(
    deployment: InfrastructureDeployment,
    *,
    timeout_seconds: int = DEFAULT_SSH_READY_TIMEOUT_SECONDS,
    interval_seconds: int = DEFAULT_SSH_RETRY_INTERVAL_SECONDS,
) -> str:
    """
    Wait until TCP/22 accepts connections and SSH auth succeeds for all inventory hosts.
    Returns a human-readable log summary. Raises ValueError on timeout.
    """
    hosts = resolve_inventory_hosts(deployment)
    if not hosts:
        raise ValueError("No host outputs available to wait for SSH readiness.")

    lines: list[str] = [
        f"[ssh-readiness] waiting up to {timeout_seconds}s for SSH on {len(hosts)} host(s)",
    ]
    deadline = time.monotonic() + timeout_seconds
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        pending: list[str] = []
        for host in hosts:
            name = str(host.get("name") or host["public_ip"])
            addr = str(host["public_ip"])
            port = int(host.get("ssh_port") or 22)
            if not check_tcp_port(addr, port):
                pending.append(f"{name} ({addr}:{port} TCP refused)")
                continue
            conn = _remote_connection(deployment, host)
            ok, detail = probe_ssh_auth(conn)
            if ok:
                lines.append(f"[ssh-readiness] attempt {attempt}: {name} SSH auth OK")
            else:
                pending.append(f"{name} ({detail})")

        if not pending:
            lines.append(f"[ssh-readiness] all hosts ready after {attempt} attempt(s)")
            return "\n".join(lines)

        lines.append(f"[ssh-readiness] attempt {attempt}: not ready — {'; '.join(pending)}")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval_seconds, remaining))

    raise ValueError(
        "SSH readiness timed out after "
        f"{timeout_seconds}s. Last status: {lines[-1] if lines else 'unknown'}"
    )


def verify_remote_docker(deployment: InfrastructureDeployment) -> str:
    """Run docker --version and docker compose version over SSH. Returns combined log text."""
    hosts = resolve_inventory_hosts(deployment)
    if not hosts:
        raise ValueError("No host outputs available to verify Docker installation.")

    lines: list[str] = ["[docker-verify] checking Docker on provisioned host(s)"]
    for host in hosts:
        conn = _remote_connection(deployment, host)
        name = str(host.get("name") or host["public_ip"])
        runner = get_remote_command_runner()

        docker_result = runner.run_ssh(conn, "docker --version", timeout_seconds=60)
        if not docker_result.ok:
            raise_for_ssh_failure(docker_result, context=f"docker --version on {name}")
        docker_out = (docker_result.stdout or docker_result.stderr or "").strip()
        if not docker_out:
            raise ValueError(f"docker --version returned no output on {name}")
        lines.append(f"[docker-verify] {name}: {docker_out}")

        compose_result = runner.run_ssh(conn, "docker compose version", timeout_seconds=60)
        if not compose_result.ok:
            raise_for_ssh_failure(compose_result, context=f"docker compose version on {name}")
        compose_out = (compose_result.stdout or compose_result.stderr or "").strip()
        if not compose_out:
            raise ValueError(f"docker compose version returned no output on {name}")
        lines.append(f"[docker-verify] {name}: {compose_out}")

    lines.append("[docker-verify] Docker and Docker Compose verified")
    return "\n".join(lines)
