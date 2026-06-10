"""Application configuration."""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # ── Database (Azure Database for PostgreSQL — Flexible Server) ──────────────
    # Primary connection string used by BOTH the asyncpg hot-path pool and the
    # synchronous PostgREST-compatible shim in db/supabase_client.py.
    #   postgresql://user:pass@host.postgres.database.azure.com:5432/dbname?sslmode=require
    database_url: str = ""
    async_db_pool_min: int = 2
    async_db_pool_max: int = 20

    # ── Legacy Supabase fields (DEPRECATED) ────────────────────────────────────
    # Kept only so older scripts/imports don't crash. No longer used by the app
    # at runtime. `supabase_db_url` still works as a fallback for `database_url`.
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_db_url: str = ""

    # ── Azure Blob Storage (replaces Supabase Storage buckets) ─────────────────
    # Prefer Managed Identity in Azure (set account name only); fall back to a
    # connection string for local/dev.
    azure_storage_account: str = ""                  # e.g. "pfmaiappsdev" (just the name)
    azure_storage_connection_string: str = ""        # full conn string (local/dev)
    azure_storage_use_managed_identity: bool = True  # use MI when running in Azure

    # Redis cache (OPTIONAL — core/cache.py falls back to in-process LRU when empty)
    redis_url: str = ""
    enable_redis_cache: bool = True
    enable_prompt_cache: bool = True

    # HTTP / worker pool sizing
    llm_http_pool_size: int = 50
    node_worker_pool_size: int = 4


    # Data Encryption at Rest - MUST be set via environment variable
    # Generate a secure 32-byte key: python -c "import secrets; print(secrets.token_urlsafe(32))"
    encryption_key: str = ""  # Used for encrypting sensitive data like API keys
    
    # Admin configuration (comma-separated list of admin emails)
    admin_emails: str = ""

    # ── Authentication (self-hosted JWT) ───────────────────────────────────────
    # The backend now issues AND verifies its own HS256 JWTs. SECRET_KEY MUST be
    # set to a strong random value in production (tokens are signed with it).
    #   python -c "import secrets; print(secrets.token_urlsafe(48))"
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    jwt_issuer: str = "potomac-backend"
    jwt_audience: str = "authenticated"
    access_token_expire_minutes: int = 60 * 24 * 7          # 7 days
    refresh_token_expire_minutes: int = 60 * 24 * 30        # 30 days

    # Optional server-side API keys - set via environment variables
    anthropic_api_key: str = ""
    tavily_api_key: str = ""

    # Multi-provider LLM API keys (server-side fallbacks)
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    vercel_gateway_api_key: str = ""

    # Default AI model
    default_ai_model: str = "claude-sonnet-4-20250514"
    
    # Researcher tool API keys
    finnhub_api_key: str = ""
    fred_api_key: str = ""
    newsapi_key: str = ""

    # SMTP settings for password reset emails
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_sender_email: str = ""
    smtp_password: str = ""
    
    # Frontend URL for password reset links
    frontend_url: str = "https://potomacdeveloper.vercel.app"

    # Storage settings
    max_upload_size_mb: int = 10240  # 10 GB (no practical limit)
    allowed_upload_types: str = "pdf,txt,csv,json,pptx,xlsx,png,jpg,jpeg,gif,webp"

    # Feature flags
    enable_brain_documents: bool = True
    enable_afl_generation: bool = True
    enable_presentations: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def effective_db_url(self) -> str:
        """Postgres DSN — prefers DATABASE_URL, falls back to the legacy
        SUPABASE_DB_URL so existing local .env files keep working."""
        return self.database_url or self.supabase_db_url

    def get_admin_emails(self) -> list:
        """Get list of admin emails from comma-separated string."""
        if not self.admin_emails:
            return []
        return [email.strip().lower() for email in self.admin_emails.split(",") if email.strip()]
    
    def get_allowed_upload_types(self) -> list:
        """Get list of allowed upload file types."""
        return [t.strip().lower() for t in self.allowed_upload_types.split(",") if t.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()