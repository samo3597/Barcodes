"""Celery delivery wrappers around the durable W3 pipeline."""

import asyncio
import random
from uuid import UUID

from celery import Task

from apps.workers.canonical_pipeline import canonicalize_job_results, process_image_fetch
from apps.workers.celery_app import app
from apps.workers.pipeline import (
    execute_job,
    fail_job,
    prepare_batch_job,
    schedule_job_retry,
)
from packages.ai_providers import ProviderPermanentError, ProviderTransientError, build_classifier
from packages.config import WorkerSettings
from packages.observability.logging import configure_logging
from packages.persistence.database import build_engine, build_session_factory
from packages.publication import HttpEventPublisher, publish_next_event

MAX_TRANSIENT_RETRIES = 3


async def _prepare_batch(batch_id: UUID) -> UUID | None:
    settings = WorkerSettings()
    classifier = build_classifier(settings.ai_provider, settings.environment)
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            job = await prepare_batch_job(
                session,
                batch_id,
                classifier,
                settings.ai_prompt_version,
            )
            return job.id if job is not None else None
    finally:
        await engine.dispose()


async def _execute_job(job_id: UUID) -> None:
    settings = WorkerSettings()
    classifier = build_classifier(settings.ai_provider, settings.environment)
    engine = build_engine(settings.database_url)
    try:
        await execute_job(build_session_factory(engine), job_id, classifier)
    finally:
        await engine.dispose()


async def _canonicalize_job(job_id: UUID) -> list[UUID]:
    settings = WorkerSettings()
    engine = build_engine(settings.database_url)
    try:
        return await canonicalize_job_results(build_session_factory(engine), job_id)
    finally:
        await engine.dispose()


async def _process_image(fetch_id: UUID) -> None:
    settings = WorkerSettings()
    engine = build_engine(settings.database_url)
    try:
        await process_image_fetch(
            build_session_factory(engine),
            fetch_id,
            storage_root=settings.image_storage_root,
            public_base_url=settings.image_public_base_url,
        )
    finally:
        await engine.dispose()


async def _publish_next() -> tuple[str, int | None]:
    settings = WorkerSettings()
    if settings.server2_internal_url is None:
        return "disabled", None
    if settings.internal_sync_secret is None:
        raise ValueError("INTERNAL_SYNC_SECRET is required when Server 2 publication is enabled")
    engine = build_engine(settings.database_url)
    publisher = HttpEventPublisher(settings.server2_internal_url, settings.internal_sync_secret)
    try:
        return await publish_next_event(build_session_factory(engine), publisher.publish)
    finally:
        await engine.dispose()


async def _record_retry(job_id: UUID, error: Exception, delay_seconds: int) -> None:
    settings = WorkerSettings()
    engine = build_engine(settings.database_url)
    try:
        await schedule_job_retry(build_session_factory(engine), job_id, error, delay_seconds)
    finally:
        await engine.dispose()


async def _record_failure(job_id: UUID, error: Exception) -> None:
    settings = WorkerSettings()
    engine = build_engine(settings.database_url)
    try:
        await fail_job(build_session_factory(engine), job_id, error)
    finally:
        await engine.dispose()


@app.task(name="barcodes.process_import_batch", acks_late=True)
def process_import_batch(batch_id: str) -> str | None:
    """Create deterministic candidates, then enqueue their durable AI job."""

    settings = WorkerSettings()
    configure_logging(settings.log_level)
    job_id = asyncio.run(_prepare_batch(UUID(batch_id)))
    if job_id is not None:
        run_ai_job.delay(str(job_id))
        return str(job_id)
    return None


@app.task(bind=True, name="barcodes.run_ai_job", acks_late=True, max_retries=MAX_TRANSIENT_RETRIES)
def run_ai_job(self: Task, job_id: str) -> None:
    """Execute a provider batch with exponential backoff and jitter."""

    parsed_job_id = UUID(job_id)
    try:
        asyncio.run(_execute_job(parsed_job_id))
        canonicalize_ai_job.delay(job_id)
    except ProviderTransientError as error:
        retries = int(self.request.retries)
        if retries >= MAX_TRANSIENT_RETRIES:
            asyncio.run(_record_failure(parsed_job_id, error))
            raise
        delay = min(300, 2 ** (retries + 1) + random.SystemRandom().randint(0, 5))
        asyncio.run(_record_retry(parsed_job_id, error, delay))
        raise self.retry(exc=error, countdown=delay) from error
    except (ProviderPermanentError, ValueError) as error:
        asyncio.run(_record_failure(parsed_job_id, error))
        raise


@app.task(name="barcodes.canonicalize_ai_job", acks_late=True)
def canonicalize_ai_job(job_id: str) -> int:
    """Create canonical versions and enqueue optional image work."""

    fetch_ids = asyncio.run(_canonicalize_job(UUID(job_id)))
    for fetch_id in fetch_ids:
        process_product_image.delay(str(fetch_id))
    publish_outbox.delay()
    return len(fetch_ids)


@app.task(name="barcodes.process_product_image", acks_late=True)
def process_product_image(fetch_id: str) -> None:
    """Image failure is recorded and intentionally does not fail text publication."""

    asyncio.run(_process_image(UUID(fetch_id)))
    publish_outbox.delay()


@app.task(name="barcodes.publish_outbox", acks_late=True)
def publish_outbox() -> str:
    """Drain ready events; delivery remains disabled until W5 exposes Server 2."""

    state, delay = asyncio.run(_publish_next())
    if state == "delivered":
        publish_outbox.delay()
    elif state == "retry_scheduled" and delay is not None:
        publish_outbox.apply_async(countdown=delay)
    return state
