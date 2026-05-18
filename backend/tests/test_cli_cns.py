"""Smoke tests for ``python -m cli.cns`` (Step 44)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_cli_help_exits_zero():
    root = _repo_root()
    env = {**os.environ, "PYTHONPATH": str(root)}
    p = subprocess.run(
        [sys.executable, "-m", "cli.cns", "--help"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0, p.stderr + p.stdout


def test_cli_projects_list_requires_token():
    root = _repo_root()
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "cns-cli-test-config.json"
        cfg.write_text(json.dumps({}), encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(root), "CNS_CONFIG": str(cfg)}
        env.pop("CNS_TOKEN", None)
        p = subprocess.run(
            [sys.executable, "-m", "cli.cns", "projects", "list"],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    assert p.returncode == 1
    assert "No token" in (p.stderr or "")
