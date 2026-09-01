"""Application services coordinating ingest rules and persistence."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from packages.contracts import IngestBatchRequest
from packages.domain.identifiers import new_uuid7
from packages.domain.ingest import canonical_payload_hash, normalize_barcode
from packages.persistence.server1.models import ImportBatch
from packages.persistence.server1.repositories import (
    RevisionInsert,
    find_batch_by_idempotency_key,
    find_batch_for_source,
    insert_revisions_ignoring_duplicates,
)


class IdempotencyConflictError(Exception):
    """The same idempotency key was already used with another payload."""


class BatchNotFoundError(Exception):
    """No batch is visible in the authenticated source scope."""


@dataclass(frozen=True, slots=True)
class AcceptedBatch:
    batch: ImportBatch
    duplicate_request: bool


def _assert_matching_payload(batch: ImportBatch, request_hash: str) -> None:
    if batch.request_hash != request_hash:
        raise IdempotencyConflictError


async def accept_batch(
    session: AsyncSession,
    source_id: UUID,
    idempotency_key: str,
    payload: IngestBatchRequest,
) -> AcceptedBatch:
    """Atomically create a batch and deduplicated immutable source revisions."""

    payload_json = payload.model_dump(mode="json")
    request_hash = canonical_payload_hash(payload_json)
    existing = await find_batch_by_idempotency_key(session, source_id, idempotency_key)
    if existing is not None:
        _assert_matching_payload(existing, request_hash)
        return AcceptedBatch(existing, duplicate_request=True)

    batch = ImportBatch(
        id=new_uuid7(),
        source_id=source_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        external_batch_id=payload.external_batch_id,
        status="accepted",
        schema_version=1,
        received=len(payload.items),
    )
    session.add(batch)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        concurrent = await find_batch_by_idempotency_key(session, source_id, idempotency_key)
        if concurrent is None:
            raise
        _assert_matching_payload(concurrent, request_hash)
        return AcceptedBatch(concurrent, duplicate_request=True)

    revisions: list[RevisionInsert] = []
    for position, item in enumerate(payload.items):
        raw_payload = item.model_dump(mode="json")
        revisions.append(
            {
                "id": new_uuid7(),
                "source_id": source_id,
                "batch_id": batch.id,
                "source_record_id": item.source_record_id,
                "barcode": normalize_barcode(item.barcode),
                "payload_hash": canonical_payload_hash(raw_payload),
                "raw_payload": raw_payload,
                "schema_version": 1,
                "source_updated_at": (
                    datetime.fromisoformat(item.source_updated_at.replace("Z", "+00:00"))
                    if item.source_updated_at is not None
                    else None
                ),
                "position": position,
            }
        )
    await insert_revisions_ignoring_duplicates(session, revisions)
    await session.commit()
    return AcceptedBatch(batch, duplicate_request=False)


async def get_batch(
    session: AsyncSession,
    source_id: UUID,
    batch_id: UUID,
) -> ImportBatch:
    batch = await find_batch_for_source(session, source_id, batch_id)
    if batch is None:
        raise BatchNotFoundError
    return batch
