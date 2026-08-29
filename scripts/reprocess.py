"""Schedule an explicit immutable AI reprocessing run."""

import argparse
import asyncio
import os

from apps.workers.celery_app import app as celery_app
from apps.workers.pipeline import prepare_reprocess_job
from packages.ai_providers import build_classifier
from packages.persistence.database import build_engine, build_session_factory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-version", required=True, help="Deployed prompt registry version")
    parser.add_argument("--barcode-from")
    parser.add_argument("--barcode-to")
    parser.add_argument("--category")
    parser.add_argument("--failed-only", action="store_true")
    parser.add_argument("--all", action="store_true", dest="select_all")
    parser.add_argument("--limit", type=int, default=1_000)
    args = parser.parse_args()
    has_filter = any(
        (args.barcode_from, args.barcode_to, args.category, args.failed_only, args.select_all)
    )
    if not has_filter:
        parser.error("choose --all or at least one explicit selection filter")
    if not 1 <= args.limit <= 10_000:
        parser.error("--limit must be between 1 and 10000")
    return args


async def schedule(args: argparse.Namespace) -> str | None:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://barcodes:barcodes@localhost:5433/barcodes_server1",
    )
    environment = os.getenv("ENVIRONMENT", "development")
    provider = os.getenv("AI_PROVIDER", "deterministic")
    classifier = build_classifier(provider, environment)
    engine = build_engine(database_url)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            job = await prepare_reprocess_job(
                session,
                classifier,
                args.prompt_version,
                barcode_from=args.barcode_from,
                barcode_to=args.barcode_to,
                category=args.category,
                failed_only=args.failed_only,
                limit=args.limit,
            )
            return str(job.id) if job is not None else None
    finally:
        await engine.dispose()


def main() -> None:
    args = parse_args()
    job_id = asyncio.run(schedule(args))
    if job_id is None:
        print("No candidates require processing for this provider/model/prompt combination.")
        return
    celery_app.send_task("barcodes.run_ai_job", args=[job_id])
    print(f"Scheduled immutable AI job: {job_id}")


if __name__ == "__main__":
    main()
