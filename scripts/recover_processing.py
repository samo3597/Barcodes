"""Re-enqueue durable batches and AI jobs after broker or worker interruption."""

import argparse
import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select

from apps.workers.celery_app import app as celery_app
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server1.models import AIJob, ImportBatch


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


async def find_recoverable(limit: int) -> tuple[list[UUID], list[UUID]]:
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
            return batch_ids, job_ids
    finally:
        await engine.dispose()


def main() -> None:
    args = parse_args()
    batch_ids, job_ids = asyncio.run(find_recoverable(args.limit))
    print(f"Recoverable accepted batches: {len(batch_ids)}")
    print(f"Recoverable AI jobs: {len(job_ids)}")
    if not args.apply:
        print("Dry run only. Add --apply to enqueue these durable records.")
        return
    for batch_id in batch_ids:
        celery_app.send_task("barcodes.process_import_batch", args=[str(batch_id)])
    for job_id in job_ids:
        celery_app.send_task("barcodes.run_ai_job", args=[str(job_id)])
    print("Recovery tasks enqueued.")


if __name__ == "__main__":
    main()
