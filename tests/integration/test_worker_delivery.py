"""Optional Redis/Celery smoke test for the real asynchronous delivery path."""

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from apps.ingest_api.services import accept_batch
from apps.workers.celery_app import app as celery_app
from packages.contracts import IngestBatchRequest
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server1.models import (
    AIJob,
    AIResult,
    CanonicalProduct,
    ImportBatch,
    ImportBatchItem,
    OutboxEvent,
    ProductCandidate,
    ProductVersion,
    Source,
    SourceProductRevision,
)
from packages.persistence.server2.models import (
    AppliedEvent,
    Category,
    ChangeEvent,
    PublishedProduct,
)


def unique_gtin13() -> str:
    body = f"290{uuid4().int % 1_000_000_000:09d}"
    weighted = sum(
        int(digit) * (3 if offset % 2 == 0 else 1) for offset, digit in enumerate(reversed(body))
    )
    return f"{body}{(10 - weighted % 10) % 10}"


@pytest.mark.integration
@pytest.mark.worker_integration
@pytest.mark.asyncio
async def test_celery_delivers_batch_to_completed_ai_result() -> None:
    if os.getenv("RUN_WORKER_INTEGRATION") != "1":
        pytest.skip("RUN_WORKER_INTEGRATION=1 is required")
    database_url = os.environ["TEST_DATABASE_URL"]
    server2_database_url = os.environ["TEST_SERVER2_DATABASE_URL"]
    barcode = unique_gtin13()
    category_root = f"smoke_{uuid4().hex}"
    category_id = f"{category_root}.worker"
    engine = build_engine(database_url)
    session_factory = build_session_factory(engine)
    server2_engine = build_engine(server2_database_url)
    server2_session_factory = build_session_factory(server2_engine)
    source = Source(name=f"worker-smoke-{uuid4()}", status="active", field_priorities={})
    async with session_factory() as session:
        session.add(source)
        await session.commit()
        accepted = await accept_batch(
            session,
            source.id,
            f"worker-smoke-{uuid4()}",
            IngestBatchRequest.model_validate(
                {
                    "items": [
                        {
                            "source_record_id": "worker-item",
                            "barcode": barcode,
                            "name": "Worker smoke product",
                            "atg_code": "0000",
                            "vat": True,
                            "is_weighted": False,
                            "category": category_id,
                        }
                    ]
                }
            ),
        )
    source_id = source.id
    batch_id = accepted.batch.id
    candidate_id: UUID | None = None
    job_ids: list[UUID] = []

    try:
        celery_app.send_task("barcodes.process_import_batch", args=[str(batch_id)])
        for _ in range(80):
            await asyncio.sleep(0.25)
            async with session_factory() as session:
                batch = await session.get(ImportBatch, batch_id)
                canonical = await session.get(CanonicalProduct, barcode)
                event = await session.scalar(
                    select(OutboxEvent).where(OutboxEvent.aggregate_id == barcode)
                )
            async with server2_session_factory() as session:
                published = await session.get(PublishedProduct, barcode)
            if (
                batch is not None
                and batch.status in {"completed", "failed"}
                and canonical is not None
                and canonical.current_version >= 1
                and event is not None
                and event.status == "delivered"
                and published is not None
                and published.version == 1
            ):
                break
        else:
            pytest.fail("worker did not publish the batch to Server 2 within 20 seconds")

        assert batch is not None and batch.status == "completed"
        async with session_factory() as session:
            candidate = await session.scalar(
                select(ProductCandidate).where(ProductCandidate.barcode == barcode)
            )
            assert candidate is not None
            candidate_id = candidate.id
            result = await session.scalar(
                select(AIResult).where(AIResult.candidate_id == candidate.id)
            )
            assert result is not None and result.status == "valid"
            canonical = await session.get(CanonicalProduct, barcode)
            assert canonical is not None and canonical.current_version == 1
            event = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == barcode)
            )
            assert event is not None and event.status == "delivered"
            job_ids = list(
                await session.scalars(select(AIJob.id).where(AIJob.candidate_ids.any(candidate.id)))
            )
        async with server2_session_factory() as session:
            published = await session.get(PublishedProduct, barcode)
            assert published is not None
            assert published.version == 1
            assert published.name == "Worker smoke product"
    finally:
        async with session_factory() as session:
            await session.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id == barcode))
            await session.execute(delete(ProductVersion).where(ProductVersion.barcode == barcode))
            await session.execute(
                delete(CanonicalProduct).where(CanonicalProduct.barcode == barcode)
            )
            if candidate_id is not None:
                await session.execute(delete(AIResult).where(AIResult.candidate_id == candidate_id))
                if job_ids:
                    await session.execute(delete(AIJob).where(AIJob.id.in_(job_ids)))
                await session.execute(
                    delete(ProductCandidate).where(ProductCandidate.id == candidate_id)
                )
            await session.execute(
                delete(ImportBatchItem).where(ImportBatchItem.batch_id == batch_id)
            )
            await session.execute(
                delete(SourceProductRevision).where(SourceProductRevision.source_id == source_id)
            )
            await session.execute(delete(ImportBatch).where(ImportBatch.source_id == source_id))
            await session.execute(delete(Source).where(Source.id == source_id))
            await session.commit()
        async with server2_session_factory() as session:
            await session.execute(delete(ChangeEvent).where(ChangeEvent.barcode == barcode))
            await session.execute(
                delete(PublishedProduct).where(PublishedProduct.barcode == barcode)
            )
            await session.execute(delete(AppliedEvent).where(AppliedEvent.aggregate_id == barcode))
            await session.execute(
                delete(Category).where(Category.category_id.in_([category_id, category_root]))
            )
            await session.commit()
        await engine.dispose()
        await server2_engine.dispose()
