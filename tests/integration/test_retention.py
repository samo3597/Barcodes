"""Cleanup tests use a separate database because the cursor floor is global state."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.engine import make_url

from packages.persistence.database import build_engine, build_session_factory
from packages.persistence.server2.change_repositories import (
    CursorExpiredError,
    load_tenant_changes,
    prune_change_prefix,
)
from packages.persistence.server2.models import AppliedEvent, ChangeEvent, ChangeRetentionState


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prefix_cleanup_watermark_dry_run_and_empty_log() -> None:
    url = os.getenv("TEST_HARDENING_DATABASE_URL")
    if not url:
        pytest.skip("TEST_HARDENING_DATABASE_URL is required")
    assert (make_url(url).database or "").startswith("w8_test_")
    engine = build_engine(url)
    factory = build_session_factory(engine)
    cutoff = datetime.now(UTC) - timedelta(days=365)
    ids = [uuid4() for _ in range(3)]
    changes: list[ChangeEvent] = []
    try:
        async with factory() as session:
            assert await session.get(ChangeRetentionState, 1) is None
            for index, event_id in enumerate(ids):
                session.add(
                    AppliedEvent(
                        event_id=event_id,
                        event_type="product.upserted",
                        aggregate_id="4850000000007",
                        aggregate_version=index + 1,
                        response_payload={},
                    )
                )
            await session.flush()
            for index, event_id in enumerate(ids):
                change = ChangeEvent(
                    event_id=event_id,
                    change_type="upsert",
                    barcode="4850000000007",
                    version=index + 1,
                    changed_at=cutoff + timedelta(days=1 if index == 1 else -1),
                )
                session.add(change)
                await session.flush()
                changes.append(change)
            await session.commit()
        async with factory() as session:
            count, floor = await prune_change_prefix(session, retained_since=cutoff)
            assert count == 1
            assert await session.get(ChangeRetentionState, 1) is None
            assert await session.get(ChangeEvent, changes[0].change_id) is not None
        async with factory() as session:
            count, floor = await prune_change_prefix(session, retained_since=cutoff, apply=True)
            assert count == 1
            assert floor < changes[1].change_id
        async with factory() as session:
            with pytest.raises(CursorExpiredError):
                await load_tenant_changes(
                    session,
                    tenant_id=uuid4(),
                    after_change_id=changes[0].change_id,
                    limit=100,
                    retained_since=cutoff,
                    include_data=False,
                )
            # A late-arriving old timestamp with a higher ID must not expire the fresh cursor.
            await load_tenant_changes(
                session,
                tenant_id=uuid4(),
                after_change_id=changes[1].change_id,
                limit=100,
                retained_since=cutoff,
                include_data=False,
            )
            fresh = await session.get(ChangeEvent, changes[1].change_id)
            assert fresh is not None
            fresh.changed_at = cutoff - timedelta(days=1)
            await session.commit()
        async with factory() as session:
            count, _ = await prune_change_prefix(session, retained_since=cutoff, apply=True)
            assert count == 2
        async with factory() as session:
            with pytest.raises(CursorExpiredError):
                await load_tenant_changes(
                    session,
                    tenant_id=uuid4(),
                    after_change_id=changes[1].change_id,
                    limit=100,
                    retained_since=cutoff,
                    include_data=False,
                )
    finally:
        async with factory() as session:
            await session.execute(delete(ChangeEvent).where(ChangeEvent.event_id.in_(ids)))
            await session.execute(delete(AppliedEvent).where(AppliedEvent.event_id.in_(ids)))
            await session.execute(delete(ChangeRetentionState).where(ChangeRetentionState.id == 1))
            await session.commit()
        await engine.dispose()
