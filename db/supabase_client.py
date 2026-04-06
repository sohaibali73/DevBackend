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

    IMPORTANT: supabase-py v2 can revert PostgREST/Storage Authorization headers
    back to the anon key when there is no active auth session (which is always the
    case for service-role-only backends).  We explicitly call
    ``client.postgrest.auth(service_key)`` after creation to pin the Authorization
    header so that all DB operations run as service_role (BYPASSRLS).
    """
    settings = get_settings()

    # Use service_role key if available (recommended for backend)
    if settings.supabase_service_key:
        client = create_client(settings.supabase_url, settings.supabase_service_key)
        # Pin PostgREST Authorization header to the service key.
        # supabase-py v2 can silently downgrade to anon key when no session exists.
        try:
            client.postgrest.auth(settings.supabase_service_key)
        except Exception as pin_err:
            logger.warning("Could not pin PostgREST auth header: %s", pin_err)
        logger.info("Using Supabase service_role key (bypasses RLS, PostgREST auth pinned)")
        return client
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
