"""W7 feedback idempotency and tenant-scoped cursor pagination."""

import os
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from apps.public_api.main import create_app
from packages.config import ServiceSettings
from packages.contracts import PublicProduct
from packages.domain.api_keys import generate_tenant_api_key
from packages.domain.change_cursor import decode_change_cursor, encode_change_cursor
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server2.models import (
    AppliedEvent,
    Category,
    ChangeEvent,
    DailyUsageRollup,
    FeedbackEvent,
    MonthlyProductUsage,
    PublishedProduct,
    Tenant,
    TenantApiKey,
)
from packages.quota import DailyRateLimitResult

CURSOR_SECRET = "w7-integration-cursor-secret"


class MemoryProductCache:
    async def get(self, barcode: str) -> PublicProduct | None:
        return None

    async def set(self, product: PublicProduct) -> None:
        return None

    async def delete(self, barcode: str) -> None:
        return None


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


def product(barcode: str, category_id: str, version: int = 2) -> PublishedProduct:
    return PublishedProduct(
        barcode=barcode,
        name=f"Product {barcode}",
        image_url=None,
        atg_code="0401",
        vat=True,
        is_weighted=False,
        category_id=category_id,
        version=version,
        quality_status="ai_processed",
        updated_at=datetime.now(UTC),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_feedback_and_incremental_changes() -> None:
    database_url = os.getenv("TEST_SERVER2_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_SERVER2_DATABASE_URL is not configured")
    engine = build_engine(database_url)
    factory = build_session_factory(engine)
    category_id = f"w7_{uuid4().hex}"
    delivered_barcode = unique_gtin13()
    hidden_barcode = unique_gtin13()
    old_barcode = unique_gtin13()
    barcodes = [delivered_barcode, hidden_barcode, old_barcode]
    tenant_key = generate_tenant_api_key()
    other_key = generate_tenant_api_key()
    tenant = Tenant(code=f"w7-{uuid4()}", name="W7 tenant", status="active", plan_config={})
    other = Tenant(code=f"w7-other-{uuid4()}", name="W7 other", status="active", plan_config={})
    event_ids = [uuid4() for _ in range(4)]
    now = datetime.now(UTC)
    async with factory() as session:
        session.add_all([tenant, other])
        await session.flush()
        api_key = TenantApiKey(
            tenant_id=tenant.id,
            key_prefix=tenant_key.prefix,
            key_hash=tenant_key.encoded_hash,
            scopes=["feedback:write", "changes:read"],
            status="active",
        )
        other_api_key = TenantApiKey(
            tenant_id=other.id,
            key_prefix=other_key.prefix,
            key_hash=other_key.encoded_hash,
            scopes=["changes:read"],
            status="active",
        )
        session.add_all([api_key, other_api_key])
        session.add(Category(category_id=category_id, name="W7", status="active"))
        session.add_all(product(barcode, category_id) for barcode in barcodes)
        await session.flush()
        session.add_all(
            AppliedEvent(
                event_id=event_id,
                event_type="product.upserted",
                aggregate_id=barcode,
                aggregate_version=version,
                response_payload={"status": "applied"},
            )
            for event_id, barcode, version in [
                (event_ids[0], delivered_barcode, 1),
                (event_ids[1], delivered_barcode, 2),
                (event_ids[2], hidden_barcode, 1),
                (event_ids[3], old_barcode, 1),
            ]
        )
        await session.flush()
        changes = [
            ChangeEvent(
                event_id=event_ids[0],
                change_type="upsert",
                barcode=delivered_barcode,
                version=1,
                changed_at=now - timedelta(minutes=2),
            ),
            ChangeEvent(
                event_id=event_ids[1],
                change_type="upsert",
                barcode=delivered_barcode,
                version=2,
                changed_at=now - timedelta(minutes=1),
            ),
            ChangeEvent(
                event_id=event_ids[2],
                change_type="upsert",
                barcode=hidden_barcode,
                version=1,
                changed_at=now,
            ),
            ChangeEvent(
                event_id=event_ids[3],
                change_type="upsert",
                barcode=old_barcode,
                version=1,
                changed_at=now - timedelta(days=366),
            ),
        ]
        session.add_all(changes)
        await session.flush()
        old_change_id = changes[3].change_id
        session.add_all(
            MonthlyProductUsage(
                tenant_id=tenant.id,
                billing_month=date(now.year, now.month, 1),
                barcode=barcode,
                first_api_key_id=api_key.id,
            )
            for barcode in [delivered_barcode, old_barcode]
        )
        await session.commit()
    tenant_id = tenant.id
    other_id = other.id
    app = create_app(
        ServiceSettings(
            service_name="public-api-w7-test",
            environment="test",
            database_url=database_url,
            redis_url="redis://unused:6379/0",
            cursor_signing_secret=CURSOR_SECRET,
        ),
        product_cache=MemoryProductCache(),
        rate_limiter=AllowAllRateLimiter(),
    )
    headers = {"Authorization": f"Bearer {tenant_key.raw_key}"}
    feedback = {
        "barcode": delivered_barcode,
        "product_version": 2,
        "action": "corrected",
        "operator_ref": "operator-12",
        "fields": {"vat": {"suggested": True, "corrected": False}},
        "client_created_at": now.isoformat(),
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first_feedback = await client.post(
                "/v1/feedback",
                headers={**headers, "Idempotency-Key": "1c-db-17-event-000042"},
                json=feedback,
            )
            replay = await client.post(
                "/v1/feedback",
                headers={**headers, "Idempotency-Key": "1c-db-17-event-000042"},
                json=feedback,
            )
            assert first_feedback.status_code == replay.status_code == 202
            assert first_feedback.json()["event_id"] == replay.json()["event_id"]
            assert first_feedback.json()["duplicate_request"] is False
            assert replay.json()["duplicate_request"] is True

            changed_feedback = {**feedback, "operator_ref": "different"}
            conflict = await client.post(
                "/v1/feedback",
                headers={**headers, "Idempotency-Key": "1c-db-17-event-000042"},
                json=changed_feedback,
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "idempotency_conflict"

            not_delivered = await client.post(
                "/v1/feedback",
                headers={**headers, "Idempotency-Key": "hidden-product-feedback"},
                json={**feedback, "barcode": hidden_barcode, "product_version": 1},
            )
            assert not_delivered.status_code == 422
            assert not_delivered.json()["error"]["code"] == "invalid_feedback_product"

            page_one = await client.get("/v1/changes?limit=1&include=data", headers=headers)
            assert page_one.status_code == 200
            assert page_one.json()["has_more"] is True
            assert len(page_one.json()["changes"]) == 1
            assert page_one.json()["changes"][0]["barcode"] == delivered_barcode
            assert page_one.json()["changes"][0]["data"]["version"] == 2

            page_two = await client.get(
                "/v1/changes",
                headers=headers,
                params={"cursor": page_one.json()["next_cursor"], "limit": 1},
            )
            assert page_two.status_code == 200
            assert page_two.json()["has_more"] is False
            assert page_two.json()["changes"][0]["version"] == 2

            wrong_tenant = await client.get(
                "/v1/changes",
                headers={"Authorization": f"Bearer {other_key.raw_key}"},
                params={"cursor": page_one.json()["next_cursor"]},
            )
            assert wrong_tenant.status_code == 400
            assert wrong_tenant.json()["error"]["code"] == "invalid_cursor"

            app.state.cursor_previous_signing_secret = CURSOR_SECRET
            app.state.cursor_signing_secret = "w8-rotated-cursor-secret"
            rotated = await client.get(
                "/v1/changes",
                headers=headers,
                params={"cursor": page_one.json()["next_cursor"]},
            )
            assert rotated.status_code == 200
            assert (
                decode_change_cursor(
                    rotated.json()["next_cursor"], tenant_id, "w8-rotated-cursor-secret"
                )
                > 0
            )

            expired = await client.get(
                "/v1/changes",
                headers=headers,
                params={"cursor": encode_change_cursor(old_change_id, tenant_id, CURSOR_SECRET)},
            )
            assert expired.status_code == 410
            assert expired.json()["error"]["code"] == "cursor_expired"

        async with factory() as session:
            stored_feedback = await session.scalar(
                select(func.count())
                .select_from(FeedbackEvent)
                .where(FeedbackEvent.tenant_id == tenant_id)
            )
            unchanged = await session.get(PublishedProduct, delivered_barcode)
            usage_count = await session.scalar(
                select(func.count())
                .select_from(MonthlyProductUsage)
                .where(MonthlyProductUsage.tenant_id == tenant_id)
            )
            assert stored_feedback == 1
            assert unchanged is not None and unchanged.vat is True
            assert usage_count == 2
    finally:
        async with factory() as session:
            await session.execute(
                delete(FeedbackEvent).where(FeedbackEvent.tenant_id.in_([tenant_id, other_id]))
            )
            await session.execute(
                delete(MonthlyProductUsage).where(
                    MonthlyProductUsage.tenant_id.in_([tenant_id, other_id])
                )
            )
            await session.execute(
                delete(DailyUsageRollup).where(
                    DailyUsageRollup.tenant_id.in_([tenant_id, other_id])
                )
            )
            await session.execute(delete(ChangeEvent).where(ChangeEvent.barcode.in_(barcodes)))
            await session.execute(
                delete(AppliedEvent).where(AppliedEvent.aggregate_id.in_(barcodes))
            )
            await session.execute(
                delete(PublishedProduct).where(PublishedProduct.barcode.in_(barcodes))
            )
            await session.execute(
                delete(TenantApiKey).where(TenantApiKey.tenant_id.in_([tenant_id, other_id]))
            )
            await session.execute(delete(Tenant).where(Tenant.id.in_([tenant_id, other_id])))
            await session.execute(delete(Category).where(Category.category_id == category_id))
            await session.commit()
        await engine.dispose()
