"""Durable normalization and AI orchestration independent of Celery delivery."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from packages.ai_providers import (
    ProductClassifier,
    ProviderPermanentError,
    ProviderTransientError,
)
from packages.contracts import AIProductResult, AIRequest
from packages.domain.candidates import build_candidate
from packages.domain.identifiers import new_uuid7
from packages.domain.ingest import canonical_payload_hash
from packages.domain.prompts import get_prompt
from packages.persistence.server1.ai_repositories import (
    candidate_ids_with_results,
    complete_job,
    create_job_idempotent,
    latest_candidates_for_reprocess,
    load_job,
    load_revision_inputs_for_batch,
    mark_job_failed,
    mark_job_retry,
    mark_job_submitted,
    update_batch_finished,
    update_batch_started,
    upsert_candidate,
)
from packages.persistence.server1.models import AIJob, ImportBatch, ProductCandidate


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    job_id: UUID
    valid: int
    schema_failed: int


async def prepare_batch_job(
    session: AsyncSession,
    batch_id: UUID,
    classifier: ProductClassifier,
    prompt_version: str,
) -> AIJob | None:
    """Merge revisions, persist candidates, and create an idempotent provider job."""

    get_prompt(prompt_version)
    batch = await session.get(ImportBatch, batch_id)
    if batch is None:
        raise ValueError(f"unknown import batch: {batch_id}")
    grouped = await load_revision_inputs_for_batch(session, batch_id)
    candidates = [
        await upsert_candidate(session, build_candidate(barcode, revisions))
        for barcode, revisions in sorted(grouped.items())
    ]
    await session.commit()

    completed_ids = await candidate_ids_with_results(
        session,
        [candidate.id for candidate in candidates],
        classifier.provider_name,
        classifier.model_name,
        prompt_version,
    )
    pending = [candidate for candidate in candidates if candidate.id not in completed_ids]
    await update_batch_started(
        session,
        batch_id,
        validated=batch.received,
        ai_pending=len(pending),
    )
    if not pending:
        await update_batch_finished(session, batch_id, failed=0)
        return None

    request_hash = _job_request_hash(classifier, prompt_version, pending)
    job = await create_job_idempotent(
        session,
        provider=classifier.provider_name,
        model=classifier.model_name,
        prompt_version=prompt_version,
        request_hash=request_hash,
        candidates=pending,
        batch_id=batch_id,
    )
    await session.commit()
    return job


async def prepare_reprocess_job(
    session: AsyncSession,
    classifier: ProductClassifier,
    prompt_version: str,
    *,
    barcode_from: str | None,
    barcode_to: str | None,
    category: str | None,
    failed_only: bool,
    limit: int,
) -> AIJob | None:
    """Create a new immutable run for explicitly selected latest candidates."""

    get_prompt(prompt_version)
    candidates = await latest_candidates_for_reprocess(
        session,
        barcode_from=barcode_from,
        barcode_to=barcode_to,
        category=category,
        failed_only=failed_only,
        limit=limit,
    )
    completed_ids = await candidate_ids_with_results(
        session,
        [candidate.id for candidate in candidates],
        classifier.provider_name,
        classifier.model_name,
        prompt_version,
    )
    pending = [candidate for candidate in candidates if candidate.id not in completed_ids]
    if not pending:
        return None
    job = await create_job_idempotent(
        session,
        provider=classifier.provider_name,
        model=classifier.model_name,
        prompt_version=prompt_version,
        request_hash=_job_request_hash(classifier, prompt_version, pending),
        candidates=pending,
    )
    await session.commit()
    return job


def _job_request_hash(
    classifier: ProductClassifier,
    prompt_version: str,
    candidates: list[ProductCandidate],
) -> str:
    return canonical_payload_hash(
        {
            "provider": classifier.provider_name,
            "model": classifier.model_name,
            "prompt_version": prompt_version,
            "candidates": [
                {"id": str(candidate.id), "input_hash": candidate.input_hash}
                for candidate in sorted(candidates, key=lambda item: str(item.id))
            ],
        }
    )


def _requests_from_job(job: AIJob) -> list[AIRequest]:
    raw_candidates = job.request_payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ProviderPermanentError("job request_payload has no candidates list")
    return [
        AIRequest(
            candidate_id=UUID(str(raw["candidate_id"])),
            barcode=str(raw["barcode"]),
            prompt_version=job.prompt_version,
            input_data=dict(raw["input_data"]),
        )
        for raw in raw_candidates
        if isinstance(raw, dict)
    ]


def _parse_checked(
    classifier: ProductClassifier,
    request: AIRequest,
    raw: dict[str, Any],
) -> AIProductResult:
    parsed = classifier.parse_result(raw)
    if parsed.barcode != request.barcode:
        raise ValueError("AI provider attempted to change barcode")
    return parsed


async def _parse_with_one_repair(
    classifier: ProductClassifier,
    request: AIRequest,
    raw: dict[str, Any],
) -> tuple[AIProductResult | None, dict[str, Any], dict[str, Any], str | None, bool]:
    try:
        return _parse_checked(classifier, request, raw), raw, {}, None, False
    except (ValidationError, ValueError) as first_error:
        repair = request.model_copy(update={"repair_response": raw})
        repair_batch = await classifier.submit_batch([repair])
        repair_status = await classifier.get_batch(repair_batch.provider_batch_id)
        repaired_raw = repair_status.results.get(str(request.candidate_id), {})
        try:
            parsed = _parse_checked(classifier, request, repaired_raw)
            return parsed, repaired_raw, repair_status.usage, None, True
        except (ValidationError, ValueError) as final_error:
            error_code = "ai_schema_invalid"
            error_message = f"{type(first_error).__name__}; repair: {type(final_error).__name__}"
            return None, repaired_raw, repair_status.usage, f"{error_code}:{error_message}", True


async def execute_job(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    classifier: ProductClassifier,
) -> ExecutionSummary:
    """Submit/poll/validate one job and persist every raw response exactly once."""

    async with session_factory() as session:
        job = await load_job(session, job_id)
        if job is None:
            raise ValueError(f"unknown AI job: {job_id}")
        if job.status == "completed":
            return ExecutionSummary(job_id=job.id, valid=0, schema_failed=0)
        if job.provider != classifier.provider_name or job.model != classifier.model_name:
            raise ProviderPermanentError("configured classifier does not match durable AI job")
        requests = _requests_from_job(job)
        if job.provider_batch_id is None:
            submitted = await classifier.submit_batch(requests)
            await mark_job_submitted(session, job, submitted.provider_batch_id)
        provider_status = await classifier.get_batch(str(job.provider_batch_id))
        if provider_status.status == "failed":
            raise ProviderPermanentError("provider batch failed")
        if provider_status.status != "completed":
            raise ProviderTransientError(f"provider batch is {provider_status.status}")

        result_rows: list[dict[str, Any]] = []
        schema_failed = 0
        repair_attempts = 0
        for request in requests:
            raw = provider_status.results.get(str(request.candidate_id), {})
            parsed, final_raw, repair_usage, error, repaired = await _parse_with_one_repair(
                classifier,
                request,
                raw,
            )
            repair_attempts += int(repaired)
            if parsed is None:
                schema_failed += 1
            result_rows.append(
                {
                    "id": new_uuid7(),
                    "job_id": job.id,
                    "candidate_id": request.candidate_id,
                    "provider": job.provider,
                    "model": job.model,
                    "prompt_version": job.prompt_version,
                    "raw_response": final_raw,
                    "status": "schema_failed" if parsed is None else "valid",
                    "parsed_result": parsed.model_dump(mode="json") if parsed is not None else None,
                    "error_code": error.split(":", maxsplit=1)[0] if error else None,
                    "warnings": parsed.warnings if parsed is not None else [],
                    "usage": {"provider": provider_status.usage, "repair": repair_usage},
                }
            )
        job.attempts += repair_attempts
        await complete_job(session, job, result_rows)
        batch_id_value = job.request_payload.get("batch_id")
        if batch_id_value is not None:
            await update_batch_finished(session, UUID(str(batch_id_value)), failed=schema_failed)
        return ExecutionSummary(
            job_id=job.id,
            valid=len(requests) - schema_failed,
            schema_failed=schema_failed,
        )


async def schedule_job_retry(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    error: Exception,
    delay_seconds: int,
) -> None:
    async with session_factory() as session:
        job = await load_job(session, job_id)
        if job is not None:
            await mark_job_retry(
                session,
                job,
                error,
                datetime.now(UTC) + timedelta(seconds=delay_seconds),
            )


async def fail_job(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: UUID,
    error: Exception,
) -> None:
    async with session_factory() as session:
        job = await load_job(session, job_id)
        if job is None:
            return
        await mark_job_failed(session, job, type(error).__name__, str(error))
        batch_id_value = job.request_payload.get("batch_id")
        if batch_id_value is not None:
            await update_batch_finished(
                session,
                UUID(str(batch_id_value)),
                failed=len(job.candidate_ids),
            )
