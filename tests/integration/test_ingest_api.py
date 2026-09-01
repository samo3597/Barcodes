"""End-to-end ingest API checks against a real PostgreSQL database."""

import copy
import gzip
import json
import os
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from apps.ingest_api.main import create_app
from packages.config import ServiceSettings
from packages.domain.api_keys import generate_source_api_key
from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server1.models import (
    ImportBatch,
    Source,
    SourceApiKey,
    SourceProductRevision,
)


def batch_payload() -> dict[str, object]:
    return {
        "external_batch_id": "export-001",
        "items": [
            {
                "source_record_id": "item-4421",
                "barcode": "4850000000007",
                "name": "Թթվասեր 20 տոկոս 800գ",
                "image_url": "https://source.example/item-4421.jpg",
                "atg_code": "0403",
                "vat": True,
                "is_weighted": False,
                "category": "Կաթնամթերք",
                "source_updated_at": "2026-08-25T08:00:00+04:00",
                "attributes": {"brand": "Example", "package": "800 գ"},
            }
        ],
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_authenticated_batch_is_idempotent_and_queryable() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = build_engine(database_url)
    session_factory = build_session_factory(engine)
    generated = generate_source_api_key()
    reader_only = generate_source_api_key()
    source = Source(name=f"integration-{uuid4()}", status="active", field_priorities={})
    async with session_factory() as session:
        session.add(source)
        await session.flush()
        session.add(
            SourceApiKey(
                source_id=source.id,
                key_prefix=generated.prefix,
                key_hash=generated.encoded_hash,
                scopes=["ingest:write", "batches:read"],
                status="active",
            )
        )
        session.add(
            SourceApiKey(
                source_id=source.id,
                key_prefix=reader_only.prefix,
                key_hash=reader_only.encoded_hash,
                scopes=["batches:read"],
                status="active",
            )
        )
        await session.commit()
    source_id = source.id

    settings = ServiceSettings(
        service_name="ingest-api-test",
        environment="test",
        database_url=database_url,
        redis_url="redis://unused:6379/0",
    )
    app = create_app(settings=settings)
    headers = {
        "Authorization": f"Bearer {generated.raw_key}",
        "Idempotency-Key": "integration-batch-001",
    }
    payload = batch_payload()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            missing_key = await client.post("/ingest/v1/batches", json=payload)
            assert missing_key.status_code == 401

            insufficient_scope = await client.post(
                "/ingest/v1/batches",
                json=payload,
                headers={
                    "Authorization": f"Bearer {reader_only.raw_key}",
                    "Idempotency-Key": "scope-test",
                },
            )
            assert insufficient_scope.status_code == 403
            assert insufficient_scope.json()["error"]["code"] == "insufficient_scope"

            first = await client.post("/ingest/v1/batches", json=payload, headers=headers)
            assert first.status_code == 202
            assert first.json()["duplicate_request"] is False
            batch_id = UUID(first.json()["batch_id"])

            replay = await client.post(
                "/ingest/v1/batches",
                content=gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
                headers={
                    **headers,
                    "Content-Encoding": "gzip",
                    "Content-Type": "application/json",
                },
            )
            assert replay.status_code == 202
            assert replay.json()["batch_id"] == str(batch_id)
            assert replay.json()["duplicate_request"] is True

            changed_payload = copy.deepcopy(payload)
            items = changed_payload["items"]
            assert isinstance(items, list)
            item = items[0]
            assert isinstance(item, dict)
            item["name"] = "Այլ անվանում"
            conflict = await client.post(
                "/ingest/v1/batches",
                json=changed_payload,
                headers=headers,
            )
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "idempotency_conflict"

            status_response = await client.get(
                f"/ingest/v1/batches/{batch_id}",
                headers={"Authorization": f"Bearer {generated.raw_key}"},
            )
            assert status_response.status_code == 200
            assert status_response.json()["received"] == 1

            second_batch = await client.post(
                "/ingest/v1/batches",
                json=payload,
                headers={**headers, "Idempotency-Key": "integration-batch-002"},
            )
            assert second_batch.status_code == 202
            assert second_batch.json()["duplicate_request"] is False

        async with session_factory() as session:
            batch_count = await session.scalar(
                select(func.count())
                .select_from(ImportBatch)
                .where(ImportBatch.source_id == source_id)
            )
            revision_count = await session.scalar(
                select(func.count())
                .select_from(SourceProductRevision)
                .where(SourceProductRevision.source_id == source_id)
            )
            revision = await session.scalar(
                select(SourceProductRevision).where(
                    SourceProductRevision.source_id == source_id,
                    SourceProductRevision.source_record_id == "item-4421",
                )
            )
            assert batch_count == 2
            assert revision_count == 1
            assert revision is not None
            assert revision.barcode == "4850000000007"
            assert revision.raw_payload["name"] == "Թթվասեր 20 տոկոս 800գ"
            assert revision.raw_payload["image_url"] == "https://source.example/item-4421.jpg"
    finally:
        await app.state.engine.dispose()
        async with session_factory() as session:
            await session.execute(
                delete(SourceProductRevision).where(SourceProductRevision.source_id == source_id)
            )
            await session.execute(delete(ImportBatch).where(ImportBatch.source_id == source_id))
            await session.execute(delete(SourceApiKey).where(SourceApiKey.source_id == source_id))
            await session.execute(delete(Source).where(Source.id == source_id))
            await session.commit()
        await engine.dispose()
