"""Database operations for Server 1 ingestion."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.persistence.server1.models import (
    ImportBatch,
    Source,
    SourceApiKey,
    SourceProductRevision,
)


async def find_api_key_by_prefix(
    session: AsyncSession,
    prefix: str,
) -> tuple[SourceApiKey, Source] | None:
    """Resolve a short public prefix before expensive hash verification."""

    result = await session.execute(
        select(SourceApiKey, Source)
        .join(Source, Source.id == SourceApiKey.source_id)
        .where(SourceApiKey.key_prefix == prefix)
    )
    row = result.one_or_none()
    return (row[0], row[1]) if row is not None else None


async def find_batch_by_idempotency_key(
    session: AsyncSession,
    source_id: UUID,
    idempotency_key: str,
) -> ImportBatch | None:
    result = await session.execute(
        select(ImportBatch).where(
            ImportBatch.source_id == source_id,
            ImportBatch.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def find_batch_for_source(
    session: AsyncSession,
    source_id: UUID,
    batch_id: UUID,
) -> ImportBatch | None:
    result = await session.execute(
        select(ImportBatch).where(
            ImportBatch.id == batch_id,
            ImportBatch.source_id == source_id,
        )
    )
    return result.scalar_one_or_none()


async def insert_revisions_ignoring_duplicates(
    session: AsyncSession,
    revisions: Sequence[dict[str, object]],
) -> None:
    """Keep one immutable copy of an identical source record payload."""

    if not revisions:
        return
    statement = (
        postgres_insert(SourceProductRevision)
        .values(list(revisions))
        .on_conflict_do_nothing(index_elements=["source_id", "source_record_id", "payload_hash"])
    )
    await session.execute(statement)
