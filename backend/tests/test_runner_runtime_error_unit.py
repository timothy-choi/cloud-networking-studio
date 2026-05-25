"""Unit tests for runtime error clearing without HTTP client fixtures."""

from __future__ import annotations

from app.runtime.runner_runtime_error import (
    clear_runtime_error,
    clear_runtime_error_after_probe_success,
    get_runtime_error,
    set_runtime_error,
)


def test_clear_probe_error_after_runtime_status_success():
    clear_runtime_error()
    set_runtime_error(operation="runner_status", message="Go runner unavailable", status_code=503)

    clear_runtime_error_after_probe_success("runtime_status")

    assert get_runtime_error(include_historical=False) is None


def test_clear_probe_error_after_runner_status_success():
    clear_runtime_error()
    set_runtime_error(operation="runtime_status", message="probe failed", status_code=503)

    clear_runtime_error_after_probe_success("runner_status")

    assert get_runtime_error(include_historical=False) is None


def test_deploy_error_not_cleared_by_probe_success():
    clear_runtime_error()
    set_runtime_error(operation="deploy", message="invalid topology", status_code=400)

    clear_runtime_error_after_probe_success("runtime_status")

    err = get_runtime_error(include_historical=False)
    assert err is not None
    assert err["operation"] == "deploy"
    clear_runtime_error()


def test_normalize_runner_unreachable_message():
    from app.api.runtime import _normalize_runner_unreachable_message

    msg = _normalize_runner_unreachable_message("[Errno -3] Temporary failure in name resolution")
    assert "unavailable" in msg.lower()
    assert "name resolution" in msg.lower()

    msg2 = _normalize_runner_unreachable_message("connection refused")
    assert "unavailable" in msg2.lower()
