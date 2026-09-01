"""W5 signed publication and tenant read APIs against PostgreSQL."""

import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from apps.public_api.main import create_app
from packages.config import ServiceSettings
from packages.contracts import ProductUpsertedEvent, PublicProduct
from packages.domain.api_keys import generate_tenant_api_key
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server2.models import (
    AppliedEvent,
    Category,
    ChangeEvent,
    DailyUsageRollup,
    MonthlyProductUsage,
    PublishedProduct,
    Tenant,
    TenantApiKey,
)
from packages.quota import DailyRateLimitResult

SECRET = "w5-integration-secret"


class MemoryProductCache:
    def __init__(self) -> None:
        self.values: dict[str, PublicProduct] = {}
        self.deleted: list[str] = []

    async def get(self, barcode: str) -> PublicProduct | None:
        return self.values.get(barcode)

    async def set(self, product: PublicProduct) -> None:
        self.values[product.barcode] = product

    async def delete(self, barcode: str) -> None:
        self.values.pop(barcode, None)
        self.deleted.append(barcode)


class AllowAllRateLimiter:
    async def check(
        self, tenant_id: UUID, limit: int, *, now: datetime | None = None
    ) -> DailyRateLimitResult:
        current = now or datetime.now(UTC)
        return DailyRateLimitResult(
            allowed=True,
            used=1,
            limit=limit,
            reset_at=current + timedelta(days=1),
        )


def unique_gtin13() -> str:
    body = f"290{uuid4().int % 1_000_000_000:09d}"
    weighted = sum(
        int(digit) * (3 if offset % 2 == 0 else 1) for offset, digit in enumerate(reversed(body))
    )
    return f"{body}{(10 - weighted % 10) % 10}"


def event(
    barcode: str,
    category_id: str,
    version: int,
    *,
    name: str,
) -> ProductUpsertedEvent:
    return ProductUpsertedEvent(
        event_id=uuid4(),
        aggregate_id=barcode,
        aggregate_version=version,
        occurred_at=datetime.now(UTC),
        payload=PublicProduct(
            barcode=barcode,
            name=name,
            image_url=None,
            atg_code="0401",
            vat=True,
            is_weighted=False,
            category_id=category_id,
            version=version,
            quality_status="ai_processed",
            updated_at=datetime.now(UTC),
        ),
    )


def signed_request(value: ProductUpsertedEvent) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signed = b".".join([timestamp.encode(), str(value.event_id).encode(), body])
    signature = hmac.new(SECRET.encode(), signed, hashlib.sha256).hexdigest()
    return body, {
        "Content-Type": "application/json",
        "Idempotency-Key": str(value.event_id),
        "X-Event-Id": str(value.event_id),
        "X-Signature-Timestamp": timestamp,
        "X-Signature-SHA256": signature,
    }


async def put_event(
    client: AsyncClient,
    value: ProductUpsertedEvent,
) -> object:
    body, headers = signed_request(value)
    return await client.put(
        f"/internal/v1/products/{value.aggregate_id}", content=body, headers=headers
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publication_replay_version_order_auth_and_cache() -> None:
    database_url = os.getenv("TEST_SERVER2_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_SERVER2_DATABASE_URL is not configured")
    barcode = unique_gtin13()
    missing_barcode = unique_gtin13()
    category_root = f"test_{uuid4().hex}"
    category_id = f"{category_root}.dairy"
    generated = generate_tenant_api_key()
    engine = build_engine(database_url)
    session_factory = build_session_factory(engine)
    tenant = Tenant(code=f"w5-{uuid4()}", name="W5 tenant", status="active", plan_config={})
    async with session_factory() as session:
        session.add(tenant)
        await session.flush()
        session.add(
            TenantApiKey(
                tenant_id=tenant.id,
                key_prefix=generated.prefix,
                key_hash=generated.encoded_hash,
                scopes=["products:read", "categories:read"],
                status="active",
            )
        )
        await session.commit()
    tenant_id = tenant.id
    cache = MemoryProductCache()
    app = create_app(
        ServiceSettings(
            service_name="public-api-test",
            environment="test",
            database_url=database_url,
            redis_url="redis://unused:6379/0",
            internal_sync_secret=SECRET,
        ),
        product_cache=cache,
        rate_limiter=AllowAllRateLimiter(),
    )
    first = event(barcode, category_id, 1, name="Կաթ")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            applied = await put_event(client, first)
            replay = await put_event(client, first)
            assert applied.status_code == replay.status_code == 200
            assert applied.json()["status"] == replay.json()["status"] == "applied"

            same = first.model_copy(update={"event_id": uuid4()})
            ignored = await put_event(client, same)
            assert ignored.status_code == 200
            assert ignored.json()["status"] == "ignored_stale"

            third = event(barcode, category_id, 3, name="Կաթ 3")
            gap = await put_event(client, third)
            assert gap.status_code == 200
            assert gap.json()["version_gap"] is True

            second = event(barcode, category_id, 2, name="Կաթ 2")
            stale = await put_event(client, second)
            assert stale.status_code == 200
            assert stale.json()["status"] == "ignored_stale"

            conflict = event(barcode, category_id, 3, name="Conflicting version")
            conflict_response = await put_event(client, conflict)
            assert conflict_response.status_code == 409
            assert conflict_response.json()["error"]["code"] == "product_version_conflict"

            authorization = {"Authorization": f"Bearer {generated.raw_key}"}
            product = await client.get(f"/v1/products/{barcode}", headers=authorization)
            assert product.status_code == 200
            assert product.json()["data"]["name"] == "Կաթ 3"
            assert product.headers["ETag"] == f'"{barcode}:3"'

            not_modified = await client.get(
                f"/v1/products/{barcode}",
                headers={**authorization, "If-None-Match": f'"{barcode}:3"'},
            )
            assert not_modified.status_code == 304

            batch = await client.post(
                "/v1/products/batch",
                headers=authorization,
                json={"barcodes": [barcode, missing_barcode, barcode]},
            )
            assert batch.status_code == 200
            assert [item["status"] for item in batch.json()["results"]] == [
                "ok",
                "not_found",
                "ok",
            ]
            assert batch.json()["usage"]["monthly_unique_used"] == 1

            categories = await client.get("/v1/categories", headers=authorization)
            assert categories.status_code == 200
            assert category_id in {item["category_id"] for item in categories.json()["data"]}

            unauthenticated = await client.get(f"/v1/products/{barcode}")
            assert unauthenticated.status_code == 401

        async with session_factory() as session:
            await session.execute(
                delete(MonthlyProductUsage).where(MonthlyProductUsage.tenant_id == tenant_id)
            )
            await session.execute(
                delete(DailyUsageRollup).where(DailyUsageRollup.tenant_id == tenant_id)
            )
            applied_count = await session.scalar(
                select(func.count())
                .select_from(AppliedEvent)
                .where(AppliedEvent.aggregate_id == barcode)
            )
            change_count = await session.scalar(
                select(func.count()).select_from(ChangeEvent).where(ChangeEvent.barcode == barcode)
            )
            current = await session.get(PublishedProduct, barcode)
            assert applied_count == 4
            assert change_count == 2
            assert current is not None and current.version == 3
            assert cache.deleted.count(barcode) == 2
    finally:
        async with session_factory() as session:
            await session.execute(delete(ChangeEvent).where(ChangeEvent.barcode == barcode))
            await session.execute(delete(AppliedEvent).where(AppliedEvent.aggregate_id == barcode))
            await session.execute(
                delete(PublishedProduct).where(PublishedProduct.barcode == barcode)
            )
            await session.execute(delete(Category).where(Category.category_id == category_id))
            await session.execute(delete(Category).where(Category.category_id == category_root))
            await session.execute(delete(TenantApiKey).where(TenantApiKey.tenant_id == tenant_id))
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.commit()
        await engine.dispose()
