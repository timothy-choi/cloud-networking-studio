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
    # When false (default for local development), unauthenticated requests use a built-in dev user + default project
    # for those routes only — GET /auth/me always requires a Bearer token (see app.api.deps.require_bearer_user).
    auth_require_login: bool = Field(
        default=False,
        validation_alias="AUTH_REQUIRE_LOGIN",
    )
    # --- Optional Go runtime runner (RUNTIME_EXECUTOR=go) ---
    runtime_executor: str = Field(
        default="python",
        validation_alias=AliasChoices("RUNTIME_EXECUTOR", "runtime_executor"),
        description="python: docker-py in API process; go: delegate deploy/destroy/logs/traffic to cns-runner",
    )
    go_runner_url: str = Field(
        default="http://runner:8090",
        validation_alias="GO_RUNNER_URL",
    )
    go_runner_timeout_seconds: float = Field(
        default=600.0,
        ge=5.0,
        le=3600.0,
        validation_alias="GO_RUNNER_TIMEOUT_SECONDS",
    )
    terminal_idle_timeout_seconds: int = Field(
        default=300,
        ge=60,
        le=7200,
        validation_alias="TERMINAL_IDLE_TIMEOUT_SECONDS",
    )
    terminal_max_duration_seconds: int = Field(
        default=3600,
        ge=120,
        le=14400,
        validation_alias="TERMINAL_MAX_DURATION_SECONDS",
    )
    terminal_max_sessions_per_user: int = Field(
        default=3,
        ge=1,
        le=20,
        validation_alias="TERMINAL_MAX_SESSIONS_PER_USER",
    )
    # --- Step 53B: project quotas (generous defaults for local dev) ---
    quota_max_active_deployments_per_project: int = Field(
        default=20,
        ge=1,
        le=500,
        validation_alias="CNS_QUOTA_MAX_ACTIVE_DEPLOYMENTS_PER_PROJECT",
    )
    quota_max_nodes_per_topology: int = Field(
        default=50,
        ge=1,
        le=500,
        validation_alias="CNS_QUOTA_MAX_NODES_PER_TOPOLOGY",
    )
    quota_max_services_per_deployment: int = Field(
        default=30,
        ge=1,
        le=500,
        validation_alias="CNS_QUOTA_MAX_SERVICES_PER_DEPLOYMENT",
    )
    quota_max_api_tokens_per_user: int = Field(
        default=25,
        ge=1,
        le=200,
        validation_alias="CNS_QUOTA_MAX_API_TOKENS_PER_USER",
    )
    # Optional deployment TTL (hours); 0 = disabled.
    deployment_ttl_hours: int = Field(
        default=0,
        ge=0,
        le=8760,
        validation_alias="CNS_DEPLOYMENT_TTL_HOURS",
    )
    # --- Step 53B: per-user/IP rate limits (requests per window) ---
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        validation_alias="CNS_RATE_LIMIT_WINDOW_SECONDS",
    )
    rate_limit_auth_per_ip: int = Field(
        default=30,
        ge=5,
        le=500,
        validation_alias="CNS_RATE_LIMIT_AUTH_PER_IP",
    )
    rate_limit_deploy_per_user: int = Field(
        default=20,
        ge=1,
        le=500,
        validation_alias="CNS_RATE_LIMIT_DEPLOY_PER_USER",
    )
    rate_limit_expose_per_user: int = Field(
        default=30,
        ge=1,
        le=500,
        validation_alias="CNS_RATE_LIMIT_EXPOSE_PER_USER",
    )
    rate_limit_terminal_per_user: int = Field(
        default=20,
        ge=1,
        le=500,
        validation_alias="CNS_RATE_LIMIT_TERMINAL_PER_USER",
    )
    rate_limit_exec_per_user: int = Field(
        default=60,
        ge=1,
        le=1000,
        validation_alias="CNS_RATE_LIMIT_EXEC_PER_USER",
    )
    rate_limit_download_per_user: int = Field(
        default=60,
        ge=1,
        le=1000,
        validation_alias="CNS_RATE_LIMIT_DOWNLOAD_PER_USER",
    )
    # --- Step 54A: email / notifications ---
    email_provider: str = Field(
        default="console",
        validation_alias="EMAIL_PROVIDER",
        description="console | smtp | disabled",
    )
    smtp_host: str = Field(default="localhost", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, ge=1, le=65535, validation_alias="SMTP_PORT")
    smtp_username: str = Field(default="", validation_alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", validation_alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="cns@localhost", validation_alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, validation_alias="SMTP_USE_TLS")


settings = Settings()
