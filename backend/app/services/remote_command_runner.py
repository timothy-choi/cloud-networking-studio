"""SSH/SCP command runner for external deployments (injectable for tests)."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Protocol

from app.services.remote_ssh_runtime import ensure_ssh_client_installed, raise_for_ssh_failure


@dataclass(frozen=True)
class RemoteCommandResult:
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class RemoteHostConnection:
    host: str
    user: str
    port: int
    key_path: str
    known_hosts_file: str | None = None


def build_ssh_argv(conn: RemoteHostConnection, remote_command: str) -> list[str]:
    """Build argv for an SSH invocation (used by runner and safe debug logging)."""
    return _ssh_connection_argv(conn) + [remote_command]


def format_ssh_command_for_log(conn: RemoteHostConnection, remote_command: str) -> str:
    """Human-readable SSH command for logs (no secret key material)."""
    return shlex.join(build_ssh_argv(conn, remote_command))


def _ssh_connection_argv(conn: RemoteHostConnection) -> list[str]:
    opts = [
        "ssh",
        "-i",
        conn.key_path,
        "-p",
        str(conn.port),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "ConnectTimeout=15",
    ]
    if conn.known_hosts_file:
        opts.extend(
            [
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                f"UserKnownHostsFile={conn.known_hosts_file}",
            ]
        )
    else:
        opts.extend(["-o", "StrictHostKeyChecking=accept-new"])
    opts.append(f"{conn.user}@{conn.host}")
    return opts


def _scp_connection_argv(conn: RemoteHostConnection) -> list[str]:
    opts = [
        "scp",
        "-i",
        conn.key_path,
        "-P",
        str(conn.port),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
    ]
    if conn.known_hosts_file:
        opts.extend(
            [
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                f"UserKnownHostsFile={conn.known_hosts_file}",
            ]
        )
    else:
        opts.extend(["-o", "StrictHostKeyChecking=accept-new"])
    return opts


class RemoteCommandRunner(Protocol):
    def run_ssh(
        self,
        conn: RemoteHostConnection,
        remote_command: str,
        *,
        timeout_seconds: int = 120,
    ) -> RemoteCommandResult: ...

    def upload_files(
        self,
        conn: RemoteHostConnection,
        local_paths: list[tuple[str, str]],
        remote_dir: str,
        *,
        timeout_seconds: int = 120,
    ) -> RemoteCommandResult: ...


class SubprocessRemoteCommandRunner:
    """Run ssh/scp via subprocess (production path)."""

    def run_ssh(
        self,
        conn: RemoteHostConnection,
        remote_command: str,
        *,
        timeout_seconds: int = 120,
    ) -> RemoteCommandResult:
        ensure_ssh_client_installed()
        cmd = build_ssh_argv(conn, remote_command)
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ValueError("SSH/SCP client is missing from backend container") from exc
        return RemoteCommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")

    def upload_files(
        self,
        conn: RemoteHostConnection,
        local_paths: list[tuple[str, str]],
        remote_dir: str,
        *,
        timeout_seconds: int = 120,
    ) -> RemoteCommandResult:
        ensure_ssh_client_installed()
        mkdir = self._run_ssh_no_raise(conn, f"mkdir -p {remote_dir}", timeout_seconds=timeout_seconds)
        if not mkdir.ok:
            raise_for_ssh_failure(mkdir, context="SSH mkdir")
        scp_base = _scp_connection_argv(conn)
        outputs: list[str] = []
        errors: list[str] = []
        for local_path, remote_name in local_paths:
            remote_target = f"{conn.user}@{conn.host}:{remote_dir}/{remote_name}"
            try:
                proc = subprocess.run(
                    scp_base + [local_path, remote_target],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise ValueError("SSH/SCP client is missing from backend container") from exc
            outputs.append(proc.stdout or "")
            errors.append(proc.stderr or "")
            if proc.returncode != 0:
                result = RemoteCommandResult(proc.returncode, "\n".join(outputs), "\n".join(errors))
                raise_for_ssh_failure(result, context="SCP upload")
        return RemoteCommandResult(0, "\n".join(outputs), "\n".join(errors))

    def _run_ssh_no_raise(
        self,
        conn: RemoteHostConnection,
        remote_command: str,
        *,
        timeout_seconds: int = 120,
    ) -> RemoteCommandResult:
        cmd = build_ssh_argv(conn, remote_command)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return RemoteCommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")


_runner: RemoteCommandRunner | None = None


def get_remote_command_runner() -> RemoteCommandRunner:
    global _runner
    if _runner is None:
        _runner = SubprocessRemoteCommandRunner()
    return _runner


def set_remote_command_runner(runner: RemoteCommandRunner | None) -> None:
    global _runner
    _runner = runner
