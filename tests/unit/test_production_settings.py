"""Fail closed on unsafe production configuration."""

import pytest
from pydantic import ValidationError

from packages.config import ServiceSettings, WorkerSettings


def test_production_rejects_development_secrets() -> None:
    with pytest.raises(ValidationError, match="INTERNAL_SYNC_SECRET"):
        ServiceSettings(
            service_name="public-api",
            environment="production",
            database_url="postgresql+asyncpg://test/db",
            redis_url="redis://test/0",
        )


def test_configuration_error_does_not_echo_secret_input() -> None:
    with pytest.raises(ValidationError) as captured:
        ServiceSettings(
            service_name="public-api",
            environment="production",
            database_url="postgresql+asyncpg://test/db",
            redis_url="redis://test/0",
            internal_sync_secret="private-short-value",
        )
    assert "private-short-value" not in str(captured.value)


def test_production_accepts_non_placeholder_secrets() -> None:
    settings = ServiceSettings(
        service_name="public-api",
        environment="production",
        database_url="postgresql+asyncpg://test/db",
        redis_url="redis://test/0",
        internal_sync_secret="a" * 40,
        cursor_signing_secret="b" * 40,
    )
    assert settings.environment == "production"


def test_change_limits_must_be_consistent() -> None:
    with pytest.raises(ValidationError, match="changes_default_limit"):
        ServiceSettings(
            service_name="test",
            database_url="postgresql+asyncpg://test/db",
            redis_url="redis://test/0",
            changes_default_limit=100,
            changes_max_limit=10,
        )


def test_production_worker_rejects_fixture_ai() -> None:
    with pytest.raises(ValidationError, match="deterministic"):
        WorkerSettings(
            environment="production",
            database_url="postgresql+asyncpg://test/db",
            internal_sync_secret="a" * 40,
            server2_internal_url="https://private.example",
        )
