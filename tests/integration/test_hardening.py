"""W8 outage, security, UTF-8 and reconnect tests with real PostgreSQL."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from apps.public_api.main import create_app
from packages.cache import RedisProductCache
from packages.config import ServiceSettings
from packages.domain.api_keys import generate_tenant_api_key
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server2.models import (
    Category,
    DailyUsageRollup,
    FeedbackEvent,
    MonthlyProductUsage,
    PublishedProduct,
    Tenant,
    TenantApiKey,
)
from packages.quota import RedisDailyRateLimiter


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_outage_key_security_utf8_and_pool_reconnect() -> None:
    url = os.getenv("TEST_SERVER2_DATABASE_URL")
    if not url:
        pytest.skip("TEST_SERVER2_DATABASE_URL is required")
    engine = build_engine(url)
    factory = build_session_factory(engine)
    # Valid GTIN chosen randomly so no user product is overwritten.
    body = f"298{uuid4().int % 1_000_000_000:09d}"
    weight = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    barcode = f"{body}{(10 - weight % 10) % 10}"
    category_id = f"w8_{uuid4().hex}"
    tenant = Tenant(code=f"w8-{uuid4()}", name="Hardening", status="active", plan_config={})
    generated = generate_tenant_api_key()
    async with factory() as session:
        session.add(tenant)
        await session.flush()
        key = TenantApiKey(
            tenant_id=tenant.id,
            key_prefix=generated.prefix,
            key_hash=generated.encoded_hash,
            scopes=["products:read", "feedback:write"],
            status="active",
        )
        session.add(key)
        session.add(Category(category_id=category_id, name="Փորձ / Тест", status="active"))
        await session.flush()
        session.add(
            PublishedProduct(
                barcode=barcode,
                name="Կաթ / Молоко",
                atg_code="0401",
                vat=True,
                is_weighted=False,
                category_id=category_id,
                version=1,
                quality_status="source_complete",
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()
    key_id, tenant_id = key.id, tenant.id
    unavailable = "redis://127.0.0.1:1/0"
    app = create_app(
        ServiceSettings(
            service_name="public-api-w8",
            environment="test",
            database_url=url,
            redis_url=unavailable,
        ),
        product_cache=RedisProductCache(unavailable),
        rate_limiter=RedisDailyRateLimiter(unavailable, fail_open=True),
    )
    headers = {"Authorization": f"Bearer {generated.raw_key}"}
    closed_limiter = RedisDailyRateLimiter(unavailable, fail_open=False)
    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                product = await client.get(f"/v1/products/{barcode}", headers=headers)
                assert product.status_code == 200
                assert product.json()["data"]["name"] == "Կաթ / Молоко"
                assert 'outcome="limiter_degraded"' in (await client.get("/metrics")).text
                # Dispose the actual pool, then establish a fresh DB connection on the next request.
                await app.state.session_factory.kw["bind"].dispose()
                assert (
                    await client.get(f"/v1/products/{barcode}", headers=headers)
                ).status_code == 200
                feedback = await client.post(
                    "/v1/feedback",
                    headers={**headers, "Idempotency-Key": "utf8", "X-Request-ID": "x" * 128},
                    json={
                        "barcode": barcode,
                        "product_version": 1,
                        "action": "accepted",
                        "client_created_at": datetime.now(UTC).isoformat(),
                    },
                )
                assert feedback.status_code == 202
                assert feedback.json()["request_id"] == "x" * 128
                invalid_feedback = await client.post(
                    "/v1/feedback",
                    headers={**headers, "Idempotency-Key": "invalid-field"},
                    json={
                        "barcode": barcode,
                        "product_version": 1,
                        "action": "corrected",
                        "fields": {"vat": {"suggested": True, "corrected": "not-a-bool"}},
                        "client_created_at": datetime.now(UTC).isoformat(),
                    },
                )
                assert invalid_feedback.status_code == 422
                assert invalid_feedback.json()["error"]["code"] == "validation_error"
                app.state.rate_limiter = closed_limiter
                blocked = await client.get(f"/v1/products/{barcode}", headers=headers)
                assert blocked.status_code == 503
                assert blocked.json()["error"]["code"] == "rate_limiter_unavailable"
                async with factory() as session:
                    row = await session.get(TenantApiKey, key_id)
                    assert row is not None
                    row.status = "revoked"
                    await session.commit()
                assert (
                    await client.get(f"/v1/products/{barcode}", headers=headers)
                ).status_code == 401
                async with factory() as session:
                    row = await session.get(TenantApiKey, key_id)
                    assert row is not None
                    row.status = "active"
                    row.scopes = []
                    await session.commit()
                assert (
                    await client.get(f"/v1/products/{barcode}", headers=headers)
                ).status_code == 403
    finally:
        await closed_limiter.close()
        async with factory() as session:
            for model in [FeedbackEvent, MonthlyProductUsage, DailyUsageRollup]:
                await session.execute(delete(model).where(model.tenant_id == tenant_id))
            await session.execute(
                delete(PublishedProduct).where(PublishedProduct.barcode == barcode)
            )
            await session.execute(delete(Category).where(Category.category_id == category_id))
            await session.execute(delete(TenantApiKey).where(TenantApiKey.tenant_id == tenant_id))
            await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
            await session.commit()
        await engine.dispose()
