"""W4 canonical versioning and outbox checks against PostgreSQL."""

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from apps.ingest_api.services import accept_batch
from apps.workers.canonical_pipeline import CanonicalizationResult, canonicalize_ai_result
from apps.workers.pipeline import execute_job, prepare_batch_job
from packages.ai_providers import build_classifier
from packages.contracts import IngestBatchRequest, ProductUpsertedEvent
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server1.canonical_repositories import upsert_image_asset
from packages.persistence.server1.models import (
    AIJob,
    AIResult,
    CanonicalProduct,
    ImageAsset,
    ImageFetch,
    ImportBatch,
    ImportBatchItem,
    OutboxEvent,
    ProductCandidate,
    ProductVersion,
    Source,
    SourceProductRevision,
)
from packages.publication import PublisherError, publish_next_event


@pytest.mark.integration
@pytest.mark.asyncio
async def test_canonical_versions_are_idempotent_and_outbox_is_replay_safe() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = build_engine(database_url)
    session_factory = build_session_factory(engine)
    source = Source(name=f"w4-{uuid4()}", status="active", field_priorities={})
    async with session_factory() as session:
        session.add(source)
        await session.commit()
        accepted = await accept_batch(
            session,
            source.id,
            f"w4-{uuid4()}",
            IngestBatchRequest.model_validate(
                {
                    "items": [
                        {
                            "source_record_id": "w4-item",
                            "barcode": "4850000000007",
                            "name": "W4 milk",
                            "image_url": "https://images.example/milk.png",
                            "atg_code": "0401",
                            "vat": True,
                            "is_weighted": False,
                            "category": "Dairy",
                        }
                    ]
                }
            ),
        )
    source_id = source.id
    batch_id = accepted.batch.id
    candidate_id: UUID | None = None
    job_id: UUID | None = None
    try:
        classifier = build_classifier("deterministic", "test")
        async with session_factory() as session:
            job = await prepare_batch_job(session, batch_id, classifier, "product-v1")
            assert job is not None
            job_id = job.id
        await execute_job(session_factory, job.id, classifier)
        async with session_factory() as session:
            result = await session.scalar(select(AIResult).where(AIResult.job_id == job.id))
            assert result is not None
            result_id = result.id
            candidate_id = result.candidate_id

        async def canonicalize_once() -> CanonicalizationResult:
            async with session_factory() as session:
                return await canonicalize_ai_result(session, result_id)

        first, replay = await asyncio.gather(canonicalize_once(), canonicalize_once())
        assert {first.created, replay.created} == {True, False}
        assert first.version == replay.version == 1
        assert first.image_fetch_id == replay.image_fetch_id

        async with session_factory() as session:
            asset = await upsert_image_asset(
                session,
                content_hash="a" * 64,
                storage_key="images/aa/test.webp",
                public_url="https://cdn.example/images/aa/test.webp",
                size_bytes=100,
                width=10,
                height=10,
            )
            await session.commit()
            asset_id = asset.id
        async with session_factory() as session:
            with_image = await canonicalize_ai_result(session, result_id, image_asset_id=asset_id)
        assert with_image.created is True and with_image.version == 2

        delivered: list[dict[str, object]] = []

        async def fake_send(payload: dict[str, object]) -> None:
            delivered.append(payload)

        state, _ = await publish_next_event(session_factory, fake_send)
        assert state == "delivered"
        ProductUpsertedEvent.model_validate(delivered[0])

        async with session_factory() as session:
            remaining = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.status == "pending")
            )
            assert remaining is not None
            remaining.max_attempts = 1
            await session.commit()

        async def fail_send(_: dict[str, object]) -> None:
            raise PublisherError("Server 2 is unavailable")

        failed_state, retry_delay = await publish_next_event(session_factory, fail_send)
        assert failed_state == "dead_letter"
        assert retry_delay is None

        async with session_factory() as session:
            product = await session.get(CanonicalProduct, "4850000000007")
            version_count = await session.scalar(
                select(func.count())
                .select_from(ProductVersion)
                .where(ProductVersion.barcode == "4850000000007")
            )
            event_count = await session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.aggregate_id == "4850000000007")
            )
            assert product is not None and product.current_version == 2
            assert version_count == 2
            assert event_count == 2
    finally:
        async with session_factory() as session:
            await session.execute(
                delete(OutboxEvent).where(OutboxEvent.aggregate_id == "4850000000007")
            )
            await session.execute(
                delete(ProductVersion).where(ProductVersion.barcode == "4850000000007")
            )
            await session.execute(
                delete(CanonicalProduct).where(CanonicalProduct.barcode == "4850000000007")
            )
            if candidate_id is not None:
                await session.execute(
                    delete(ImageFetch).where(
                        ImageFetch.ai_result_id.in_(
                            select(AIResult.id).where(AIResult.candidate_id == candidate_id)
                        )
                    )
                )
                await session.execute(delete(AIResult).where(AIResult.candidate_id == candidate_id))
                await session.execute(
                    delete(ProductCandidate).where(ProductCandidate.id == candidate_id)
                )
            if job_id is not None:
                await session.execute(delete(AIJob).where(AIJob.id == job_id))
            await session.execute(delete(ImageAsset).where(ImageAsset.content_hash == "a" * 64))
            await session.execute(
                delete(ImportBatchItem).where(ImportBatchItem.batch_id == batch_id)
            )
            await session.execute(
                delete(SourceProductRevision).where(SourceProductRevision.source_id == source_id)
            )
            await session.execute(delete(ImportBatch).where(ImportBatch.source_id == source_id))
            await session.execute(delete(Source).where(Source.id == source_id))
            await session.commit()
        await engine.dispose()
