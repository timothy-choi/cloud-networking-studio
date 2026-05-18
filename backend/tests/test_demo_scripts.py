"""Lightweight checks for demo shell scripts (no shell execution required)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
DEMO = SCRIPTS / "demo_full_flow.sh"
CLEANUP = SCRIPTS / "cleanup_cns_docker.sh"


def test_demo_scripts_exist():
    assert DEMO.is_file(), "scripts/demo_full_flow.sh missing"
    assert CLEANUP.is_file(), "scripts/cleanup_cns_docker.sh missing"


def test_demo_scripts_are_executable():
    assert os.access(DEMO, os.X_OK), "chmod +x scripts/demo_full_flow.sh"
    assert os.access(CLEANUP, os.X_OK), "chmod +x scripts/cleanup_cns_docker.sh"


def test_demo_full_flow_contains_expected_sections_and_commands():
    text = DEMO.read_text()
    for needle in (
        "set -euo pipefail",
        "API_BASE",
        "localhost:8000",
        "curl",
        "jq",
        "/health",
        "/topologies",
        "/traffic-tests/ping",
        "/traffic-tests/http",
        "/failures/stop-node",
        "/failures/restart-node",
        "/reconcile",
        "/heal",
        "/destroy",
        "/failures",
        "/events",
        "Verify",
    ):
        assert needle in text, f"missing expected fragment: {needle}"


def test_cleanup_script_filters_on_app_label():
    text = CLEANUP.read_text()
    assert "set -euo pipefail" in text
    assert "label=app=cloud-networking-studio" in text
    assert "docker rm" in text
    assert "docker network rm" in text
