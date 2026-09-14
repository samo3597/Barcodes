"""Server 1 exposes durable backlog gauges without runtime Server 2 coupling."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from apps.ingest_api.main import create_app
from packages.config import ServiceSettings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_metrics_collect_from_database() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required")
    app = create_app(
        ServiceSettings(
            service_name="ingest-api-metrics-test",
            environment="test",
            database_url=url,
            redis_url="redis://unused/0",
        )
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            metrics = await client.get("/metrics")
            assert metrics.status_code == 200
            assert "pipeline_collection_success 1.0" in metrics.text
            assert 'pipeline_records{kind="outbox",status="dead_letter"}' in metrics.text
            assert 'pipeline_records{kind="ai_result",status="schema_failed"}' in metrics.text
            assert "outbox_oldest_pending_age_seconds" in metrics.text
