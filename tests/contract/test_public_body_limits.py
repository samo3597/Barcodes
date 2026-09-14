"""Reject oversized public requests before database access."""

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from packages.observability.body import RequestBodyLimitMiddleware
from packages.observability.errors import install_error_handlers
from packages.observability.http import install_http_observability


@pytest.mark.asyncio
async def test_public_body_limits_and_correlation() -> None:
    app = FastAPI()
    install_http_observability(app, "body-test")
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=16)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, str]:
        return {"body": (await request.body()).decode()}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        okay = await client.post("/echo", content=b"1234567890123456")
        assert okay.status_code == 200
        assert okay.json()["body"] == "1234567890123456"
        oversized = await client.post(
            "/echo", content=b"12345678901234567", headers={"X-Request-ID": "safe-id"}
        )
        assert oversized.status_code == 413
        assert oversized.json()["error"]["code"] == "request_too_large"
        assert oversized.headers["X-Request-ID"] == "safe-id"
        encoding = await client.post("/echo", content=b"x", headers={"Content-Encoding": "gzip"})
        assert encoding.status_code == 415


@pytest.mark.asyncio
async def test_unhandled_errors_are_counted_without_path_cardinality() -> None:
    app = FastAPI()
    install_http_observability(app, "error-test")
    install_error_handlers(app)

    @app.get("/failure/{item}")
    async def failure(item: str) -> None:
        raise RuntimeError("simulated")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        failed = await client.get("/failure/secret-product-id")
        assert failed.status_code == 500
        assert failed.json()["error"]["code"] == "internal_error"
        assert failed.json()["request_id"] == failed.headers["X-Request-ID"]
        assert "simulated" not in failed.text
        metrics = (await client.get("/metrics")).text
        assert 'route="/failure/{item}",service="error-test",status="500"' in metrics
        assert "secret-product-id" not in metrics
