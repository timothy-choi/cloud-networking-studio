"""Tests for production GCP infrastructure credential deploy wiring."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CREDENTIALS_SH = REPO / "scripts" / "infra_deployment_credentials.sh"
PROD_DEPLOY_SH = REPO / "scripts" / "prod_deploy_remote.sh"
PROD_COMPOSE = REPO / "docker-compose.prod.yml"
PROD_WORKFLOW = REPO / ".github" / "workflows" / "deploy-production.yml"


def _source_credentials_bash(*statements: str) -> subprocess.CompletedProcess[str]:
    body = "\n".join([f"source '{CREDENTIALS_SH}'", *statements])
    return subprocess.run(
        ["bash", "-c", body],
        capture_output=True,
        text=True,
        check=False,
    )


def test_prod_compose_backend_and_runner_include_infra_credential_defaults():
    compose_text = PROD_COMPOSE.read_text(encoding="utf-8")
    gcp_default = "GOOGLE_APPLICATION_CREDENTIALS: ${GOOGLE_APPLICATION_CREDENTIALS:-/opt/cns/secrets/gcp-terraform-sa.json}"
    ssh_default = "CNS_REMOTE_DOCKER_SSH_KEY_PATH: ${CNS_REMOTE_DOCKER_SSH_KEY_PATH:-/opt/cns/secrets/gcp-remote-docker-key}"
    pub_default = "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH: ${CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH:-/opt/cns/secrets/gcp-remote-docker-key.pub}"
    assert compose_text.count(gcp_default) >= 2
    assert compose_text.count(ssh_default) >= 2
    assert compose_text.count(pub_default) >= 2
    assert compose_text.count("/opt/cns/secrets:/opt/cns/secrets:ro") >= 2


def test_prod_deploy_script_sources_shared_credentials_helpers():
    text = PROD_DEPLOY_SH.read_text(encoding="utf-8")
    assert "infra_deployment_credentials.sh" in text
    assert "ensure_infra_deployment_credential_env_lines" in text
    assert "verify_host_infra_credential_files" in text
    assert "verify_infra_credentials_in_containers" in text


def test_prod_workflow_passes_infra_credential_env_to_ssh():
    workflow = PROD_WORKFLOW.read_text(encoding="utf-8")
    assert "prod_deploy_remote.sh" in workflow
    assert "GOOGLE_APPLICATION_CREDENTIALS" in workflow
    assert "CNS_REMOTE_DOCKER_SSH_KEY_PATH" in workflow
    assert "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH" in workflow


def test_infra_credentials_resolve_preserves_existing_env(tmp_path: Path):
    existing = tmp_path / ".env"
    existing.write_text(
        "GOOGLE_APPLICATION_CREDENTIALS=/custom/gcp.json\n"
        "CNS_REMOTE_DOCKER_SSH_KEY_PATH=/custom/key\n"
        "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH=/custom/key.pub\n",
        encoding="utf-8",
    )
    proc = _source_credentials_bash(
        f'echo "$(resolve_google_application_credentials_path "{existing}")"',
        f'echo "$(resolve_cns_remote_docker_ssh_key_path "{existing}")"',
        f'echo "$(resolve_cns_remote_docker_ssh_public_key_path "{existing}")"',
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines() == [
        "/custom/gcp.json",
        "/custom/key",
        "/custom/key.pub",
    ]


def test_infra_credentials_resolve_production_defaults_when_missing():
    proc = _source_credentials_bash(
        'echo "$(resolve_google_application_credentials_path "")"',
        'echo "$(resolve_cns_remote_docker_ssh_key_path "")"',
        'echo "$(resolve_cns_remote_docker_ssh_public_key_path "")"',
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines() == [
        "/opt/cns/secrets/gcp-terraform-sa.json",
        "/opt/cns/secrets/gcp-remote-docker-key",
        "/opt/cns/secrets/gcp-remote-docker-key.pub",
    ]


def test_infra_credentials_env_lines_rewrite_single_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GOOGLE_APPLICATION_CREDENTIALS=/old/gcp.json\n"
        "GOOGLE_APPLICATION_CREDENTIALS=/stale/gcp.json\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    proc = _source_credentials_bash(
        'ENV_FILE=".env"',
        'GOOGLE_APPLICATION_CREDENTIALS="/opt/cns/secrets/gcp-terraform-sa.json"',
        'CNS_REMOTE_DOCKER_SSH_KEY_PATH="/opt/cns/secrets/gcp-remote-docker-key"',
        'CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH="/opt/cns/secrets/gcp-remote-docker-key.pub"',
        "ensure_infra_deployment_credential_env_lines",
    )
    assert proc.returncode == 0, proc.stderr
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines.count("GOOGLE_APPLICATION_CREDENTIALS=/opt/cns/secrets/gcp-terraform-sa.json") == 1
    assert "CNS_REMOTE_DOCKER_SSH_KEY_PATH=/opt/cns/secrets/gcp-remote-docker-key" in lines
    assert "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH=/opt/cns/secrets/gcp-remote-docker-key.pub" in lines


def test_prod_compose_config_renders_infra_credentials_with_env_file(tmp_path: Path):
    env_file = tmp_path / ".env.prod.compose-test"
    env_file.write_text(
        "\n".join(
            [
                "GOOGLE_APPLICATION_CREDENTIALS=/opt/cns/secrets/gcp-terraform-sa.json",
                "CNS_REMOTE_DOCKER_SSH_KEY_PATH=/opt/cns/secrets/gcp-remote-docker-key",
                "CNS_REMOTE_DOCKER_SSH_PUBLIC_KEY_PATH=/opt/cns/secrets/gcp-remote-docker-key.pub",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.prod.yml",
            "--env-file",
            str(env_file),
            "config",
        ],
        cwd=REPO,
        env={**__import__("os").environ, "GOOGLE_APPLICATION_CREDENTIALS": "", "CNS_REMOTE_DOCKER_SSH_KEY_PATH": ""},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("GOOGLE_APPLICATION_CREDENTIALS: /opt/cns/secrets/gcp-terraform-sa.json") >= 2
    assert proc.stdout.count("CNS_REMOTE_DOCKER_SSH_KEY_PATH: /opt/cns/secrets/gcp-remote-docker-key") >= 2
