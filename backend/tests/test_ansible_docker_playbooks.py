"""Tests for GCP Docker/Compose Ansible playbooks."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYBOOKS = REPO_ROOT / "ansible_playbooks"

PLAYBOOK_FILES = (
    "install-docker.yml",
    "install-docker-compose.yml",
    "cns-runtime-dirs.yml",
)

# ansible.builtin.command with shell builtins (e.g. command -v) fails at runtime.
COMMAND_BUILTIN_PATTERN = re.compile(
    r"ansible\.builtin\.command:\s*command\s+-v\b",
    re.MULTILINE,
)


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
    assert "which docker" in content
    assert "sudo docker compose version" in content


def test_install_docker_compose_playbook_installs_compose_plugin():
    content = (PLAYBOOKS / "install-docker-compose.yml").read_text(encoding="utf-8")
    assert "docker-compose-plugin" in content
    assert "which docker" in content
    assert "docker compose version" in content
    assert "sudo docker compose version" in content


def test_cns_runtime_dirs_playbook_owns_external_deployment_workdir_for_ssh_user():
    content = (PLAYBOOKS / "cns-runtime-dirs.yml").read_text(encoding="utf-8")
    assert "/opt/cns-external-deployments" in content
    assert 'owner: "{{ ansible_user }}"' in content
    assert 'group: "{{ ansible_user }}"' in content


def test_ansible_playbooks_do_not_use_command_module_with_shell_builtins():
    offenders: list[str] = []
    for filename in PLAYBOOK_FILES:
        path = PLAYBOOKS / filename
        content = path.read_text(encoding="utf-8")
        if COMMAND_BUILTIN_PATTERN.search(content):
            offenders.append(filename)
    assert offenders == [], f"shell builtins used with command module: {offenders}"
