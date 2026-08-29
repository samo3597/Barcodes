"""Database operations for Server 1 ingestion."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.persistence.server1.models import (
    ImportBatch,
    ImportBatchItem,
    Source,
    SourceApiKey,
    SourceProductRevision,
)


class RevisionInsert(TypedDict):
    id: UUID
    source_id: UUID
    batch_id: UUID
    source_record_id: str
    barcode: str
    payload_hash: str
    raw_payload: dict[str, Any]
    schema_version: int
    source_updated_at: datetime | None
    position: int


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
    revisions: Sequence[RevisionInsert],
) -> None:
    """Deduplicate revisions while retaining an item link from every batch."""

    if not revisions:
        return
    revision_rows = [
        {key: value for key, value in revision.items() if key != "position"}
        for revision in revisions
    ]
    statement = (
        postgres_insert(SourceProductRevision)
        .values(revision_rows)
        .on_conflict_do_nothing(index_elements=["source_id", "source_record_id", "payload_hash"])
        .returning(
            SourceProductRevision.id,
            SourceProductRevision.source_id,
            SourceProductRevision.source_record_id,
            SourceProductRevision.payload_hash,
        )
    )
    inserted = await session.execute(statement)
    revision_ids = {
        (row.source_id, row.source_record_id, row.payload_hash): row.id for row in inserted
    }
    missing_keys = {
        (revision["source_id"], revision["source_record_id"], revision["payload_hash"])
        for revision in revisions
        if (revision["source_id"], revision["source_record_id"], revision["payload_hash"])
        not in revision_ids
    }
    if missing_keys:
        existing = await session.execute(
            select(
                SourceProductRevision.id,
                SourceProductRevision.source_id,
                SourceProductRevision.source_record_id,
                SourceProductRevision.payload_hash,
            ).where(
                tuple_(
                    SourceProductRevision.source_id,
                    SourceProductRevision.source_record_id,
                    SourceProductRevision.payload_hash,
                ).in_(missing_keys)
            )
        )
        revision_ids.update(
            {(row.source_id, row.source_record_id, row.payload_hash): row.id for row in existing}
        )

    item_rows = []
    for revision in revisions:
        key = (revision["source_id"], revision["source_record_id"], revision["payload_hash"])
        item_rows.append(
            {
                "id": revision["id"],
                "batch_id": revision["batch_id"],
                "revision_id": revision_ids[key],
                "source_record_id": revision["source_record_id"],
                "barcode": revision["barcode"],
                "position": revision["position"],
            }
        )
    await session.execute(
        postgres_insert(ImportBatchItem)
        .values(item_rows)
        .on_conflict_do_nothing(index_elements=["batch_id", "position"])
    )
