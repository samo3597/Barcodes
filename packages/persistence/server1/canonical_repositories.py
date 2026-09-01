"""Transactional persistence for canonical versions, images, and outbox events."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.canonical import CanonicalFields, canonical_hash, changed_fields
from packages.domain.identifiers import new_uuid7
from packages.persistence.server1.models import (
    CanonicalProduct,
    ImageAsset,
    ImageFetch,
    OutboxEvent,
    ProductVersion,
)


async def create_product_version(
    session: AsyncSession,
    fields: CanonicalFields,
    *,
    origin: str,
    origin_id: UUID | None,
    image_asset_id: UUID | None,
) -> tuple[ProductVersion, OutboxEvent | None]:
    """Lock a barcode and atomically create its next version and outbox event."""

    await session.execute(
        postgres_insert(CanonicalProduct)
        .values(barcode=fields.barcode, current_version=0)
        .on_conflict_do_nothing(index_elements=["barcode"])
    )
    product = await session.scalar(
        select(CanonicalProduct).where(CanonicalProduct.barcode == fields.barcode).with_for_update()
    )
    if product is None:
        raise RuntimeError("canonical product lock could not be acquired")

    previous = None
    if product.current_version:
        previous = await session.scalar(
            select(ProductVersion).where(
                ProductVersion.barcode == fields.barcode,
                ProductVersion.version == product.current_version,
            )
        )
    digest = canonical_hash(fields)
    if previous is not None and previous.content_hash == digest:
        return previous, None

    now = datetime.now(UTC)
    version_number = product.current_version + 1
    payload = fields.model_dump(mode="json")
    version = ProductVersion(
        barcode=fields.barcode,
        version=version_number,
        content_hash=digest,
        payload=payload,
        changed_fields=changed_fields(previous.payload if previous is not None else None, payload),
        origin=origin,
        origin_id=origin_id,
        image_asset_id=image_asset_id,
        created_at=now,
    )
    event_id = new_uuid7()
    event_payload: dict[str, Any] = {
        "event_id": str(event_id),
        "event_type": "product.upserted",
        "aggregate_id": fields.barcode,
        "aggregate_version": version_number,
        "occurred_at": now.isoformat(),
        "payload": {
            **payload,
            "version": version_number,
            "updated_at": now.isoformat(),
        },
    }
    event = OutboxEvent(
        id=event_id,
        event_type="product.upserted",
        aggregate_id=fields.barcode,
        aggregate_version=version_number,
        payload=event_payload,
        status="pending",
    )
    session.add_all([version, event])
    await session.flush()
    product.current_version = version_number
    product.current_version_id = version.id
    return version, event


async def create_image_fetch(
    session: AsyncSession,
    ai_result_id: UUID,
    source_url: str,
) -> UUID:
    """Create or resolve one durable image attempt per immutable AI result."""

    fetch_id = new_uuid7()
    inserted = (
        await session.execute(
            postgres_insert(ImageFetch)
            .values(
                id=fetch_id,
                ai_result_id=ai_result_id,
                source_url=source_url,
                status="pending",
                attempts=0,
            )
            .on_conflict_do_nothing(index_elements=["ai_result_id"])
            .returning(ImageFetch.id)
        )
    ).scalar_one_or_none()
    resolved = inserted or await session.scalar(
        select(ImageFetch.id).where(ImageFetch.ai_result_id == ai_result_id)
    )
    if resolved is None:
        raise RuntimeError("image fetch upsert did not resolve an identifier")
    return resolved


async def upsert_image_asset(
    session: AsyncSession,
    *,
    content_hash: str,
    storage_key: str,
    public_url: str,
    size_bytes: int,
    width: int,
    height: int,
) -> ImageAsset:
    asset_id = new_uuid7()
    inserted = (
        await session.execute(
            postgres_insert(ImageAsset)
            .values(
                id=asset_id,
                content_hash=content_hash,
                storage_key=storage_key,
                public_url=public_url,
                media_type="image/webp",
                size_bytes=size_bytes,
                width=width,
                height=height,
            )
            .on_conflict_do_nothing(index_elements=["content_hash"])
            .returning(ImageAsset.id)
        )
    ).scalar_one_or_none()
    resolved = inserted or await session.scalar(
        select(ImageAsset.id).where(ImageAsset.content_hash == content_hash)
    )
    if resolved is None:
        raise RuntimeError("image asset upsert did not resolve an identifier")
    asset = await session.get(ImageAsset, resolved)
    if asset is None:
        raise RuntimeError("image asset disappeared after upsert")
    return asset


async def claim_outbox_event(session: AsyncSession) -> OutboxEvent | None:
    """Claim one ready event without holding a transaction over the network."""

    now = datetime.now(UTC)
    event = await session.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.status.in_(["pending", "retry_scheduled"]),
            or_(OutboxEvent.next_attempt_at.is_(None), OutboxEvent.next_attempt_at <= now),
        )
        .order_by(OutboxEvent.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if event is None:
        return None
    event.status = "processing"
    event.attempts += 1
    event.next_attempt_at = None
    await session.commit()
    return event
