"""Create a source and print its API key exactly once."""

import argparse
import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.api_keys import generate_source_api_key
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server1.models import Source, SourceApiKey

DEFAULT_SCOPES = ["ingest:write", "batches:read"]


async def create_source(name: str, scopes: list[str], database_url: str) -> str:
    """Persist a source credential and return the one-time plaintext key."""

    engine = build_engine(database_url)
    session_factory = build_session_factory(engine)
    generated = generate_source_api_key()
    try:
        async with session_factory() as session:
            await _persist_source(session, name, scopes, generated.prefix, generated.encoded_hash)
    finally:
        await engine.dispose()
    return generated.raw_key


async def _persist_source(
    session: AsyncSession,
    name: str,
    scopes: list[str],
    key_prefix: str,
    key_hash: str,
) -> None:
    source = Source(name=name, status="active", field_priorities={})
    session.add(source)
    await session.flush()
    session.add(
        SourceApiKey(
            source_id=source.id,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes,
            status="active",
        )
    )
    await session.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Stable unique source name")
    parser.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        choices=["ingest:write", "batches:read", "images:write"],
        help="Repeat for each scope; defaults to ingest and batch status access",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://barcodes:barcodes@localhost:5433/barcodes_server1",
    )
    raw_key = asyncio.run(create_source(args.name, args.scopes or DEFAULT_SCOPES, database_url))
    print("Source created. Save this API key now; it will not be shown again:")
    print(raw_key)


if __name__ == "__main__":
    main()
