-- ============================================================================
-- Migration 017: Multi-Provider LLM API Keys
-- ============================================================================
-- Adds columns for OpenAI, OpenRouter, and Vercel Gateway API keys,
-- plus user preferences for provider and model selection.
--
-- Safe to run multiple times (uses IF NOT EXISTS).
-- ============================================================================

-- Add encrypted API key columns for additional providers
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS openai_api_key_encrypted TEXT,
  ADD COLUMN IF NOT EXISTS openrouter_api_key_encrypted TEXT,
  ADD COLUMN IF NOT EXISTS preferred_provider TEXT DEFAULT 'anthropic',
  ADD COLUMN IF NOT EXISTS preferred_model TEXT DEFAULT 'claude-sonnet-4-20250514';

-- Add comment for documentation
COMMENT ON COLUMN user_profiles.openai_api_key_encrypted IS 'AES-256 encrypted OpenAI API key (user-provided)';
COMMENT ON COLUMN user_profiles.openrouter_api_key_encrypted IS 'AES-256 encrypted OpenRouter API key (user-provided)';
COMMENT ON COLUMN user_profiles.preferred_provider IS 'User preferred LLM provider: anthropic, openai, openrouter, vercel_gateway';
COMMENT ON COLUMN user_profiles.preferred_model IS 'User preferred model ID (e.g. claude-sonnet-4-6, gpt-4o, meta-llama/llama-3.1-70b)';