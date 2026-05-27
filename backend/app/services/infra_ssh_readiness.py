"""SSH readiness and post-configure checks for GCP infrastructure (Step 57F)."""

from __future__ import annotations

import json
import socket
import time
from typing import Any
from uuid import UUID

from app.models.infrastructure_deployment import InfrastructureDeployment
from app.services.infra_apply_safety import is_gcp_docker_vm_apply_eligible
from app.services.remote_command_runner import RemoteCommandResult, RemoteHostConnection, get_remote_command_runner
from app.services.remote_credentials_service import resolve_ssh_key_path
from app.services.remote_ssh_runtime import ensure_ssh_client_installed, raise_for_ssh_failure

DEFAULT_SSH_READY_TIMEOUT_SECONDS = 300
DEFAULT_SSH_RETRY_INTERVAL_SECONDS = 5

REMOTE_DOCKER_SSH_CREDENTIALS_REF = "env:CNS_REMOTE_DOCKER_SSH_KEY_PATH"

REMOTE_DOCKER_EXTERNAL_WORKDIR = "/opt/cns-external-deployments"

REMOTE_WORKDIR_NOT_WRITABLE_MESSAGE = (
    "remote_workdir is not writable by ssh_user "
    f"(expected writable directory: {REMOTE_DOCKER_EXTERNAL_WORKDIR})"
)

WORKDIR_VERIFY_COMMAND = (
    f"test -d {REMOTE_DOCKER_EXTERNAL_WORKDIR} && "
    f"test -w {REMOTE_DOCKER_EXTERNAL_WORKDIR} && "
    f"mkdir -p {REMOTE_DOCKER_EXTERNAL_WORKDIR}/.cns-write-test && "
    f"rm -rf {REMOTE_DOCKER_EXTERNAL_WORKDIR}/.cns-write-test"
)

COMPOSE_PLUGIN_PATH_CMD = (
    "sh -c 'for candidate in "
    "/usr/libexec/docker/cli-plugins/docker-compose "
    "/usr/local/lib/docker/cli-plugins/docker-compose; do "
    'if test -x "$candidate"; then readlink -f "$candidate"; exit 0; fi; done; '
    "echo compose-plugin-path-not-found'"
)


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


def _command_output(result: RemoteCommandResult) -> str:
    return (result.stdout or result.stderr or "").strip()


def _should_try_sudo(result: RemoteCommandResult) -> bool:
    if result.ok:
        return False
    text = _command_output(result).lower()
    return (
        "permission denied" in text
        or "got permission denied" in text
        or "cannot connect to the docker daemon" in text
        or result.exit_code in {1, 126, 127}
    )


def _run_docker_command(
    runner,
    conn: RemoteHostConnection,
    command: str,
    *,
    host_name: str,
    timeout_seconds: int = 60,
) -> tuple[str, bool]:
    """Run a docker command as ssh_user, falling back to sudo on permission errors."""
    result = runner.run_ssh(conn, command, timeout_seconds=timeout_seconds)
    if result.ok:
        output = _command_output(result)
        if output:
            return output, False
        raise ValueError(f"{command} returned no output on {host_name}")

    if not _should_try_sudo(result):
        raise_for_ssh_failure(result, context=f"{command} on {host_name}")

    sudo_result = runner.run_ssh(conn, f"sudo {command}", timeout_seconds=timeout_seconds)
    if not sudo_result.ok:
        raise_for_ssh_failure(sudo_result, context=f"sudo {command} on {host_name}")
    output = _command_output(sudo_result)
    if not output:
        raise ValueError(f"sudo {command} returned no output on {host_name}")
    return output, True


def verify_remote_docker(deployment: InfrastructureDeployment) -> str:
    """Run docker --version and docker compose version over SSH. Returns combined log text."""
    hosts = resolve_inventory_hosts(deployment)
    if not hosts:
        raise ValueError("No host outputs available to verify Docker installation.")

    lines: list[str] = ["[docker-verify] checking Docker on provisioned host(s)"]
    runner = get_remote_command_runner()

    for host in hosts:
        conn = _remote_connection(deployment, host)
        name = str(host.get("name") or host["public_ip"])

        docker_path_result = runner.run_ssh(conn, "which docker", timeout_seconds=30)
        docker_path = _command_output(docker_path_result) if docker_path_result.ok else "unknown"
        lines.append(f"[docker-verify] {name}: docker binary path={docker_path}")

        compose_path_result = runner.run_ssh(conn, COMPOSE_PLUGIN_PATH_CMD, timeout_seconds=30)
        compose_path = _command_output(compose_path_result) if compose_path_result.ok else "unknown"
        lines.append(f"[docker-verify] {name}: docker compose plugin path={compose_path}")

        docker_out, docker_sudo = _run_docker_command(
            runner,
            conn,
            "docker --version",
            host_name=name,
        )
        lines.append(
            f"[docker-verify] {name}: docker version={docker_out}"
            + (" (sudo fallback)" if docker_sudo else "")
        )

        compose_out, compose_sudo = _run_docker_command(
            runner,
            conn,
            "docker compose version",
            host_name=name,
        )
        lines.append(
            f"[docker-verify] {name}: docker compose version={compose_out}"
            + (" (sudo fallback)" if compose_sudo else "")
        )

    lines.append("[docker-verify] Docker and Docker Compose verified")
    return "\n".join(lines)


def verify_remote_workdir(deployment: InfrastructureDeployment) -> str:
    """Verify external deployment workdir exists and is writable by ssh_user."""
    hosts = resolve_inventory_hosts(deployment)
    if not hosts:
        raise ValueError("No host outputs available to verify remote workdir.")

    lines: list[str] = [
        f"[workdir-verify] checking ssh_user write access to {REMOTE_DOCKER_EXTERNAL_WORKDIR}",
    ]
    ensure_ssh_client_installed()
    runner = get_remote_command_runner()

    for host in hosts:
        conn = _remote_connection(deployment, host)
        name = str(host.get("name") or host["public_ip"])
        ssh_user = str(host.get("ssh_user") or "ubuntu")
        lines.append(
            f"[workdir-verify] {name}: ssh_user={ssh_user} path={REMOTE_DOCKER_EXTERNAL_WORKDIR}"
        )

        result = runner.run_ssh(conn, WORKDIR_VERIFY_COMMAND, timeout_seconds=60)
        if not result.ok:
            detail = _command_output(result) or f"exit {result.exit_code}"
            lines.append(f"[workdir-verify] {name}: failed — {detail}")
            raise ValueError(REMOTE_WORKDIR_NOT_WRITABLE_MESSAGE)
        lines.append(f"[workdir-verify] {name}: directory exists, writable, write test passed")

    lines.append("[workdir-verify] remote workdir verified")
    return "\n".join(lines)
