"""Preview or prune an expired changes prefix; never prune feedback or usage history."""

import argparse
import asyncio
import os
from datetime import UTC, datetime, timedelta

from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server2.change_repositories import prune_change_prefix


async def run(days: int, apply: bool) -> tuple[int, int]:
    database_url = os.environ["DATABASE_URL"]
    engine = build_engine(database_url)
    try:
        async with build_session_factory(engine)() as session:
            return await prune_change_prefix(
                session, retained_since=datetime.now(UTC) - timedelta(days=days), apply=apply
            )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--apply", action="store_true", help="Delete the previewed expired prefix")
    args = parser.parse_args()
    if args.days < 365:
        parser.error("retention must be at least 365 days")
    count, boundary = asyncio.run(run(args.days, args.apply))
    print(f"{'Pruned' if args.apply else 'Would prune'} {count} changes through ID {boundary}")


if __name__ == "__main__":
    main()
