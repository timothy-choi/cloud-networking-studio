"""Unit tests for in-memory runner operation history."""

from app.runtime.runner_operation_history import list_recent_runner_operations, record_runner_operation


def test_record_and_list_operations():
    record_runner_operation(
        operation="deploy",
        provider="docker",
        status="ok",
        duration_ms=42,
        request_id="req-1",
    )
    rows = list_recent_runner_operations(limit=5)
    assert any(r["operation"] == "deploy" for r in rows)


def test_masks_secrets_in_error_message():
    record_runner_operation(
        operation="exec",
        provider="docker",
        status="error",
        duration_ms=1,
        error_message="Authorization: Bearer super-secret-token",
    )
    rows = list_recent_runner_operations(limit=1)
    assert rows
    assert "super-secret-token" not in (rows[0].get("error_message") or "")
    assert "[redacted]" in (rows[0].get("error_message") or "")
