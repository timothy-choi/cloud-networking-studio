"""Application configuration loaded from environment and optional `.env` file."""

from pydantic import AliasChoices, Field
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
    # Optional regex for extra CORS origins (Starlette allow_origin_regex), e.g. Vercel previews:
    # ^https://.*\\.vercel\\.app$ — leave unset to disable.
    cors_origin_regex: str | None = Field(
        default=None,
        validation_alias="CNS_CORS_ORIGIN_REGEX",
    )
    # Default matches local Docker Compose Postgres on host 5433 (docker-compose.yml or
    # docker-compose.prod.yml). Production uses DATABASE_URL from `.env` (Compose `postgres` or RDS).
    database_url: str = Field(
        default="postgresql://cns_user:cns_password@localhost:5433/cloud_networking_studio",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    # --- Auth (JWT + bcrypt). Production must set AUTH_SECRET_KEY. ---
    auth_secret_key: str = Field(
        default="local-dev-only-change-AUTH_SECRET_KEY-in-production-min-32-chars",
        validation_alias="AUTH_SECRET_KEY",
    )
    auth_token_expire_minutes: int = Field(
        default=60 * 24 * 7,
        ge=5,
        le=60 * 24 * 365,
        validation_alias="AUTH_TOKEN_EXPIRE_MINUTES",
    )
    # When true, mutating and data APIs require a valid Bearer JWT (except /health, /auth/register, /auth/login).
    # When false (default for local development), unauthenticated requests use a built-in dev user + default project.
    auth_require_login: bool = Field(
        default=False,
        validation_alias="AUTH_REQUIRE_LOGIN",
    )


settings = Settings()
