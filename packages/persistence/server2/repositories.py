"""Server 2 authentication, read-model, and publication operations."""

from collections.abc import Sequence

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.contracts import ProductUpsertedEvent, PublicationApplyResponse, PublicProduct
from packages.persistence.server2.models import (
    AppliedEvent,
    Category,
    ChangeEvent,
    PublishedProduct,
    Tenant,
    TenantApiKey,
)


class VersionConflictError(ValueError):
    """The same aggregate version arrived with different public data."""


async def find_tenant_key_by_prefix(
    session: AsyncSession,
    prefix: str,
) -> tuple[TenantApiKey, Tenant] | None:
    row = await session.execute(
        select(TenantApiKey, Tenant)
        .join(Tenant, Tenant.id == TenantApiKey.tenant_id)
        .where(TenantApiKey.key_prefix == prefix)
    )
    resolved = row.one_or_none()
    return None if resolved is None else (resolved[0], resolved[1])


def product_contract(row: PublishedProduct) -> PublicProduct:
    return PublicProduct(
        barcode=row.barcode,
        name=row.name,
        image_url=row.image_url,
        atg_code=row.atg_code,
        vat=row.vat,
        is_weighted=row.is_weighted,
        category_id=row.category_id,
        version=row.version,
        quality_status=row.quality_status,
        updated_at=row.updated_at,
    )


async def load_product(session: AsyncSession, barcode: str) -> PublicProduct | None:
    row = await session.get(PublishedProduct, barcode)
    if row is None or row.quality_status == "disabled":
        return None
    return product_contract(row)


async def load_products(
    session: AsyncSession,
    barcodes: Sequence[str],
) -> dict[str, PublicProduct]:
    if not barcodes:
        return {}
    rows = await session.scalars(
        select(PublishedProduct).where(
            PublishedProduct.barcode.in_(barcodes),
            PublishedProduct.quality_status != "disabled",
        )
    )
    return {row.barcode: product_contract(row) for row in rows}


async def list_active_categories(session: AsyncSession) -> list[Category]:
    return list(
        await session.scalars(
            select(Category).where(Category.status == "active").order_by(Category.category_id)
        )
    )


async def _ensure_category_tree(session: AsyncSession, category_id: str) -> None:
    segments = category_id.split(".")
    parent_id = None
    for index in range(1, len(segments) + 1):
        current_id = ".".join(segments[:index])
        await session.execute(
            postgresql_insert(Category)
            .values(
                category_id=current_id,
                name=segments[index - 1].replace("_", " ").title(),
                parent_id=parent_id,
                status="active",
            )
            .on_conflict_do_nothing(index_elements=[Category.category_id])
        )
        parent_id = current_id


def _same_snapshot(current: PublishedProduct, incoming: PublicProduct) -> bool:
    return product_contract(current).model_dump(mode="json") == incoming.model_dump(mode="json")


async def apply_publication_event(
    session: AsyncSession,
    event: ProductUpsertedEvent,
) -> tuple[PublicationApplyResponse, bool]:
    """Atomically deduplicate an event and apply only a newer Server 1 snapshot."""

    existing = await session.get(AppliedEvent, event.event_id)
    if existing is not None:
        return PublicationApplyResponse.model_validate(existing.response_payload), False

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:barcode, 0))"),
        {"barcode": event.aggregate_id},
    )
    existing = await session.get(AppliedEvent, event.event_id)
    if existing is not None:
        return PublicationApplyResponse.model_validate(existing.response_payload), False

    current = await session.get(PublishedProduct, event.aggregate_id)
    if current is not None and current.version == event.aggregate_version:
        if not _same_snapshot(current, event.payload):
            raise VersionConflictError("aggregate version already exists with different data")
        status = "ignored_stale"
    elif current is not None and current.version > event.aggregate_version:
        status = "ignored_stale"
    else:
        status = "applied"

    version_gap = (
        status == "applied"
        and current is not None
        and event.aggregate_version > current.version + 1
    )
    response = PublicationApplyResponse(
        event_id=event.event_id,
        barcode=event.aggregate_id,
        version=event.aggregate_version,
        status=status,
        version_gap=version_gap,
    )
    applied = AppliedEvent(
        event_id=event.event_id,
        event_type=event.event_type,
        aggregate_id=event.aggregate_id,
        aggregate_version=event.aggregate_version,
        response_payload=response.model_dump(mode="json"),
    )
    session.add(applied)
    if status == "applied":
        if event.event_type == "product.disabled" and event.payload.quality_status != "disabled":
            raise ValueError("product.disabled event requires disabled quality_status")
        await _ensure_category_tree(session, event.payload.category_id)
        values = event.payload.model_dump(mode="python")
        if current is None:
            current = PublishedProduct(**values)
            session.add(current)
        else:
            for field, value in values.items():
                setattr(current, field, value)
        await session.flush()
        # Serialize ID allocation through commit so a cursor never skips a
        # lower-ID publication that is still uncommitted on another connection.
        await session.execute(text("SELECT pg_advisory_xact_lock(8172008)"))
        session.add(
            ChangeEvent(
                event_id=event.event_id,
                change_type="disabled" if event.event_type == "product.disabled" else "upsert",
                barcode=event.aggregate_id,
                version=event.aggregate_version,
                changed_at=event.occurred_at,
            )
        )
    await session.commit()
    return response, status == "applied"
