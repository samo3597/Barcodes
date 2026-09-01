"""Shared FastAPI exception handlers for the stable error envelope."""

import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from packages.contracts import ErrorBody, ErrorEnvelope


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", f"req_{uuid.uuid4()}")


def _response(
    request: Request,
    status_code: int,
    error: ErrorBody,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(error=error, request_id=_request_id(request))
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    """Make framework and validation failures follow the public error contract."""

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        details: dict[str, Any] | None = None
        code = f"http_{exc.status_code}"
        message = str(exc.detail)
        retryable = exc.status_code >= 500

        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("code", code))
            message = str(exc.detail.get("message", message))
            retryable = bool(exc.detail.get("retryable", retryable))
            supplied_details = exc.detail.get("details")
            if isinstance(supplied_details, dict):
                details = supplied_details

        response_headers = dict(getattr(request.state, "rate_limit_headers", {}))
        response_headers.update(exc.headers or {})
        return _response(
            request,
            exc.status_code,
            ErrorBody(code=code, message=message, details=details, retryable=retryable),
            response_headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _response(
            request,
            422,
            ErrorBody(
                code="validation_error",
                message="Request validation failed",
                details={"errors": exc.errors()},
                retryable=False,
            ),
        )
