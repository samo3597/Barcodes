"""Contract tests shared by both HTTP applications."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from apps.ingest_api.main import create_app as create_ingest_app
from apps.public_api.main import create_app as create_public_app


async def ready() -> None:
    return None


async def not_ready() -> None:
    raise RuntimeError("database unavailable")


@pytest.mark.parametrize("factory", [create_ingest_app, create_public_app])
@pytest.mark.asyncio
async def test_liveness_contract(factory: Callable[..., FastAPI]) -> None:
    app = factory(readiness_check=ready)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/health/live",
            headers={"X-Request-ID": "test-request-1"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "alive"
    assert response.headers["X-Request-ID"] == "test-request-1"


@pytest.mark.parametrize("factory", [create_ingest_app, create_public_app])
@pytest.mark.asyncio
async def test_readiness_contract(factory: Callable[..., FastAPI]) -> None:
    app = factory(readiness_check=ready)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.parametrize("factory", [create_ingest_app, create_public_app])
@pytest.mark.asyncio
async def test_unavailable_database_uses_error_envelope(
    factory: Callable[..., FastAPI],
) -> None:
    app = factory(readiness_check=not_ready)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")

    payload: dict[str, Any] = response.json()
    assert response.status_code == 503
    assert payload["error"]["code"] == "dependency_not_ready"
    assert payload["error"]["retryable"] is True
    assert payload["request_id"].startswith("req_")


@pytest.mark.parametrize("factory", [create_ingest_app, create_public_app])
@pytest.mark.asyncio
async def test_metrics_endpoint(factory: Callable[..., FastAPI]) -> None:
    app = factory(readiness_check=ready)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/health/live")
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text
