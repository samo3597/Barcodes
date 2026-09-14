"""Tenant-scoped incremental reads from the immutable change log."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.persistence.server2.models import ChangeEvent, MonthlyProductUsage, PublishedProduct


class CursorExpiredError(ValueError):
    """The requested position is outside the configured retention window."""


async def load_tenant_changes(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    after_change_id: int,
    limit: int,
    retained_since: datetime,
    include_data: bool,
) -> tuple[list[ChangeEvent], bool, dict[str, PublishedProduct]]:
    if after_change_id:
        cursor_time = await session.scalar(
            select(ChangeEvent.changed_at).where(ChangeEvent.change_id == after_change_id)
        )
        if cursor_time is not None and cursor_time < retained_since:
            raise CursorExpiredError("cursor is older than the change retention window")
        if cursor_time is None:
            oldest_retained = await session.scalar(
                select(ChangeEvent.change_id)
                .where(ChangeEvent.changed_at >= retained_since)
                .order_by(ChangeEvent.change_id)
                .limit(1)
            )
            if oldest_retained is not None and after_change_id < oldest_retained:
                raise CursorExpiredError("cursor is older than the change retention window")

    delivered = exists(
        select(MonthlyProductUsage.id).where(
            MonthlyProductUsage.tenant_id == tenant_id,
            MonthlyProductUsage.barcode == ChangeEvent.barcode,
        )
    )
    rows = list(
        await session.scalars(
            select(ChangeEvent)
            .where(
                ChangeEvent.change_id > after_change_id,
                ChangeEvent.changed_at >= retained_since,
                delivered,
            )
            .order_by(ChangeEvent.change_id)
            .limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    products: dict[str, PublishedProduct] = {}
    if include_data and rows:
        current = await session.scalars(
            select(PublishedProduct).where(
                PublishedProduct.barcode.in_({row.barcode for row in rows})
            )
        )
        products = {product.barcode: product for product in current}
    return rows, has_more, products
