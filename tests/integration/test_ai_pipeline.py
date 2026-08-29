"""W3 lifecycle checks against real PostgreSQL tables and constraints."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from apps.ingest_api.services import accept_batch
from apps.workers.pipeline import execute_job, prepare_batch_job, prepare_reprocess_job
from packages.ai_providers import build_classifier
from packages.contracts import IngestBatchRequest
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server1.models import (
    AIJob,
    AIResult,
    ImportBatch,
    ImportBatchItem,
    ProductCandidate,
    Source,
    SourceProductRevision,
)


def payload() -> IngestBatchRequest:
    return IngestBatchRequest.model_validate(
        {
            "external_batch_id": "ai-export-001",
            "items": [
                {
                    "source_record_id": "ai-item-1",
                    "barcode": "4850000000007",
                    "name": "Թթվասեր 20 տոկոս 800գ",
                    "atg_code": "0403",
                    "vat": True,
                    "is_weighted": False,
                    "category": "Dairy",
                    "source_updated_at": "2026-08-29T10:00:00+04:00",
                }
            ],
        }
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_is_idempotent_and_reprocess_keeps_old_result() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = build_engine(database_url)
    session_factory = build_session_factory(engine)
    source = Source(name=f"ai-integration-{uuid4()}", status="active", field_priorities={})
    async with session_factory() as session:
        session.add(source)
        await session.commit()
    source_id = source.id
    classifier = build_classifier("deterministic", "test")
    candidate_id: UUID | None = None
    first_job_id: UUID | None = None
    reprocess_job_id: UUID | None = None

    try:
        async with session_factory() as session:
            first = await accept_batch(session, source_id, "ai-batch-001", payload())
            first_batch_id = first.batch.id
        async with session_factory() as session:
            first_job = await prepare_batch_job(
                session,
                first_batch_id,
                classifier,
                "product-v1",
            )
            assert first_job is not None
            first_job_id = first_job.id
            first_candidate = first_job.request_payload["candidates"][0]
            candidate_id = UUID(str(first_candidate["candidate_id"]))

        assert first_job_id is not None
        summary = await execute_job(session_factory, first_job_id, classifier)
        assert summary.valid == 1
        assert summary.schema_failed == 0

        async with session_factory() as session:
            second = await accept_batch(session, source_id, "ai-batch-002", payload())
            second_batch_id = second.batch.id
        async with session_factory() as session:
            duplicate_job = await prepare_batch_job(
                session,
                second_batch_id,
                classifier,
                "product-v1",
            )
            assert duplicate_job is None

        async with session_factory() as session:
            reprocess_job = await prepare_reprocess_job(
                session,
                classifier,
                "product-v2",
                barcode_from="4850000000007",
                barcode_to="4850000000007",
                category=None,
                failed_only=False,
                limit=10,
            )
            assert reprocess_job is not None
            reprocess_job_id = reprocess_job.id
        assert reprocess_job_id is not None
        await execute_job(session_factory, reprocess_job_id, classifier)

        async with session_factory() as session:
            revision_count = await session.scalar(
                select(func.count())
                .select_from(SourceProductRevision)
                .where(SourceProductRevision.source_id == source_id)
            )
            batch_item_count = await session.scalar(
                select(func.count())
                .select_from(ImportBatchItem)
                .join(ImportBatch, ImportBatch.id == ImportBatchItem.batch_id)
                .where(ImportBatch.source_id == source_id)
            )
            candidate_count = await session.scalar(
                select(func.count())
                .select_from(ProductCandidate)
                .where(ProductCandidate.id == candidate_id)
            )
            result_count = await session.scalar(
                select(func.count())
                .select_from(AIResult)
                .where(AIResult.candidate_id == candidate_id)
            )
            first_batch = await session.get(ImportBatch, first_batch_id)
            second_batch = await session.get(ImportBatch, second_batch_id)

            assert revision_count == 1
            assert batch_item_count == 2
            assert candidate_count >= 1
            assert result_count == 2
            assert first_batch is not None and first_batch.status == "completed"
            assert second_batch is not None and second_batch.status == "completed"
    finally:
        async with session_factory() as session:
            if candidate_id is not None:
                await session.execute(delete(AIResult).where(AIResult.candidate_id == candidate_id))
                job_ids = [job_id for job_id in (first_job_id, reprocess_job_id) if job_id]
                if job_ids:
                    await session.execute(delete(AIJob).where(AIJob.id.in_(job_ids)))
                await session.execute(
                    delete(ProductCandidate).where(ProductCandidate.id == candidate_id)
                )
            await session.execute(
                delete(ImportBatchItem).where(
                    ImportBatchItem.batch_id.in_(
                        select(ImportBatch.id).where(ImportBatch.source_id == source_id)
                    )
                )
            )
            await session.execute(
                delete(SourceProductRevision).where(SourceProductRevision.source_id == source_id)
            )
            await session.execute(delete(ImportBatch).where(ImportBatch.source_id == source_id))
            await session.execute(delete(Source).where(Source.id == source_id))
            await session.commit()
        await engine.dispose()
