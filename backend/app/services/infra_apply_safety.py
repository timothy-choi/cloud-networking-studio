"""Apply/destroy safety gates for real GCP infrastructure (Step 57E)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models.infrastructure_deployment import InfrastructureDeployment

GCP_DOCKER_VM_APPLY_PROVIDER = "gcp"
GCP_DOCKER_VM_APPLY_TEMPLATE = "docker-vm"

GCP_APPLY_REGIONS = frozenset({"us-central1", "us-west1", "us-east1"})
GCP_APPLY_MACHINE_TYPES = frozenset({"e2-micro", "e2-small", "e2-medium"})
GCP_APPLY_MAX_INSTANCES = 1
OPEN_INTERNET_CIDR = "0.0.0.0/0"


class InfraApplySafetyError(Exception):
    def __init__(self, message: str, *, checklist: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.checklist = checklist or {}


class InfraInvalidStateError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def is_gcp_docker_vm_apply_eligible(deployment: InfrastructureDeployment) -> bool:
    return (
        deployment.provider == GCP_DOCKER_VM_APPLY_PROVIDER
        and deployment.template_id == GCP_DOCKER_VM_APPLY_TEMPLATE
    )


def variables_hash(variables: dict[str, Any] | None) -> str:
    payload = json.dumps(variables or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_apply_safety_checklist(
    deployment: InfrastructureDeployment,
    *,
    unsafe_testing_override: bool = False,
) -> dict[str, Any]:
    variables = deployment.variables_json or {}
    items: list[dict[str, Any]] = []
    passed = True

    def add(name: str, ok: bool, message: str, *, warning: bool = False) -> None:
        nonlocal passed
        if not ok and not warning:
            passed = False
        items.append({"name": name, "ok": ok, "warning": warning, "message": message})

    add(
        "provider_template",
        is_gcp_docker_vm_apply_eligible(deployment),
        "Provider/template must be gcp + docker-vm",
    )
    add(
        "status",
        deployment.status == "awaiting_confirmation",
        f"Status must be awaiting_confirmation (current: {deployment.status})",
    )
    add(
        "plan_ready",
        bool((deployment.state_metadata_json or {}).get("plan_execution_id")),
        "A successful Terraform plan must exist before apply",
    )

    stored_hash = (deployment.state_metadata_json or {}).get("variables_hash")
    current_hash = variables_hash(variables)
    add(
        "plan_fresh",
        bool(stored_hash) and stored_hash == current_hash,
        "Plan is stale — re-run Plan after changing variables",
    )

    vm_count = int(variables.get("vm_count") or 1)
    add(
        "max_instances",
        vm_count <= GCP_APPLY_MAX_INSTANCES,
        f"vm_count must be <= {GCP_APPLY_MAX_INSTANCES} for apply",
    )

    machine_type = str(variables.get("machine_type") or "e2-medium").strip()
    add(
        "machine_type",
        machine_type in GCP_APPLY_MACHINE_TYPES,
        f"machine_type must be one of: {', '.join(sorted(GCP_APPLY_MACHINE_TYPES))}",
    )

    region = str(variables.get("region") or "").strip()
    zone = str(variables.get("zone") or "").strip()
    add(
        "region_allowlist",
        region in GCP_APPLY_REGIONS,
        f"region must be one of: {', '.join(sorted(GCP_APPLY_REGIONS))}",
    )
    add(
        "zone_region_match",
        bool(region and zone.startswith(f"{region}-")),
        "zone must belong to the selected region",
    )

    instance_name = str(variables.get("instance_name") or "").strip()
    add(
        "instance_name_prefix",
        instance_name.startswith("cns-"),
        "instance_name must be prefixed with cns-",
    )

    network_name = str(variables.get("network_name") or "").strip()
    if network_name and network_name != "default":
        add(
            "network_name_prefix",
            network_name.startswith("cns-"),
            "network_name must be prefixed with cns- (or use default)",
        )
    else:
        add("network_name_prefix", True, "network_name uses default VPC")

    ssh_cidr = str(variables.get("allowed_ssh_cidr") or "").strip()
    app_cidr = str(variables.get("allowed_app_cidr") or "").strip()
    open_cidr = ssh_cidr == OPEN_INTERNET_CIDR or app_cidr == OPEN_INTERNET_CIDR
    if open_cidr and not unsafe_testing_override:
        add(
            "cidr_restrictions",
            False,
            "allowed_ssh_cidr/allowed_app_cidr cannot be 0.0.0.0/0 without unsafe_testing_override",
        )
    elif open_cidr:
        add(
            "cidr_restrictions",
            True,
            "Open CIDR override enabled (testing only)",
            warning=True,
        )
    else:
        add("cidr_restrictions", True, "CIDR restrictions look safe")

    add(
        "credentials_ref",
        bool((deployment.credentials_ref or "").strip()),
        "Terraform credentials_ref must be configured",
    )

    add(
        "public_ip_warning",
        True,
        "This will create a VM with a public IP address",
        warning=True,
    )
    add(
        "cost_warning",
        True,
        "This may create billable cloud resources.",
        warning=True,
    )

    return {
        "passed": passed,
        "items": items,
        "unsafe_testing_override": unsafe_testing_override,
        "variables_hash": current_hash,
    }


def validate_gcp_apply_safety(
    deployment: InfrastructureDeployment,
    *,
    unsafe_testing_override: bool = False,
) -> dict[str, Any]:
    if not is_gcp_docker_vm_apply_eligible(deployment):
        raise InfraApplySafetyError(
            "Real apply is only enabled for gcp docker-vm deployments.",
        )
    checklist = build_apply_safety_checklist(
        deployment,
        unsafe_testing_override=unsafe_testing_override,
    )
    if not checklist["passed"]:
        failed = [item["message"] for item in checklist["items"] if not item["ok"]]
        raise InfraApplySafetyError(
            "; ".join(failed),
            checklist=checklist,
        )
    return checklist
