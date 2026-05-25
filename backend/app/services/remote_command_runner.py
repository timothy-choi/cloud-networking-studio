"""SSH/SCP command runner for external deployments (injectable for tests)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol


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

    def _ssh_base(self, conn: RemoteHostConnection) -> list[str]:
        return [
            "ssh",
            "-i",
            conn.key_path,
            "-p",
            str(conn.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=15",
            f"{conn.user}@{conn.host}",
        ]

    def run_ssh(
        self,
        conn: RemoteHostConnection,
        remote_command: str,
        *,
        timeout_seconds: int = 120,
    ) -> RemoteCommandResult:
        cmd = self._ssh_base(conn) + [remote_command]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return RemoteCommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")

    def upload_files(
        self,
        conn: RemoteHostConnection,
        local_paths: list[tuple[str, str]],
        remote_dir: str,
        *,
        timeout_seconds: int = 120,
    ) -> RemoteCommandResult:
        mkdir = self.run_ssh(conn, f"mkdir -p {remote_dir}", timeout_seconds=timeout_seconds)
        if not mkdir.ok:
            return mkdir
        scp_base = [
            "scp",
            "-i",
            conn.key_path,
            "-P",
            str(conn.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        outputs: list[str] = []
        errors: list[str] = []
        for local_path, remote_name in local_paths:
            remote_target = f"{conn.user}@{conn.host}:{remote_dir}/{remote_name}"
            proc = subprocess.run(
                scp_base + [local_path, remote_target],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            outputs.append(proc.stdout or "")
            errors.append(proc.stderr or "")
            if proc.returncode != 0:
                return RemoteCommandResult(proc.returncode, "\n".join(outputs), "\n".join(errors))
        return RemoteCommandResult(0, "\n".join(outputs), "\n".join(errors))


_runner: RemoteCommandRunner | None = None


def get_remote_command_runner() -> RemoteCommandRunner:
    global _runner
    if _runner is None:
        _runner = SubprocessRemoteCommandRunner()
    return _runner


def set_remote_command_runner(runner: RemoteCommandRunner | None) -> None:
    global _runner
    _runner = runner
