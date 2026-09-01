"""Typed application settings loaded from environment variables."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Settings common to an HTTP service instance."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    service_name: str = Field(min_length=1)
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    database_url: str
    redis_url: str
    image_storage_root: Path = Path("/data/barcodes")


class WorkerSettings(BaseSettings):
    """Settings for Server 1 normalization and AI workers."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
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

    @field_validator("server2_internal_url", "internal_sync_secret", mode="before")
    @classmethod
    def blank_optional_values_are_unset(cls, value: object) -> object:
        return None if value == "" else value
