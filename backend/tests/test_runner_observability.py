"""Tests for backend runner observability endpoints."""

from __future__ import annotations

import httpx
import pytest

from app.core.request_context import set_request_id


def test_runner_status_unreachable_when_executor_go(client, monkeypatch):
    from app.core import config
    from app.runtime import go_runner_client as grc

    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")

    def boom(_self):
        raise httpx.ConnectError(
            "refused",
            request=httpx.Request("GET", "http://runner:8090/status"),
        )

    monkeypatch.setattr(grc.GoRunnerClient, "get_runner_status", boom)
    r = client.get("/runtime/runner-status")
    assert r.status_code == 200
    body = r.json()
    assert body["runner_reachable"] is False
    assert body["runtime_executor"] == "go"
    err = body.get("last_runtime_error")
    assert isinstance(err, dict)
    assert err.get("operation") == "runner_status"
    msg = (err.get("message") or body.get("message") or "").lower()
    assert "unavailable" in msg or "refused" in msg or "name resolution" in msg


def test_runner_status_reachable_when_mocked(client, monkeypatch):
    from app.core import config
    from app.runtime import go_runner_client as grc

    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")

    def fake_status(_self):
        return {
            "runner_status": "ok",
            "status": "ok",
            "runtime_provider": "docker",
            "docker_reachable": True,
            "kubernetes_reachable": False,
            "version": "1.0.0",
            "git_sha": "abc123",
            "build_time": "2026-01-01T00:00:00Z",
            "supported_operations": ["deploy", "destroy", "logs"],
        }

    monkeypatch.setattr(grc.GoRunnerClient, "get_runner_status", fake_status)
    r = client.get("/runtime/runner-status")
    assert r.status_code == 200
    body = r.json()
    assert body["runner_reachable"] is True
    assert body["runner_status"] == "ok"
    assert body["version"] == "1.0.0"
    assert "deploy" in body["supported_operations"]


def test_runtime_status_includes_runner_block(client, monkeypatch):
    from app.core import config
    from app.runtime import go_runner_client as grc

    monkeypatch.setenv("RUNTIME_EXECUTOR", "go")
    monkeypatch.setattr(config.settings, "runtime_executor", "go")

    def fake_get_runtime_status(_self):
        return {
            "status": "ok",
            "runner_status": "ok",
            "runtime_provider": "docker",
            "docker_reachable": True,
            "supported_operations": ["deploy", "destroy"],
            "version": "dev",
        }

    monkeypatch.setattr(grc.GoRunnerClient, "get_runtime_status", fake_get_runtime_status)
    r = client.get("/runtime/status")
    assert r.status_code == 200
    body = r.json()
    assert body.get("runner_reachable") is True
    assert body.get("runner", {}).get("version") == "dev"
    assert "checked_at" in body


def test_recent_runner_operations_endpoint(client):
    from app.runtime.runner_operation_history import record_runner_operation

    record_runner_operation(
        operation="deploy",
        provider="docker",
        status="ok",
        duration_ms=12,
        request_id="req-test-1",
    )
    r = client.get("/runtime/operations/recent?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any(op["operation"] == "deploy" for op in body["operations"])


def test_go_runner_client_forwards_request_id(monkeypatch):
    from app.runtime.go_runner_client import GoRunnerClient

    captured: dict[str, str] = {}

    class FakeTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            captured["request_id"] = request.headers.get("X-Request-ID", "")
            return httpx.Response(200, json={"status": "ok", "runtime_provider": "docker"})

    set_request_id("trace-abc-123")
    client = GoRunnerClient("http://runner.test", transport=FakeTransport())
    client.get_runtime_status()
    assert captured.get("request_id") == "trace-abc-123"
