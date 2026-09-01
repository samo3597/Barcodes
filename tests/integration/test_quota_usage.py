"""W6 monthly quota, daily rate limit, usage report, and concurrency checks."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from apps.public_api.main import create_app
from packages.config import ServiceSettings
from packages.contracts import PublicProduct
from packages.domain.api_keys import generate_tenant_api_key
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server2.models import (
    Category,
    DailyUsageRollup,
    MonthlyProductUsage,
    PublishedProduct,
    Tenant,
    TenantApiKey,
)
from packages.persistence.server2.quota_repositories import reserve_monthly_products
from packages.quota import DailyRateLimitResult


class MemoryProductCache:
    def __init__(self) -> None:
        self.values: dict[str, PublicProduct] = {}

    async def get(self, barcode: str) -> PublicProduct | None:
        return self.values.get(barcode)

    async def set(self, product: PublicProduct) -> None:
        self.values[product.barcode] = product

    async def delete(self, barcode: str) -> None:
        self.values.pop(barcode, None)


class MemoryDailyRateLimiter:
    def __init__(self) -> None:
        self.counts: dict[UUID, int] = {}

    async def check(
        self,
        tenant_id: UUID,
        limit: int,
        *,
        now: datetime | None = None,
    ) -> DailyRateLimitResult:
        used = self.counts.get(tenant_id, 0) + 1
        self.counts[tenant_id] = used
        current = now or datetime.now(UTC)
        return DailyRateLimitResult(
            allowed=used <= limit,
            used=used,
            limit=limit,
            reset_at=current + timedelta(days=1),
        )


def unique_gtin13() -> str:
    body = f"290{uuid4().int % 1_000_000_000:09d}"
    weighted = sum(
        int(digit) * (3 if offset % 2 == 0 else 1) for offset, digit in enumerate(reversed(body))
    )
    return f"{body}{(10 - weighted % 10) % 10}"


def published(barcode: str, category_id: str) -> PublishedProduct:
    return PublishedProduct(
        barcode=barcode,
        name=f"Product {barcode}",
        image_url=None,
        atg_code="0401",
        vat=True,
        is_weighted=False,
        category_id=category_id,
        version=1,
        quality_status="ai_processed",
        updated_at=datetime.now(UTC),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quota_partial_success_usage_and_daily_limit() -> None:
    database_url = os.getenv("TEST_SERVER2_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_SERVER2_DATABASE_URL is not configured")
    engine = build_engine(database_url)
    factory = build_session_factory(engine)
    category_id = f"w6_{uuid4().hex}"
    barcodes = [unique_gtin13() for _ in range(4)]
    tenant_key = generate_tenant_api_key()
    limited_key = generate_tenant_api_key()
    tenant = Tenant(
        code=f"w6-{uuid4()}",
        name="W6 tenant",
        status="active",
        plan_config={"monthly_unique_product_limit": 2, "daily_request_limit": 100},
    )
    limited_tenant = Tenant(
        code=f"w6-limited-{uuid4()}",
        name="W6 limited tenant",
        status="active",
        plan_config={"monthly_unique_product_limit": 2, "daily_request_limit": 2},
    )
    async with factory() as session:
        session.add_all([tenant, limited_tenant])
        await session.flush()
        session.add_all(
            [
                TenantApiKey(
                    tenant_id=tenant.id,
                    key_prefix=tenant_key.prefix,
                    key_hash=tenant_key.encoded_hash,
                    scopes=["products:read", "categories:read", "usage:read"],
                    status="active",
                ),
                TenantApiKey(
                    tenant_id=limited_tenant.id,
                    key_prefix=limited_key.prefix,
                    key_hash=limited_key.encoded_hash,
                    scopes=["categories:read"],
                    status="active",
                ),
            ]
        )
        session.add(Category(category_id=category_id, name="W6", status="active"))
        session.add_all(published(barcode, category_id) for barcode in barcodes[:3])
        await session.commit()
    tenant_id = tenant.id
    limited_tenant_id = limited_tenant.id
    limiter = MemoryDailyRateLimiter()
    app = create_app(
        ServiceSettings(
            service_name="public-api-w6-test",
            environment="test",
            database_url=database_url,
            redis_url="redis://unused:6379/0",
        ),
        product_cache=MemoryProductCache(),
        rate_limiter=limiter,
    )
    headers = {"Authorization": f"Bearer {tenant_key.raw_key}"}
    limited_headers = {"Authorization": f"Bearer {limited_key.raw_key}"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get(f"/v1/products/{barcodes[0]}", headers=headers)
            replay = await client.get(f"/v1/products/{barcodes[0]}", headers=headers)
            assert first.status_code == replay.status_code == 200
            assert first.headers["X-RateLimit-Remaining"] == "99"

            batch = await client.post(
                "/v1/products/batch",
                headers=headers,
                json={
                    "barcodes": [barcodes[0], barcodes[1], barcodes[2], barcodes[3], barcodes[1]]
                },
            )
            assert batch.status_code == 200
            assert [item["status"] for item in batch.json()["results"]] == [
                "ok",
                "ok",
                "quota_exceeded",
                "not_found",
                "ok",
            ]
            assert batch.json()["usage"] == {
                "monthly_unique_used": 2,
                "monthly_unique_limit": 2,
            }

            already_used = await client.get(f"/v1/products/{barcodes[0]}", headers=headers)
            denied = await client.get(f"/v1/products/{barcodes[2]}", headers=headers)
            missing = await client.get(f"/v1/products/{barcodes[3]}", headers=headers)
            assert already_used.status_code == 200
            assert denied.status_code == 429
            assert denied.json()["error"]["code"] == "monthly_unique_product_limit"
            assert missing.status_code == 404

            usage = await client.get("/v1/usage", headers=headers)
            assert usage.status_code == 200
            assert usage.json()["data"]["monthly_unique_used"] == 2
            assert usage.json()["data"]["daily_request_used"] == 7

            assert (await client.get("/v1/categories", headers=limited_headers)).status_code == 200
            assert (await client.get("/v1/categories", headers=limited_headers)).status_code == 200
            rate_denied = await client.get("/v1/categories", headers=limited_headers)
            assert rate_denied.status_code == 429
            assert rate_denied.json()["error"]["code"] == "daily_request_limit"
            assert "Retry-After" in rate_denied.headers

        async with factory() as session:
            monthly_count = await session.scalar(
                select(func.count())
                .select_from(MonthlyProductUsage)
                .where(MonthlyProductUsage.tenant_id == tenant_id)
            )
            limited_daily = await session.get(
                DailyUsageRollup,
                (limited_tenant_id, datetime.now(UTC).date()),
            )
            assert monthly_count == 2
            assert limited_daily is not None
            assert limited_daily.request_count == 3
            assert limited_daily.rate_limited_count == 1
    finally:
        async with factory() as session:
            await session.execute(
                delete(MonthlyProductUsage).where(
                    MonthlyProductUsage.tenant_id.in_([tenant_id, limited_tenant_id])
                )
            )
            await session.execute(
                delete(DailyUsageRollup).where(
                    DailyUsageRollup.tenant_id.in_([tenant_id, limited_tenant_id])
                )
            )
            await session.execute(
                delete(PublishedProduct).where(PublishedProduct.barcode.in_(barcodes))
            )
            await session.execute(
                delete(TenantApiKey).where(
                    TenantApiKey.tenant_id.in_([tenant_id, limited_tenant_id])
                )
            )
            await session.execute(
                delete(Tenant).where(Tenant.id.in_([tenant_id, limited_tenant_id]))
            )
            await session.execute(delete(Category).where(Category.category_id == category_id))
            await session.commit()
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_monthly_reservation_is_race_safe() -> None:
    database_url = os.getenv("TEST_SERVER2_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_SERVER2_DATABASE_URL is not configured")
    engine = build_engine(database_url)
    factory = build_session_factory(engine)
    tenant = Tenant(code=f"w6-race-{uuid4()}", name="W6 race", status="active", plan_config={})
    key = generate_tenant_api_key()
    async with factory() as session:
        session.add(tenant)
        await session.flush()
        api_key = TenantApiKey(
            tenant_id=tenant.id,
            key_prefix=key.prefix,
            key_hash=key.encoded_hash,
            scopes=["products:read"],
            status="active",
        )
        session.add(api_key)
        await session.commit()
    tenant_id = tenant.id
    api_key_id = api_key.id
    barcodes = [unique_gtin13() for _ in range(10)]

    async def reserve(barcode: str) -> set[str]:
        async with factory() as session:
            allowed, _ = await reserve_monthly_products(
                session,
                tenant_id=tenant_id,
                api_key_id=api_key_id,
                barcodes=[barcode],
                limit=3,
            )
            return allowed

    try:
        results = await asyncio.gather(*(reserve(barcode) for barcode in barcodes))
        assert sum(bool(result) for result in results) == 3
        async with factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(MonthlyProductUsage)
                .where(MonthlyProductUsage.tenant_id == tenant_id)
            )
            assert count == 3
    finally:
        async with factory() as session:
            await session.execute(
                delete(MonthlyProductUsage).where(MonthlyProductUsage.tenant_id == tenant_id)
            )
            await session.execute(delete(TenantApiKey).where(TenantApiKey.tenant_id == tenant_id))
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.commit()
        await engine.dispose()
