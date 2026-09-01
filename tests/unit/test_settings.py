"""Unit tests for environment-based service configuration."""

import pytest

from apps.ingest_api.main import load_settings as load_ingest_settings
from apps.public_api.main import load_settings as load_public_settings
from packages.config import WorkerSettings


def test_ingest_settings_accept_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://override/server1")
    monkeypatch.setenv("REDIS_URL", "redis://override/1")

    settings = load_ingest_settings()

    assert settings.database_url == "postgresql+asyncpg://override/server1"
    assert settings.redis_url == "redis://override/1"


def test_public_settings_accept_prefixed_env_file_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv(
        "SERVER2_DATABASE_URL",
        "postgresql+asyncpg://env-file/server2",
    )
    monkeypatch.setenv("SERVER2_REDIS_URL", "redis://env-file/2")

    settings = load_public_settings()

    assert settings.database_url == "postgresql+asyncpg://env-file/server2"
    assert settings.redis_url == "redis://env-file/2"


def test_worker_treats_blank_optional_publication_settings_as_disabled() -> None:
    settings = WorkerSettings(
        database_url="postgresql+asyncpg://example/server1",
        server2_internal_url="",
        internal_sync_secret="",
    )

    assert settings.server2_internal_url is None
    assert settings.internal_sync_secret is None
