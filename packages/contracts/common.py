"""Contracts that are shared by every HTTP application."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictContract(BaseModel):
    """Base model that rejects unknown fields instead of silently ignoring them."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictContract):
    """Response returned by liveness and readiness probes."""

    status: Literal["alive", "ready", "not_ready"]
    service: str = Field(min_length=1)


class ErrorBody(StrictContract):
    """Machine-readable error information returned by every API."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any] | None = None
    retryable: bool = False


class ErrorEnvelope(StrictContract):
    """Stable outer envelope for API errors."""

    error: ErrorBody
    request_id: str
