"""Application configuration loaded from environment and optional `.env` file."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings for the control plane API and persistence layer."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Cloud Networking Studio"
    environment: str = "development"
    controller_mode: str = Field(
        default="manual",
        validation_alias="CNS_CONTROLLER_MODE",
    )
    # Default matches docker-compose (Postgres published on host port 5433). Override via .env.
    database_url: str = (
        "postgresql://cns_user:cns_password@localhost:5433/cloud_networking_studio"
    )


settings = Settings()
