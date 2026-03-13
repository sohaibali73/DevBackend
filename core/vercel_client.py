"""
Vercel AI Gateway Client
Initialize Anthropic client pointed to Vercel Gateway
"""

import os
import logging
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Singleton client instance
_client = None


def get_vercel_client() -> Anthropic:
    """
    Get Vercel-routed Anthropic client (singleton).
    
    Uses environment variables:
    - ANTHROPIC_API_KEY: Your Anthropic API key
    - VERCEL_AI_GATEWAY_URL: Optional Vercel gateway URL (defaults to api.anthropic.com)
    
    Returns:
        Anthropic client instance
        
    Raises:
        ValueError: If API key not configured
    """
    global _client
    
    if _client is not None:
        return _client
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    
    gateway_url = os.getenv("VERCEL_AI_GATEWAY_URL", "https://api.anthropic.com")
    
    _client = Anthropic(
        api_key=api_key,
        base_url=gateway_url
    )
    
    logger.info(f"Initialized Anthropic client with gateway: {gateway_url}")
    return _client


def get_model() -> str:
    """Get configured model name"""
    return os.getenv("MODEL", "claude-3-5-sonnet-latest")


def reset_client():
    """Reset client (for testing)"""
    global _client
    _client = None