"""Application configuration."""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Supabase - MUST be set via environment variables
    supabase_url: str = ""
    supabase_key: str = ""  # anon/public key
    supabase_service_key: str = ""  # service_role key (required for backend operations with RLS)

    # Data Encryption at Rest - MUST be set via environment variable
    # Generate a secure 32-byte key: python -c "import secrets; print(secrets.token_urlsafe(32))"
    encryption_key: str = ""  # Used for encrypting sensitive data like API keys
    
    # Admin configuration (comma-separated list of admin emails)
    admin_emails: str = ""

    # Security - Note: These are DEPRECATED - Supabase Auth handles JWT tokens
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 600 * 24 * 7

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