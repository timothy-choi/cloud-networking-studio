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
    environment: str = Field(
        default="development",
        validation_alias="CNS_ENVIRONMENT",
    )
    controller_mode: str = Field(
        default="manual",
        validation_alias="CNS_CONTROLLER_MODE",
    )
    # Comma-separated browser origins for CORS (include your public UI URL in production).
    cors_origins: str = Field(
        default="http://localhost:5174,http://127.0.0.1:5174",
        validation_alias="CNS_CORS_ORIGINS",
    )
    # Default matches docker-compose (Postgres published on host port 5433). Override via .env.
    database_url: str = (
        "postgresql://cns_user:cns_password@localhost:5433/cloud_networking_studio"
    )


settings = Settings()
