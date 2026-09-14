"""100k-fixture ASGI/DB/cache benchmark in an explicitly isolated w8_load_* database.

This is a local closed-loop probe, not a network target-RPS certification.
"""

import argparse
import asyncio
import json
import math
import os
import time
from datetime import UTC, datetime
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from apps.public_api.main import create_app
from packages.config import ServiceSettings
from packages.contracts import ProductUpsertedEvent, PublicProduct
from packages.domain.api_keys import generate_tenant_api_key
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server2.models import Tenant, TenantApiKey
from packages.persistence.server2.repositories import apply_publication_event


def summary(samples: list[float], elapsed: float) -> dict[str, float | int]:
    ordered = sorted(samples)
    return {
        "requests": len(samples),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1] * 1000, 2),
        "achieved_rps": round(len(samples) / elapsed, 2),
    }


async def run(products: int, requests: int, concurrency: int) -> dict[str, object]:
    url = os.environ["DATABASE_URL"]
    if not (make_url(url).database or "").startswith("w8_load_"):
        raise ValueError("load probe requires a disposable w8_load_* database")
    redis_url = os.environ["REDIS_URL"]
    if not redis_url.rstrip("/").endswith("/14"):
        raise ValueError("load probe requires dedicated Redis DB 14")
    engine = build_engine(url)
    factory = build_session_factory(engine)
    generated = generate_tenant_api_key()
    tenant = Tenant(
        code=f"w8-load-{uuid4()}",
        name="Load fixture",
        status="active",
        plan_config={"daily_request_limit": 1_000_000, "monthly_unique_product_limit": products},
    )
    try:
        async with factory() as session:
            session.add(tenant)
            await session.flush()
            session.add(
                TenantApiKey(
                    tenant_id=tenant.id,
                    key_prefix=generated.prefix,
                    key_hash=generated.encoded_hash,
                    scopes=["products:read", "changes:read"],
                    status="active",
                )
            )
            await session.execute(
                text(
                    "INSERT INTO categories(category_id,name,status) "
                    "VALUES ('w8_load','Load','active') "
                    "ON CONFLICT DO NOTHING"
                )
            )
            await session.execute(
                text("""
                INSERT INTO published_products
                (barcode,name,atg_code,vat,is_weighted,category_id,version,quality_status,updated_at)
                SELECT body || ((10 - weighted % 10) % 10)::text,
                       'Փորձնական / Тест ' || n, '0401', true, false, 'w8_load', 1,
                       'source_complete', now()
                FROM (SELECT n, '299' || lpad(n::text,9,'0') AS body
                      FROM generate_series(1,:count) n) bodies
                CROSS JOIN LATERAL (
                    SELECT sum(substr(body,p,1)::int * CASE WHEN p%2=0 THEN 3 ELSE 1 END) weighted
                    FROM generate_series(1,12) p
                ) checksum
                ON CONFLICT (barcode) DO NOTHING
            """),
                {"count": products},
            )
            barcodes = list(
                await session.scalars(
                    text("SELECT barcode FROM published_products ORDER BY barcode LIMIT 100")
                )
            )
            await session.commit()
        publication_samples: list[float] = []
        for barcode in barcodes:
            started = time.perf_counter()
            async with factory() as session:
                await apply_publication_event(
                    session,
                    ProductUpsertedEvent(
                        event_id=uuid4(),
                        aggregate_id=barcode,
                        aggregate_version=2,
                        occurred_at=datetime.now(UTC),
                        payload=PublicProduct(
                            barcode=barcode,
                            name="Թարմացված / Обновлено",
                            image_url=None,
                            atg_code="0401",
                            vat=True,
                            is_weighted=False,
                            category_id="w8_load",
                            version=2,
                            quality_status="source_complete",
                            updated_at=datetime.now(UTC),
                        ),
                    ),
                )
            publication_samples.append(time.perf_counter() - started)
        app = create_app(
            ServiceSettings(
                service_name="public-api-load",
                environment="test",
                log_level="WARNING",
                database_url=url,
                redis_url=redis_url,
            )
        )
        semaphore = asyncio.Semaphore(concurrency)
        headers = {"Authorization": f"Bearer {generated.raw_key}"}
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://load"
            ) as client:

                async def request(index: int, batch: bool) -> float:
                    async with semaphore:
                        started = time.perf_counter()
                        response = (
                            await client.post(
                                "/v1/products/batch", headers=headers, json={"barcodes": barcodes}
                            )
                            if batch
                            else await client.get(
                                f"/v1/products/{barcodes[index % len(barcodes)]}", headers=headers
                            )
                        )
                        if response.status_code != 200:
                            raise RuntimeError(f"load request failed: HTTP {response.status_code}")
                        return time.perf_counter() - started

                await request(0, True)  # warm cache and monthly reservation, outside measurements
                results: dict[str, object] = {
                    "fixture_products": products,
                    "concurrency": concurrency,
                    "mode": "local-asgi",
                }
                for batch, name in [(False, "single"), (True, "batch_100")]:
                    started = time.perf_counter()
                    samples = await asyncio.gather(*(request(i, batch) for i in range(requests)))
                    results[name] = summary(samples, time.perf_counter() - started)
                results["publication_100"] = summary(publication_samples, sum(publication_samples))
                return results
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--products", type=int, default=100_000)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    if args.products < 100 or args.requests < 1 or not 1 <= args.concurrency <= 64:
        parser.error("products >= 100, requests >= 1 and concurrency 1..64 required")
    print(json.dumps(asyncio.run(run(args.products, args.requests, args.concurrency)), indent=2))


if __name__ == "__main__":
    main()
