"""Re-enqueue durable batches and AI jobs after broker or worker interruption."""

import argparse
import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select, update

from apps.workers.celery_app import app as celery_app
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server1.models import (
    AIJob,
    AIResult,
    ImageFetch,
    ImportBatch,
    OutboxEvent,
    ProductVersion,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=1_000)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually enqueue; without this flag only print what would be recovered",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 10_000:
        parser.error("--limit must be between 1 and 10000")
    return args


async def find_recoverable(
    limit: int,
) -> tuple[list[UUID], list[UUID], list[UUID], list[UUID], bool]:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://barcodes:barcodes@localhost:5433/barcodes_server1",
    )
    engine = build_engine(database_url)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            batch_ids = list(
                await session.scalars(
                    select(ImportBatch.id)
                    .where(ImportBatch.status == "accepted")
                    .order_by(ImportBatch.created_at)
                    .limit(limit)
                )
            )
            remaining = max(0, limit - len(batch_ids))
            job_ids = list(
                await session.scalars(
                    select(AIJob.id)
                    .where(
                        AIJob.status.in_(["pending", "submitted", "processing", "retry_scheduled"]),
                        or_(
                            AIJob.next_attempt_at.is_(None),
                            AIJob.next_attempt_at <= datetime.now(UTC),
                        ),
                    )
                    .order_by(AIJob.created_at)
                    .limit(remaining)
                )
            )
            remaining = max(0, remaining - len(job_ids))
            canonical_job_ids = list(
                await session.scalars(
                    select(AIResult.job_id)
                    .outerjoin(ProductVersion, ProductVersion.origin_id == AIResult.id)
                    .where(AIResult.status == "valid", ProductVersion.id.is_(None))
                    .distinct()
                    .limit(remaining)
                )
            )
            remaining = max(0, remaining - len(canonical_job_ids))
            image_fetch_ids = list(
                await session.scalars(
                    select(ImageFetch.id)
                    .where(ImageFetch.status.in_(["pending", "processing"]))
                    .order_by(ImageFetch.created_at)
                    .limit(remaining)
                )
            )
            outbox_exists = bool(
                await session.scalar(
                    select(OutboxEvent.id)
                    .where(OutboxEvent.status.in_(["pending", "processing", "retry_scheduled"]))
                    .limit(1)
                )
            )
            return batch_ids, job_ids, canonical_job_ids, image_fetch_ids, outbox_exists
    finally:
        await engine.dispose()


def main() -> None:
    args = parse_args()
    batch_ids, job_ids, canonical_job_ids, image_fetch_ids, outbox_exists = asyncio.run(
        find_recoverable(args.limit)
    )
    print(f"Recoverable accepted batches: {len(batch_ids)}")
    print(f"Recoverable AI jobs: {len(job_ids)}")
    print(f"Recoverable canonical jobs: {len(canonical_job_ids)}")
    print(f"Recoverable image fetches: {len(image_fetch_ids)}")
    print(f"Recoverable outbox work: {'yes' if outbox_exists else 'no'}")
    if not args.apply:
        print("Dry run only. Add --apply to enqueue these durable records.")
        return
    for batch_id in batch_ids:
        celery_app.send_task("barcodes.process_import_batch", args=[str(batch_id)])
    for job_id in job_ids:
        celery_app.send_task("barcodes.run_ai_job", args=[str(job_id)])
    for job_id in canonical_job_ids:
        celery_app.send_task("barcodes.canonicalize_ai_job", args=[str(job_id)])
    for fetch_id in image_fetch_ids:
        celery_app.send_task("barcodes.process_product_image", args=[str(fetch_id)])
    if outbox_exists:
        asyncio.run(reset_orphaned_outbox())
        celery_app.send_task("barcodes.publish_outbox")
    print("Recovery tasks enqueued.")


async def reset_orphaned_outbox() -> None:
    """Return crash-orphaned claims to the ready state before enqueueing the drain."""

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://barcodes:barcodes@localhost:5433/barcodes_server1",
    )
    engine = build_engine(database_url)
    try:
        async with build_session_factory(engine)() as session:
            await session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.status == "processing")
                .values(status="retry_scheduled", next_attempt_at=None)
            )
            await session.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    main()
