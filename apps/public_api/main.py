"""Application factory for the Server 2 public API."""

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncEngine

from apps.public_api.routes.internal import router as internal_router
from apps.public_api.routes.products import router as products_router
from packages.cache import ProductCache, RedisProductCache
from packages.config import ServiceSettings
from packages.contracts import HealthResponse
from packages.observability.errors import install_error_handlers
from packages.observability.http import install_http_observability
from packages.observability.logging import configure_logging
from packages.persistence.database import build_engine, build_session_factory, check_database

ReadinessCheck = Callable[[], Awaitable[None]]


def load_settings() -> ServiceSettings:
    """Load Server 2 defaults, allowing environment variables to override them."""

    return ServiceSettings(
        service_name=os.getenv("SERVICE_NAME", "public-api"),
        database_url=os.getenv(
            "DATABASE_URL",
            os.getenv(
                "SERVER2_DATABASE_URL",
                "postgresql+asyncpg://barcodes:barcodes@postgres_server2:5432/barcodes_server2",
            ),
        ),
        redis_url=os.getenv(
            "REDIS_URL",
            os.getenv("SERVER2_REDIS_URL", "redis://redis_server2:6379/0"),
        ),
    )


def create_app(
    settings: ServiceSettings | None = None,
    readiness_check: ReadinessCheck | None = None,
    product_cache: ProductCache | None = None,
) -> FastAPI:
    """Build an independently deployable Server 2 application."""

    active_settings = settings or load_settings()
    engine: AsyncEngine = build_engine(active_settings.database_url)
    session_factory = build_session_factory(engine)
    active_cache = product_cache or RedisProductCache(
        active_settings.redis_url,
        active_settings.product_cache_ttl_seconds,
    )
    active_readiness_check = readiness_check or (lambda: check_database(engine))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(active_settings.log_level)
        try:
            yield
        finally:
            await engine.dispose()
            if isinstance(active_cache, RedisProductCache):
                await active_cache.close()

    app = FastAPI(
        title="DaaS Barcodes Public API",
        version="0.1.0",
        lifespan=lifespan,
    )
    install_http_observability(app, active_settings.service_name)
    install_error_handlers(app)
    app.state.session_factory = session_factory
    app.state.product_cache = active_cache
    app.state.internal_sync_secret = active_settings.internal_sync_secret
    app.state.internal_replay_window_seconds = active_settings.internal_replay_window_seconds
    app.include_router(internal_router)
    app.include_router(products_router)

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse(status="alive", service=active_settings.service_name)

    @app.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def readiness() -> HealthResponse:
        try:
            await active_readiness_check()
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "dependency_not_ready",
                    "message": "database is not ready",
                    "retryable": True,
                },
            ) from error
        return HealthResponse(status="ready", service=active_settings.service_name)

    return app


app = create_app()
