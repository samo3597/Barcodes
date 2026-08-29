"""Application factory for the Server 1 ingest API."""

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncEngine

from apps.ingest_api.middleware import IngestBodyMiddleware
from apps.ingest_api.routes.batches import router as batches_router
from packages.config import ServiceSettings
from packages.contracts import HealthResponse
from packages.observability.errors import install_error_handlers
from packages.observability.http import install_http_observability
from packages.observability.logging import configure_logging
from packages.persistence.database import build_engine, build_session_factory, check_database

ReadinessCheck = Callable[[], Awaitable[None]]


def load_settings() -> ServiceSettings:
    """Load Server 1 defaults, allowing environment variables to override them."""

    return ServiceSettings(
        service_name=os.getenv("SERVICE_NAME", "ingest-api"),
        database_url=os.getenv(
            "DATABASE_URL",
            os.getenv(
                "SERVER1_DATABASE_URL",
                "postgresql+asyncpg://barcodes:barcodes@postgres_server1:5432/barcodes_server1",
            ),
        ),
        redis_url=os.getenv(
            "REDIS_URL",
            os.getenv("SERVER1_REDIS_URL", "redis://redis_server1:6379/0"),
        ),
    )


def create_app(
    settings: ServiceSettings | None = None,
    readiness_check: ReadinessCheck | None = None,
) -> FastAPI:
    """Build an app whose external dependencies can be replaced in tests."""

    active_settings = settings or load_settings()
    engine: AsyncEngine = build_engine(active_settings.database_url)
    session_factory = build_session_factory(engine)
    active_readiness_check = readiness_check or (lambda: check_database(engine))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(active_settings.log_level)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="DaaS Barcodes Ingest API",
        version="0.1.0",
        lifespan=lifespan,
    )
    install_http_observability(app, active_settings.service_name)
    install_error_handlers(app)
    app.add_middleware(IngestBodyMiddleware)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.enqueue_batches = active_settings.environment != "test"
    app.include_router(batches_router)

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
