"""Supabase client singleton."""

from supabase import create_client, Client
from functools import lru_cache
from config import get_settings
import logging

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """
    Get Supabase client instance (cached singleton).
    
    Uses service_role key if available (bypasses RLS for backend operations).
    Falls back to anon key if service_role key is not configured.
    """
    settings = get_settings()
    
    # Use service_role key if available (recommended for backend)
    if settings.supabase_service_key:
        logger.info("Using Supabase service_role key (bypasses RLS)")
        return create_client(settings.supabase_url, settings.supabase_service_key)
    else:
        logger.warning(
            "⚠️ SUPABASE_SERVICE_KEY is not set! Using anon key. "
            "Backend operations will be limited by RLS policies. "
            "Get it from: Supabase Dashboard > Settings > API > service_role key"
        )
        return create_client(settings.supabase_url, settings.supabase_key)


def get_supabase_with_token(token: str) -> Client:
    """
    Get a Supabase client authenticated with a user's JWT token.
    
    This is used as a fallback when service_role key is not available.
    The client will have the permissions of the authenticated user
    (RLS policies based on auth.uid() will work).
    """
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_key)
    client.auth.set_session(token, "")  # Set the access token
    return client
