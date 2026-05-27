"""Tests for GCP Docker/Compose Ansible playbooks."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOKS = REPO_ROOT / "ansible_playbooks"


def test_install_docker_playbook_uses_official_docker_apt_repo():
    content = (PLAYBOOKS / "install-docker.yml").read_text(encoding="utf-8")
    assert "download.docker.com" in content
    assert "docker-ce" in content
    assert "docker-ce-cli" in content
    assert "containerd.io" in content
    assert "docker-buildx-plugin" in content
    assert "docker-compose-plugin" in content
    assert "docker.io" in content
    assert "append: true" in content
    assert "sudo docker compose version" in content


def test_install_docker_compose_playbook_installs_compose_plugin():
    content = (PLAYBOOKS / "install-docker-compose.yml").read_text(encoding="utf-8")
    assert "docker-compose-plugin" in content
    assert "docker compose version" in content
    assert "sudo docker compose version" in content
