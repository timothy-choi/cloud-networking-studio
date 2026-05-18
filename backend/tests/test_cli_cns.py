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


def test_cli_default_base_url_is_localhost_api():
    root = _repo_root()
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "cfg.json"
        cfg.write_text(json.dumps({}), encoding="utf-8")
        env = {
            **os.environ,
            "PYTHONPATH": str(root),
            "CNS_CONFIG": str(cfg),
        }
        env.pop("CNS_BASE_URL", None)
        env.pop("CNS_API_BASE_URL", None)
        p = subprocess.run(
            [sys.executable, "-m", "cli.cns", "config", "get", "--json"],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert data["effective_base_url"] == "http://localhost/api"


def test_cli_base_url_precedence():
    root = _repo_root()
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "cfg.json"
        cfg.write_text(json.dumps({"api_base": "http://saved.example/api"}), encoding="utf-8")
        env = {
            **os.environ,
            "PYTHONPATH": str(root),
            "CNS_CONFIG": str(cfg),
            "CNS_BASE_URL": "http://from-env.example/api",
        }
        p = subprocess.run(
            [
                sys.executable,
                "-m",
                "cli.cns",
                "config",
                "get",
                "--json",
                "--base-url",
                "http://cli.example/api",
            ],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    assert data["effective_base_url"] == "http://cli.example/api"


def test_cli_config_set_unset_roundtrip():
    root = _repo_root()
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "cfg.json"
        env = {**os.environ, "PYTHONPATH": str(root), "CNS_CONFIG": str(cfg)}
        subprocess.run(
            [sys.executable, "-m", "cli.cns", "config", "set", "base_url", "http://x/api"],
            cwd=str(root),
            env=env,
            check=True,
        )
        p1 = subprocess.run(
            [sys.executable, "-m", "cli.cns", "config", "get", "--json"],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(p1.stdout)["api_base"] == "http://x/api"
        subprocess.run(
            [sys.executable, "-m", "cli.cns", "config", "unset", "base_url"],
            cwd=str(root),
            env=env,
            check=True,
        )
        p2 = subprocess.run(
            [sys.executable, "-m", "cli.cns", "config", "get", "--json"],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    assert json.loads(p2.stdout)["api_base"] == ""


def test_cli_connection_refused_friendly_message():
    root = _repo_root()
    with tempfile.TemporaryDirectory() as td:
        cfg = Path(td) / "cfg.json"
        cfg.write_text(json.dumps({"token": "t"}), encoding="utf-8")
        env = {
            **os.environ,
            "PYTHONPATH": str(root),
            "CNS_CONFIG": str(cfg),
            "CNS_BASE_URL": "http://127.0.0.1:9",
        }
        p = subprocess.run(
            [sys.executable, "-m", "cli.cns", "projects", "list"],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    assert p.returncode == 1
    err = (p.stderr or "") + (p.stdout or "")
    assert "Could not reach CNS API at http://127.0.0.1:9" in err
