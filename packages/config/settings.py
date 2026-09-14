"""Typed application settings loaded from environment variables."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Settings common to an HTTP service instance."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    service_name: str = Field(min_length=1)
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    database_url: str
    redis_url: str
    image_storage_root: Path = Path("/data/barcodes")
    product_cache_ttl_seconds: int = Field(default=300, ge=1, le=86_400)
    daily_request_limit: int = Field(default=1_000, ge=0)
    monthly_unique_product_limit: int = Field(default=100, ge=0)
    rate_limit_fail_open: bool = True
    internal_sync_secret: str | None = None
    internal_replay_window_seconds: int = Field(default=300, ge=30, le=3_600)
    cursor_signing_secret: str = Field(default="dev-only-cursor-secret", min_length=16)
    changes_default_limit: int = Field(default=100, ge=1, le=1_000)
    changes_max_limit: int = Field(default=1_000, ge=1, le=10_000)
    changes_retention_days: int = Field(default=365, ge=365)
    cursor_previous_signing_secret: str | None = None

    @model_validator(mode="after")
    def validate_operational_settings(self) -> "ServiceSettings":
        if self.changes_default_limit > self.changes_max_limit:
            raise ValueError("changes_default_limit must not exceed changes_max_limit")
        if self.environment == "production":
            _require_production_secret(self.internal_sync_secret, "INTERNAL_SYNC_SECRET")
            _require_production_secret(self.cursor_signing_secret, "CURSOR_SIGNING_SECRET")
            if self.cursor_previous_signing_secret:
                _require_production_secret(
                    self.cursor_previous_signing_secret, "CURSOR_PREVIOUS_SIGNING_SECRET"
                )
        return self

    @field_validator("internal_sync_secret", mode="before")
    @classmethod
    def blank_internal_secret_is_unset(cls, value: object) -> object:
        return None if value == "" else value


class WorkerSettings(BaseSettings):
    """Settings for Server 1 normalization and AI workers."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    database_url: str
    ai_provider: str = "deterministic"
    ai_prompt_version: str = "product-v1"
    image_storage_root: Path = Path("/data/barcodes")
    image_public_base_url: str = "http://localhost:8001/media"
    server2_internal_url: str | None = None
    internal_sync_secret: str | None = None

    @model_validator(mode="after")
    def validate_production_worker(self) -> "WorkerSettings":
        if self.environment == "production":
            _require_production_secret(self.internal_sync_secret, "INTERNAL_SYNC_SECRET")
            if not self.server2_internal_url:
                raise ValueError("SERVER2_INTERNAL_URL is required in production")
            if self.ai_provider == "deterministic":
                raise ValueError("deterministic AI provider is not permitted in production")
        return self

    @field_validator("server2_internal_url", "internal_sync_secret", mode="before")
    @classmethod
    def blank_optional_values_are_unset(cls, value: object) -> object:
        return None if value == "" else value


def _require_production_secret(value: str | None, name: str) -> None:
    if not value or len(value) < 32 or value.lower().startswith(("dev-", "replace-", "change-me")):
        raise ValueError(f"{name} requires an independent non-placeholder secret of 32+ characters")
