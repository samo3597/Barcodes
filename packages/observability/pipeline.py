"""Durable pipeline gauges read from Server 1, independent of worker restarts."""

import asyncio
from datetime import UTC, datetime

from fastapi import FastAPI
from prometheus_client import Gauge
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.persistence.server1.models import AIJob, AIResult, ImportBatch, OutboxEvent


def install_pipeline_metrics(app: FastAPI, factory: async_sessionmaker[AsyncSession]) -> None:
    registry = app.state.metrics_registry
    records = Gauge(
        "pipeline_records",
        "Durable pipeline backlog and failures",
        ("kind", "status"),
        registry=registry,
    )
    lag = Gauge(
        "outbox_oldest_pending_age_seconds",
        "Age of oldest undelivered publication",
        registry=registry,
    )
    success = Gauge(
        "pipeline_collection_success",
        "Whether the last DB metrics scrape succeeded",
        registry=registry,
    )

    async def collect() -> None:
        async with factory() as session:
            records.clear()
            for kind, status_column, statuses in [
                ("batch", ImportBatch.status, ["accepted", "processing", "failed"]),
                ("ai_result", AIResult.status, ["schema_failed"]),
                (
                    "ai",
                    AIJob.status,
                    ["pending", "submitted", "processing", "retry_scheduled", "failed"],
                ),
                (
                    "outbox",
                    OutboxEvent.status,
                    ["pending", "processing", "retry_scheduled", "dead_letter"],
                ),
            ]:
                rows = await session.execute(
                    select(status_column, func.count())
                    .where(status_column.in_(statuses))
                    .group_by(status_column)
                )
                counts = {row[0]: row[1] for row in rows}
                for status in statuses:
                    records.labels(kind, status).set(counts.get(status, 0))
            oldest = await session.scalar(
                select(func.min(OutboxEvent.created_at)).where(
                    OutboxEvent.status.in_(["pending", "processing", "retry_scheduled"])
                )
            )
            lag.set(max(0, (datetime.now(UTC) - oldest).total_seconds()) if oldest else 0)

    async def refresh() -> None:
        try:
            await asyncio.wait_for(collect(), timeout=3)
        except (SQLAlchemyError, TimeoutError):
            success.set(0)
        else:
            success.set(1)

    app.state.refresh_operational_metrics = refresh
