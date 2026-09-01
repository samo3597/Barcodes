"""Integration check for a real PostgreSQL container."""

import os

import pytest

from packages.persistence.database import build_engine, check_database


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_accepts_connections() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = build_engine(database_url)
    try:
        await check_database(engine)
    finally:
        await engine.dispose()
