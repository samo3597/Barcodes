"""Contract tests for gzip decoding and body-size enforcement."""

import gzip

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from apps.ingest_api.middleware import IngestBodyMiddleware


def create_echo_app(max_body_bytes: int = 128) -> FastAPI:
    app = FastAPI()
    app.add_middleware(IngestBodyMiddleware, max_body_bytes=max_body_bytes)

    @app.post("/ingest/v1/batches")
    async def echo(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    return app


@pytest.mark.asyncio
async def test_gzip_body_is_decoded_before_route_parsing() -> None:
    raw = b'{"items":[]}'
    async with AsyncClient(
        transport=ASGITransport(app=create_echo_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/ingest/v1/batches",
            content=gzip.compress(raw),
            headers={"Content-Encoding": "gzip"},
        )

    assert response.status_code == 200
    assert response.json() == {"size": len(raw)}


@pytest.mark.asyncio
async def test_uncompressed_body_limit_uses_error_envelope() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_echo_app(max_body_bytes=8)),
        base_url="http://test",
    ) as client:
        response = await client.post("/ingest/v1/batches", content=b"123456789")

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


@pytest.mark.asyncio
async def test_invalid_gzip_is_rejected() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_echo_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/ingest/v1/batches",
            content=b"not-gzip",
            headers={"Content-Encoding": "gzip"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_gzip"
