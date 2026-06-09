"""Security helpers for infrastructure deployments (Step 57C/57D)."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from app.core.secret_masking import scrub_sensitive_dict

_FORBIDDEN_VAR_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "private_key",
        "credentials",
        "aws_secret_access_key",
        "gcp_credentials_json",
    }
)

_SAFE_KEY_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]{0,63}$")
_PATH_TRAVERSAL = re.compile(r"\.\.|~|//")
_CIDR_PATTERN = re.compile(
    r"^(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}$|^[0-9a-fA-F:]+/\d{1,3}$"
)
_REGION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{0,31}$")
_MACHINE_TYPE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-\.]{0,63}$")
_GCP_PROJECT_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")
_INSTANCE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{0,61}[a-z0-9]$")
_GCP_LABEL_VALUE_PATTERN = re.compile(r"^[a-z](?:[a-z0-9_-]{0,61}[a-z0-9])?$")

_TEMPLATE_VAR_ALLOWLIST: dict[tuple[str, str], frozenset[str]] = {
    ("local-mock", "local"): frozenset({"region", "vm_count", "deployment_name", "ssh_user"}),
    ("local-mock", "mock"): frozenset({"region", "vm_count", "deployment_name", "ssh_user"}),
    ("docker-vm", "local"): frozenset({"region", "vm_count", "deployment_name", "ssh_user"}),
    ("docker-vm", "mock"): frozenset({"region", "vm_count", "deployment_name", "ssh_user"}),
    (
        "docker-vm",
        "gcp",
    ): frozenset(
        {
            "project_id",
            "region",
            "zone",
            "machine_type",
            "network_name",
            "instance_name",
            "ssh_user",
            "allowed_ssh_cidr",
            "allowed_app_cidr",
            "tags",
            "vm_count",
            "deployment_name",
            "cns_template",
            "cns_provider",
        }
    ),
    (
        "docker-vm",
        "aws",
    ): frozenset(
        {
            "region",
            "instance_type",
            "vpc_id",
            "subnet_id",
            "key_name",
            "allowed_ssh_cidr",
            "allowed_app_cidr",
            "tags",
            "vm_count",
            "deployment_name",
        }
    ),
    ("gcp-vm", "gcp"): frozenset({"region", "vm_count", "deployment_name", "ssh_user"}),
    ("aws-ec2", "aws"): frozenset({"region", "vm_count", "deployment_name", "ssh_user"}),
}

REAL_CLOUD_PROVIDERS = frozenset({"gcp", "aws"})


def sanitize_gcp_label_value(value: str, *, max_length: int = 63) -> str:
    """Normalize a human-readable name for GCP resource label values."""
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-_")
    if not text:
        text = "cns-deployment"
    if not text[0].isalpha():
        text = f"c-{text}"
    text = text[:max_length].rstrip("-_")
    if not text:
        return "cns-deployment"
    if not text[0].isalpha():
        text = f"c-{text}"[:max_length].rstrip("-_")
    if not text or not text[-1].isalnum():
        text = text.rstrip("-_") or "cns-deployment"
    if not _GCP_LABEL_VALUE_PATTERN.match(text):
        return "cns-deployment"
    return text


def sanitize_gcp_resource_name(value: str, *, prefix: str = "cns-", max_length: int = 62) -> str:
    """Normalize a human-readable name for GCP compute/firewall resource identifiers."""
    base = sanitize_gcp_label_value(value, max_length=max_length)
    if not base.startswith(prefix):
        base = f"{prefix}{base}"[:max_length].rstrip("-")
    if not _INSTANCE_NAME_PATTERN.match(base):
        fallback = f"{prefix}stack"[:max_length]
        return fallback if _INSTANCE_NAME_PATTERN.match(fallback) else "cns-stack"
    return base


def gcp_terraform_label_variables(
    *,
    deployment_name: str,
    template_id: str,
    provider: str,
) -> dict[str, str]:
    """Sanitized Terraform variables used for GCP resource labels."""
    return {
        "deployment_name": sanitize_gcp_label_value(deployment_name),
        "cns_template": sanitize_gcp_label_value(template_id),
        "cns_provider": sanitize_gcp_label_value(provider),
    }


def sanitize_variables(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Allow only safe scalar variables for template execution."""
    if not raw:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        key_str = str(key).strip()
        if not _SAFE_KEY_PATTERN.match(key_str):
            raise ValueError(f"Invalid variable key: {key_str}")
        lower = key_str.lower()
        if any(part in lower for part in _FORBIDDEN_VAR_KEYS):
            raise ValueError(f"Sensitive variable keys must use credentials_ref, not variables: {key_str}")
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and _PATH_TRAVERSAL.search(value):
                raise ValueError(f"Invalid path-like variable value for {key_str}")
            cleaned[key_str] = value
        else:
            raise ValueError(f"Variable {key_str} must be a scalar")
    return scrub_sensitive_dict(cleaned)


def validate_template_variables(template_id: str, provider: str, variables: dict[str, Any]) -> None:
    """Enforce per-template variable allowlists and value constraints."""
    allowlist = _TEMPLATE_VAR_ALLOWLIST.get((template_id, provider))
    if allowlist is None:
        raise ValueError(f"Unsupported template/provider combination: {template_id}/{provider}")

    unknown = set(variables.keys()) - allowlist
    if unknown:
        raise ValueError(f"Unknown variables for {template_id}/{provider}: {', '.join(sorted(unknown))}")

    vm_count = variables.get("vm_count", 1)
    if vm_count is not None:
        try:
            count = int(vm_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("vm_count must be an integer between 1 and 10") from exc
        if count < 1 or count > 10:
            raise ValueError("vm_count must be between 1 and 10")

    if provider == "gcp" and template_id == "docker-vm":
        _validate_gcp_docker_vm(variables)
    elif provider == "aws" and template_id == "docker-vm":
        _validate_aws_docker_vm(variables)


def validate_gcp_project_id(project_id: str) -> str:
    value = str(project_id or "").strip()
    if not _GCP_PROJECT_PATTERN.match(value):
        raise ValueError("project_id must be a valid GCP project ID")
    return value


def _validate_gcp_docker_vm(variables: dict[str, Any]) -> None:
    validate_gcp_project_id(str(variables.get("project_id") or ""))

    region = str(variables.get("region") or "").strip()
    zone = str(variables.get("zone") or "").strip()
    if not _REGION_PATTERN.match(region):
        raise ValueError("region must be a safe lowercase identifier")
    if not _REGION_PATTERN.match(zone) or not zone.startswith(f"{region}-"):
        raise ValueError("zone must be a safe identifier within the selected region")

    machine_type = str(variables.get("machine_type") or "e2-medium").strip()
    if not _MACHINE_TYPE_PATTERN.match(machine_type):
        raise ValueError("machine_type format is invalid")

    instance_name = str(variables.get("instance_name") or "").strip()
    if not _INSTANCE_NAME_PATTERN.match(instance_name):
        raise ValueError("instance_name must be a valid GCP resource name")

    network_name = str(variables.get("network_name") or "default").strip()
    if not _REGION_PATTERN.match(network_name.replace("_", "-")):
        raise ValueError("network_name format is invalid")

    _validate_cidr("allowed_ssh_cidr", variables.get("allowed_ssh_cidr"))
    _validate_cidr("allowed_app_cidr", variables.get("allowed_app_cidr"))

    tags = str(variables.get("tags") or "cns-docker-vm").strip()
    for tag in tags.split(","):
        tag = tag.strip()
        if tag and not re.match(r"^[a-z][a-z0-9\-]{0,62}$", tag):
            raise ValueError("tags must be comma-separated lowercase identifiers")

    deployment_name = sanitize_gcp_label_value(str(variables.get("deployment_name") or ""))
    if not _GCP_LABEL_VALUE_PATTERN.match(deployment_name):
        raise ValueError("deployment_name must be a valid GCP label value")

    for label_key in ("cns_template", "cns_provider"):
        raw = str(variables.get(label_key) or "").strip()
        if not raw:
            continue
        if not _GCP_LABEL_VALUE_PATTERN.match(sanitize_gcp_label_value(raw)):
            raise ValueError(f"{label_key} must be a valid GCP label value")


def _validate_aws_docker_vm(variables: dict[str, Any]) -> None:
    region = str(variables.get("region") or "").strip()
    if not _REGION_PATTERN.match(region):
        raise ValueError("region must be a safe lowercase identifier")

    instance_type = str(variables.get("instance_type") or "t3.medium").strip()
    if not _MACHINE_TYPE_PATTERN.match(instance_type):
        raise ValueError("instance_type format is invalid")

    for optional in ("vpc_id", "subnet_id", "key_name"):
        val = variables.get(optional)
        if val is None or val == "":
            continue
        if not re.match(r"^[a-zA-Z0-9\-_./]{1,128}$", str(val)):
            raise ValueError(f"{optional} format is invalid")

    _validate_cidr("allowed_ssh_cidr", variables.get("allowed_ssh_cidr"))
    _validate_cidr("allowed_app_cidr", variables.get("allowed_app_cidr"))


def _validate_cidr(name: str, value: Any) -> None:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{name} is required")
    if not _CIDR_PATTERN.match(raw):
        raise ValueError(f"{name} must be a valid CIDR")
    try:
        ipaddress.ip_network(raw, strict=False)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid CIDR") from exc


def validate_provider(provider: str, allowed: frozenset[str]) -> None:
    if provider not in allowed:
        raise ValueError(f"Unsupported provider '{provider}'. Allowed: {', '.join(sorted(allowed))}")


def is_real_cloud_provider(provider: str) -> bool:
    return provider in REAL_CLOUD_PROVIDERS


def redact_logs(text: str) -> str:
    from app.core.secret_masking import mask_secrets_in_text

    return mask_secrets_in_text(text) or ""
