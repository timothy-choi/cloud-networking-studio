"""Structured API error envelope (Step 53A)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.request_context import get_request_id

ERROR_CODES = frozenset(
    {
        "AUTH_REQUIRED",
        "FORBIDDEN",
        "NOT_FOUND",
        "VALIDATION_ERROR",
        "RUNTIME_PROVIDER_UNAVAILABLE",
        "RUNNER_UNREACHABLE",
        "DEPLOYMENT_FAILED",
        "TERMINAL_UNAVAILABLE",
        "EXEC_UNSUPPORTED",
        "EXPORT_FAILED",
        "RATE_LIMITED",
        "INTERNAL_ERROR",
        "CONFLICT",
    }
)


def _code_for_status(status: int) -> str:
    if status == 401:
        return "AUTH_REQUIRED"
    if status == 403:
        return "FORBIDDEN"
    if status == 404:
        return "NOT_FOUND"
    if status == 409:
        return "CONFLICT"
    if status == 422:
        return "VALIDATION_ERROR"
    if status == 429:
        return "RATE_LIMITED"
    if status == 503:
        return "RUNNER_UNREACHABLE"
    if status >= 500:
        return "INTERNAL_ERROR"
    return "VALIDATION_ERROR"


def _message_from_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list) and detail:
        return str(detail[0])
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("detail") or detail)
    return "Request failed"


def build_error_body(
    *,
    code: str,
    message: str,
    status: int,
    details: dict[str, Any] | None = None,
    legacy_detail: Any = None,
) -> dict[str, Any]:
    rid = get_request_id()
    body: dict[str, Any] = {
        "detail": legacy_detail if legacy_detail is not None else message,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": rid,
        },
    }
    if rid:
        body["request_id"] = rid
    body["status"] = status
    return body


def register_exception_handlers(app) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code = _code_for_status(exc.status_code)
        detail = exc.detail
        if isinstance(detail, dict) and detail.get("code") in ERROR_CODES:
            code = str(detail["code"])
        message = _message_from_detail(detail)
        extra = detail if isinstance(detail, dict) else {}
        body = build_error_body(
            code=code,
            message=message,
            status=exc.status_code,
            details={k: v for k, v in extra.items() if k not in ("code", "message", "detail")},
            legacy_detail=detail,
        )
        return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = build_error_body(
            code="VALIDATION_ERROR",
            message="Validation error",
            status=422,
            details={"errors": exc.errors()},
            legacy_detail=exc.errors(),
        )
        return JSONResponse(status_code=422, content=body)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        body = build_error_body(
            code="INTERNAL_ERROR",
            message="Internal server error",
            status=500,
            legacy_detail="Internal server error",
        )
        return JSONResponse(status_code=500, content=body)
