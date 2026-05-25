"""Whitelisted infrastructure templates and Ansible playbooks (Step 57C)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES_ROOT = Path(os.environ.get("CNS_INFRA_TEMPLATES_ROOT", REPO_ROOT / "infra_templates"))
PLAYBOOKS_ROOT = Path(os.environ.get("CNS_ANSIBLE_PLAYBOOKS_ROOT", REPO_ROOT / "ansible_playbooks"))
REGISTRY_PATH = TEMPLATES_ROOT / "registry.json"


@dataclass(frozen=True)
class InfraTemplateSpec:
    template_id: str
    description: str
    supported_providers: tuple[str, ...]
    terraform_dir: str
    ansible_playbooks: tuple[str, ...]

    @property
    def terraform_path(self) -> Path:
        return TEMPLATES_ROOT / self.terraform_dir


@dataclass(frozen=True)
class AnsiblePlaybookSpec:
    playbook_id: str
    description: str
    filename: str

    @property
    def path(self) -> Path:
        return PLAYBOOKS_ROOT / self.filename


@lru_cache(maxsize=1)
def _load_registry() -> dict:
    if not REGISTRY_PATH.is_file():
        return {"templates": {}, "playbooks": {}}
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    return data


def list_templates() -> list[InfraTemplateSpec]:
    reg = _load_registry()
    items: list[InfraTemplateSpec] = []
    for template_id, spec in (reg.get("templates") or {}).items():
        items.append(
            InfraTemplateSpec(
                template_id=template_id,
                description=str(spec.get("description") or ""),
                supported_providers=tuple(spec.get("supported_providers") or []),
                terraform_dir=str(spec.get("terraform_dir") or template_id),
                ansible_playbooks=tuple(spec.get("ansible_playbooks") or []),
            )
        )
    return items


def get_template(template_id: str) -> InfraTemplateSpec:
    for item in list_templates():
        if item.template_id == template_id:
            return item
    raise ValueError(f"Unsupported template_id: {template_id}")


def list_playbooks() -> list[AnsiblePlaybookSpec]:
    reg = _load_registry()
    items: list[AnsiblePlaybookSpec] = []
    for playbook_id, spec in (reg.get("playbooks") or {}).items():
        items.append(
            AnsiblePlaybookSpec(
                playbook_id=playbook_id,
                description=str(spec.get("description") or ""),
                filename=str(spec.get("file") or f"{playbook_id}.yml"),
            )
        )
    return items


def get_playbook(playbook_id: str) -> AnsiblePlaybookSpec:
    for item in list_playbooks():
        if item.playbook_id == playbook_id:
            return item
    raise ValueError(f"Unsupported playbook_id: {playbook_id}")


def validate_template_provider(template_id: str, provider: str) -> None:
    spec = get_template(template_id)
    if provider not in spec.supported_providers:
        raise ValueError(
            f"Provider '{provider}' is not supported for template '{template_id}'. "
            f"Supported: {', '.join(spec.supported_providers)}"
        )


def assert_template_on_disk(template_id: str) -> Path:
    spec = get_template(template_id)
    path = spec.terraform_path
    if not path.is_dir():
        raise ValueError(f"Template directory missing on disk: {path}")
    if not (path / "main.tf").is_file():
        raise ValueError(f"Template {template_id} missing main.tf")
    return path


def assert_playbook_on_disk(playbook_id: str) -> Path:
    spec = get_playbook(playbook_id)
    path = spec.path
    if not path.is_file():
        raise ValueError(f"Playbook file missing on disk: {path}")
    return path
