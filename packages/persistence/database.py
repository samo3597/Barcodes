"""Async SQLAlchemy engine lifecycle and readiness checks."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str) -> AsyncEngine:
    """Create a service-owned engine without connecting immediately."""

    return create_async_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create short-lived sessions with explicit transaction boundaries."""

    return async_sessionmaker(engine, expire_on_commit=False)


async def check_database(engine: AsyncEngine) -> None:
    """Raise when PostgreSQL cannot execute a minimal query."""

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


@asynccontextmanager
async def engine_lifespan(engine: AsyncEngine) -> AsyncIterator[None]:
    """Dispose pooled connections when an application stops."""

    try:
        yield
    finally:
        await engine.dispose()
