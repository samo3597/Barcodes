"""PostgreSQL operations for normalized candidates and immutable AI runs."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.candidates import CandidateSnapshot, SourceRevisionInput
from packages.domain.identifiers import new_uuid7
from packages.persistence.server1.models import (
    AIJob,
    AIResult,
    ImportBatch,
    ImportBatchItem,
    ProductCandidate,
    Source,
    SourceProductRevision,
)


async def load_revision_inputs_for_batch(
    session: AsyncSession,
    batch_id: UUID,
) -> dict[str, list[SourceRevisionInput]]:
    """Load every known source revision for barcodes touched by one batch."""

    target_barcodes = select(ImportBatchItem.barcode).where(ImportBatchItem.batch_id == batch_id)
    rows = await session.execute(
        select(SourceProductRevision, Source)
        .join(Source, Source.id == SourceProductRevision.source_id)
        .where(SourceProductRevision.barcode.in_(target_barcodes))
    )
    grouped: dict[str, list[SourceRevisionInput]] = defaultdict(list)
    for revision, source in rows:
        grouped[revision.barcode].append(
            SourceRevisionInput(
                revision_id=revision.id,
                source_id=revision.source_id,
                barcode=revision.barcode,
                payload=revision.raw_payload,
                field_priorities=source.field_priorities,
                occurred_at=revision.source_updated_at or revision.created_at,
            )
        )
    return dict(grouped)


async def upsert_candidate(
    session: AsyncSession,
    snapshot: CandidateSnapshot,
) -> ProductCandidate:
    """Return the existing semantic snapshot or insert it exactly once."""

    candidate_id = new_uuid7()
    statement = (
        postgres_insert(ProductCandidate)
        .values(
            id=candidate_id,
            barcode=snapshot.barcode,
            input_hash=snapshot.input_hash,
            schema_version=1,
            normalized_payload=snapshot.normalized_payload,
            source_revision_ids=list(snapshot.source_revision_ids),
        )
        .on_conflict_do_nothing(index_elements=["barcode", "input_hash", "schema_version"])
        .returning(ProductCandidate.id)
    )
    inserted_id = (await session.execute(statement)).scalar_one_or_none()
    resolved_id = inserted_id or await session.scalar(
        select(ProductCandidate.id).where(
            ProductCandidate.barcode == snapshot.barcode,
            ProductCandidate.input_hash == snapshot.input_hash,
            ProductCandidate.schema_version == 1,
        )
    )
    if resolved_id is None:
        raise RuntimeError("candidate upsert did not resolve an identifier")
    candidate = await session.get(ProductCandidate, resolved_id)
    if candidate is None:
        raise RuntimeError("candidate disappeared after upsert")
    return candidate


async def candidate_ids_with_results(
    session: AsyncSession,
    candidate_ids: Sequence[UUID],
    provider: str,
    model: str,
    prompt_version: str,
) -> set[UUID]:
    if not candidate_ids:
        return set()
    result = await session.scalars(
        select(AIResult.candidate_id).where(
            AIResult.candidate_id.in_(candidate_ids),
            AIResult.provider == provider,
            AIResult.model == model,
            AIResult.prompt_version == prompt_version,
        )
    )
    return set(result)


async def create_job_idempotent(
    session: AsyncSession,
    *,
    provider: str,
    model: str,
    prompt_version: str,
    request_hash: str,
    candidates: Sequence[ProductCandidate],
    batch_id: UUID | None = None,
) -> AIJob:
    """Create one durable provider batch, or recover it after a task replay."""

    job_id = new_uuid7()
    request_payload = {
        "batch_id": str(batch_id) if batch_id is not None else None,
        "candidates": [
            {
                "candidate_id": str(candidate.id),
                "barcode": candidate.barcode,
                "input_hash": candidate.input_hash,
                "input_data": candidate.normalized_payload,
            }
            for candidate in candidates
        ],
    }
    statement = (
        postgres_insert(AIJob)
        .values(
            id=job_id,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            request_hash=request_hash,
            candidate_ids=[candidate.id for candidate in candidates],
            request_payload=request_payload,
            status="pending",
            attempts=0,
            max_attempts=4,
        )
        .on_conflict_do_nothing(
            index_elements=["provider", "model", "prompt_version", "request_hash"]
        )
        .returning(AIJob.id)
    )
    inserted_id = (await session.execute(statement)).scalar_one_or_none()
    resolved_id = inserted_id or await session.scalar(
        select(AIJob.id).where(
            AIJob.provider == provider,
            AIJob.model == model,
            AIJob.prompt_version == prompt_version,
            AIJob.request_hash == request_hash,
        )
    )
    if resolved_id is None:
        raise RuntimeError("AI job upsert did not resolve an identifier")
    job = await session.get(AIJob, resolved_id)
    if job is None:
        raise RuntimeError("AI job disappeared after upsert")
    return job


async def load_job(session: AsyncSession, job_id: UUID) -> AIJob | None:
    return await session.get(AIJob, job_id)


async def mark_job_submitted(
    session: AsyncSession,
    job: AIJob,
    provider_batch_id: str,
) -> None:
    job.provider_batch_id = provider_batch_id
    job.status = "submitted"
    job.attempts += 1
    job.error_code = None
    job.error_message = None
    job.next_attempt_at = None
    await session.commit()


async def mark_job_retry(
    session: AsyncSession,
    job: AIJob,
    error: Exception,
    next_attempt_at: datetime,
) -> None:
    job.status = "retry_scheduled"
    job.error_code = type(error).__name__
    job.error_message = str(error)[:2_000]
    job.next_attempt_at = next_attempt_at
    await session.commit()


async def mark_job_failed(session: AsyncSession, job: AIJob, code: str, message: str) -> None:
    job.status = "failed"
    job.error_code = code
    job.error_message = message[:2_000]
    job.completed_at = datetime.now(UTC)
    await session.commit()


async def complete_job(
    session: AsyncSession,
    job: AIJob,
    results: Sequence[dict[str, Any]],
) -> None:
    if results:
        statement = (
            postgres_insert(AIResult)
            .values(list(results))
            .on_conflict_do_nothing(
                index_elements=["candidate_id", "provider", "model", "prompt_version"]
            )
        )
        await session.execute(statement)
    job.status = "completed"
    job.completed_at = datetime.now(UTC)
    job.next_attempt_at = None
    job.error_code = None
    job.error_message = None
    await session.commit()


async def update_batch_started(
    session: AsyncSession,
    batch_id: UUID,
    validated: int,
    ai_pending: int,
) -> None:
    await session.execute(
        update(ImportBatch)
        .where(ImportBatch.id == batch_id)
        .values(status="processing", validated=validated, ai_pending=ai_pending)
    )
    await session.commit()


async def update_batch_finished(
    session: AsyncSession,
    batch_id: UUID,
    *,
    failed: int,
) -> None:
    await session.execute(
        update(ImportBatch)
        .where(ImportBatch.id == batch_id)
        .values(status="failed" if failed else "completed", ai_pending=0, failed=failed)
    )
    await session.commit()


async def latest_candidates_for_reprocess(
    session: AsyncSession,
    *,
    barcode_from: str | None,
    barcode_to: str | None,
    category: str | None,
    failed_only: bool,
    limit: int,
) -> list[ProductCandidate]:
    """Select the newest candidate per barcode under explicit operator filters."""

    statement = select(ProductCandidate).distinct(ProductCandidate.barcode)
    if barcode_from is not None:
        statement = statement.where(ProductCandidate.barcode >= barcode_from)
    if barcode_to is not None:
        statement = statement.where(ProductCandidate.barcode <= barcode_to)
    if category is not None:
        statement = statement.where(
            ProductCandidate.normalized_payload["fields"]["category"].astext == category
        )
    if failed_only:
        failed_jobs = await session.scalars(select(AIJob).where(AIJob.status == "failed"))
        failed_candidate_ids = {
            candidate_id for job in failed_jobs for candidate_id in job.candidate_ids
        }
        if not failed_candidate_ids:
            return []
        statement = statement.where(ProductCandidate.id.in_(failed_candidate_ids))
    statement = statement.order_by(
        ProductCandidate.barcode,
        ProductCandidate.created_at.desc(),
    ).limit(limit)
    return list(await session.scalars(statement))
