"""Race-safe monthly quota reservations and persistent usage reports."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.identifiers import new_uuid7
from packages.persistence.server2.models import DailyUsageRollup, MonthlyProductUsage


def billing_month(current: datetime) -> date:
    normalized = current.astimezone(UTC)
    return date(normalized.year, normalized.month, 1)


async def reserve_monthly_products(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    api_key_id: UUID,
    barcodes: Sequence[str],
    limit: int,
    now: datetime | None = None,
) -> tuple[set[str], int]:
    """Reserve new products in input order under one tenant-month lock."""

    unique = list(dict.fromkeys(barcodes))
    month = billing_month(now or datetime.now(UTC))
    lock_key = f"quota:{tenant_id}:{month.isoformat()}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    )
    existing = set(
        await session.scalars(
            select(MonthlyProductUsage.barcode).where(
                MonthlyProductUsage.tenant_id == tenant_id,
                MonthlyProductUsage.billing_month == month,
                MonthlyProductUsage.barcode.in_(unique),
            )
        )
    )
    used = int(
        await session.scalar(
            select(func.count())
            .select_from(MonthlyProductUsage)
            .where(
                MonthlyProductUsage.tenant_id == tenant_id,
                MonthlyProductUsage.billing_month == month,
            )
        )
        or 0
    )
    candidates = [barcode for barcode in unique if barcode not in existing]
    accepted_new = candidates[: max(0, limit - used)]
    if accepted_new:
        requested_at = now or datetime.now(UTC)
        await session.execute(
            postgresql_insert(MonthlyProductUsage),
            [
                {
                    "id": new_uuid7(),
                    "tenant_id": tenant_id,
                    "billing_month": month,
                    "barcode": barcode,
                    "first_api_key_id": api_key_id,
                    "first_requested_at": requested_at,
                }
                for barcode in accepted_new
            ],
        )
    await session.commit()
    return existing | set(accepted_new), used + len(accepted_new)


async def record_daily_request(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    limited: bool,
    now: datetime | None = None,
) -> None:
    usage_date = (now or datetime.now(UTC)).astimezone(UTC).date()
    insert = postgresql_insert(DailyUsageRollup).values(
        tenant_id=tenant_id,
        usage_date=usage_date,
        request_count=1,
        rate_limited_count=1 if limited else 0,
    )
    await session.execute(
        insert.on_conflict_do_update(
            index_elements=[DailyUsageRollup.tenant_id, DailyUsageRollup.usage_date],
            set_={
                "request_count": DailyUsageRollup.request_count + 1,
                "rate_limited_count": DailyUsageRollup.rate_limited_count + (1 if limited else 0),
                "updated_at": func.now(),
            },
        )
    )
    await session.commit()


async def load_usage(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    now: datetime | None = None,
) -> tuple[date, int, date, int]:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    month = billing_month(current)
    day = current.date()
    monthly_used = int(
        await session.scalar(
            select(func.count())
            .select_from(MonthlyProductUsage)
            .where(
                MonthlyProductUsage.tenant_id == tenant_id,
                MonthlyProductUsage.billing_month == month,
            )
        )
        or 0
    )
    daily = await session.get(DailyUsageRollup, (tenant_id, day))
    return month, monthly_used, day, 0 if daily is None else daily.request_count
