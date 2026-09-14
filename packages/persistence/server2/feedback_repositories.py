"""Append-only tenant feedback persistence."""

from typing import cast
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.contracts import FeedbackRequest
from packages.domain.identifiers import new_uuid7
from packages.domain.ingest import canonical_payload_hash
from packages.persistence.server2.models import FeedbackEvent, MonthlyProductUsage, PublishedProduct


class FeedbackIdempotencyConflictError(ValueError):
    """An idempotency key was reused with a different semantic request."""


class FeedbackProductError(ValueError):
    """Feedback targets an unknown product or a future version."""


async def append_feedback(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    api_key_id: UUID,
    idempotency_key: str,
    request_id: str,
    feedback: FeedbackRequest,
) -> tuple[UUID, bool]:
    request_hash = canonical_payload_hash(feedback.model_dump(mode="json"))
    existing = await _find_existing(session, tenant_id, idempotency_key)
    if existing is not None:
        _ensure_same_request(existing, request_hash)
        return existing.event_id, True

    product = await session.get(PublishedProduct, feedback.barcode)
    if product is None:
        raise FeedbackProductError("feedback product was not found")
    was_delivered = await session.scalar(
        select(
            exists().where(
                MonthlyProductUsage.tenant_id == tenant_id,
                MonthlyProductUsage.barcode == feedback.barcode,
            )
        )
    )
    if not was_delivered:
        raise FeedbackProductError("feedback product was not delivered to this tenant")
    if feedback.product_version > product.version:
        raise FeedbackProductError("feedback product_version is newer than the published product")

    event_id = new_uuid7()
    inserted = await session.scalar(
        postgresql_insert(FeedbackEvent)
        .values(
            event_id=event_id,
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            barcode=feedback.barcode,
            product_version=feedback.product_version,
            action=feedback.action,
            operator_ref=feedback.operator_ref,
            fields={key: value.model_dump(mode="json") for key, value in feedback.fields.items()},
            client_created_at=feedback.client_created_at,
            request_id=request_id,
        )
        .on_conflict_do_nothing(constraint="uq_feedback_tenant_idempotency")
        .returning(FeedbackEvent.event_id)
    )
    await session.commit()
    if inserted is not None:
        return inserted, False

    existing = await _find_existing(session, tenant_id, idempotency_key)
    if existing is None:  # defensive: the conflicting row cannot disappear under normal operation
        raise RuntimeError("idempotent feedback conflict could not be resolved")
    _ensure_same_request(existing, request_hash)
    return existing.event_id, True


async def _find_existing(
    session: AsyncSession, tenant_id: UUID, idempotency_key: str
) -> FeedbackEvent | None:
    return cast(
        FeedbackEvent | None,
        await session.scalar(
            select(FeedbackEvent).where(
                FeedbackEvent.tenant_id == tenant_id,
                FeedbackEvent.idempotency_key == idempotency_key,
            )
        ),
    )


def _ensure_same_request(event: FeedbackEvent, request_hash: str) -> None:
    if event.request_hash != request_hash:
        raise FeedbackIdempotencyConflictError(
            "Idempotency-Key was already used with a different feedback payload"
        )
