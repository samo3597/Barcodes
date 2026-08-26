"""Typed application settings loaded from environment variables."""

from typing import Literal

from pydantic import Field
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
