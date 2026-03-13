"""
Context Manager - Optimize context window usage for Claude API calls.
Prevents context overload and enables faster responses.
"""

import logging
from typing import List, Dict, Any, Optional
from functools import lru_cache
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Configuration - OPTIMIZED FOR PERFORMANCE
MAX_RECENT_MESSAGES = 10  # Reduced from 100 for faster responses
MAX_TRAINING_EXAMPLES = 3  # Reduced from 5 for performance
MAX_CONTEXT_TOKENS = 4000  # Reduced from 8000 for faster processing

# Condensed context limits for performance optimization
CONDENSED_CONTEXT_LIMITS = {
    "system_prompt_max_tokens": 500,  # Reduced from ~2000
    "training_context_max_tokens": 800,  # Reduced from 2000
    "kb_context_max_tokens": 600,  # Reduced from 1500
    "research_context_max_tokens": 1000,  # Reduced from 2000
    "total_context_budget": 5000,  # Reduced from 8000
}


@lru_cache(maxsize=100)
def get_recent_messages(
    conversation_id: str,
    limit: int = MAX_RECENT_MESSAGES,
    include_system: bool = False
) -> List[Dict[str, str]]:
    """
    Get recent messages from a conversation with limit.
    Cached to avoid repeated database queries.
    
    Args:
        conversation_id: The conversation ID
        limit: Maximum number of messages to retrieve
        include_system: Whether to include system messages
        
    Returns:
        List of message dictionaries with role and content
    """
    try:
        db = get_supabase()
        
        # Build query efficiently - filter at database level
        query = db.table("messages").select("role, content").eq(
            "conversation_id", conversation_id
        ).order("created_at", desc=True).limit(limit)
        
        # If not including system messages, filter at DB level for efficiency
        if not include_system:
            query = query.neq("role", "system")
        
        result = query.execute()
        
        # Reverse to get chronological order (oldest to newest)
        messages = [{"role": m["role"], "content": m["content"]} for m in reversed(result.data)]
        
        logger.debug(f"Retrieved {len(messages)} recent messages (limit: {limit}, include_system: {include_system})")
        return messages
        
    except Exception as e:
        logger.error(f"Error getting recent messages: {e}")
        return []


def estimate_tokens(text: str) -> int:
    """
    Improved token estimation using word count.
    English text averages ~1.3 tokens per word.
    
    Args:
        text: Text to estimate
        
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    
    # Count words (more accurate than char count)
    word_count = len(text.split())
    
    # English text: ~1.3 tokens per word
    # Code/technical: ~1.5 tokens per word
    # Use 1.4 as a balanced average
    estimated = int(word_count * 1.4)
    
    # Fallback to char-based if text is very short or has no spaces
    if word_count < 3:
        estimated = len(text) // 3  # Slightly more accurate than //4
    
    return max(estimated, 1)  # Always return at least 1 token


def truncate_context(
    context: str,
    max_tokens: int = 2000,
    preserve_start: bool = True
) -> str:
    """
    Truncate context to fit within token budget.
    
    Args:
        context: Context string to truncate
        max_tokens: Maximum tokens allowed
        preserve_start: If True, keep start; if False, keep end
        
    Returns:
        Truncated context
    """
    estimated_tokens = estimate_tokens(context)
    
    if estimated_tokens <= max_tokens:
        return context
    
    # Calculate character limit (max_tokens * 4 chars per token)
    char_limit = max_tokens * 4
    
    if preserve_start:
        truncated = context[:char_limit] + "\n\n[... context truncated for brevity ...]"
    else:
        truncated = "[... earlier context truncated ...]\n\n" + context[-char_limit:]
    
    logger.debug(f"Truncated context from ~{estimated_tokens} to ~{max_tokens} tokens")
    return truncated


def truncate_contexts_batch(
        contexts: Dict[str, tuple[str, int]]
) -> Dict[str, str]:
    """
    Efficiently truncate multiple contexts in a single pass.

    Args:
        contexts: Dictionary mapping context name to (content, max_tokens) tuple

    Returns:
        Dictionary of truncated contexts

    Example:
        >>> truncate_contexts_batch({
        ...     "training": ("long training text...", 800),
        ...     "kb": ("long kb text...", 600),
        ...     "research": ("long research text...", 1000)
        ... })
    """
    truncated = {}

    for name, (content, max_tokens) in contexts.items():
        if not content:
            truncated[name] = ""
            continue

        estimated_tokens = estimate_tokens(content)

        if estimated_tokens <= max_tokens:
            truncated[name] = content
        else:
            char_limit = max_tokens * 4
            truncated[name] = content[:char_limit] + "\n\n[... truncated ...]"
            logger.debug(f"Truncated {name}: ~{estimated_tokens} → ~{max_tokens} tokens")

    return truncated

def optimize_training_context(
    training_context: str,
    max_examples: int = MAX_TRAINING_EXAMPLES
) -> str:
    """
    Optimize training context by limiting examples.
    
    Args:
        training_context: Full training context
        max_examples: Maximum examples to include
        
    Returns:
        Optimized training context
    """
    if not training_context:
        return ""
    
    # Simple optimization: truncate to reasonable size
    return truncate_context(training_context, max_tokens=2000, preserve_start=True)


def build_optimized_context(
    conversation_history: Optional[List[Dict]] = None,
    system_prompt: Optional[str] = None,
    kb_context: Optional[str] = None,
    training_context: Optional[str] = None,
    research_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build optimized context package with token budget management.
    Uses single-pass truncation for better performance.
    
    Args:
        conversation_history: List of conversation messages
        system_prompt: System prompt text
        kb_context: Knowledge base context
        training_context: Training examples context
        research_context: Research/web search context
        
    Returns:
        Dictionary with optimized context components and token estimates
    """
    optimized = {}
    total_tokens = 0
    
    # Define context parts with their max token limits
    context_parts = []
    
    # System prompt (required, no truncation)
    if system_prompt:
        context_parts.append(("system_prompt", system_prompt, None))
    
    # Conversation history (limit by message count)
    if conversation_history:
        recent_history = conversation_history[-MAX_RECENT_MESSAGES:]
        context_parts.append(("conversation_history", recent_history, None))
    
    # Training context (truncate to 2000 tokens)
    if training_context:
        context_parts.append(("training_context", training_context, 2000))
    
    # KB context (truncate to 1500 tokens)
    if kb_context:
        context_parts.append(("kb_context", kb_context, 1500))
    
    # Research context (truncate to 2000 tokens)
    if research_context:
        context_parts.append(("research_context", research_context, 2000))
    
    # Single-pass processing of all context parts
    for key, content, max_tokens in context_parts:
        if key == "conversation_history":
            # Special handling for conversation history (already limited)
            history_tokens = sum(estimate_tokens(m.get("content", "")) for m in content)
            optimized[key] = content
            total_tokens += history_tokens
            logger.debug(f"Conversation history: {len(content)} messages, ~{history_tokens} tokens")
        else:
            # Text content - apply truncation if limit specified
            if max_tokens and estimate_tokens(content) > max_tokens:
                content = truncate_context(content, max_tokens=max_tokens, preserve_start=True)
            
            content_tokens = estimate_tokens(content)
            optimized[key] = content
            total_tokens += content_tokens
            logger.debug(f"{key}: ~{content_tokens} tokens")
    
    optimized["total_estimated_tokens"] = total_tokens
    
    if total_tokens > MAX_CONTEXT_TOKENS:
        logger.warning(f"Total context (~{total_tokens} tokens) exceeds recommended limit ({MAX_CONTEXT_TOKENS})")
    else:
        logger.info(f"Optimized context: ~{total_tokens} tokens (within budget)")
    
    return optimized


def should_include_training_context(endpoint: str, request_type: str) -> bool:
    """
    Determine if training context should be included based on endpoint.
    
    Args:
        endpoint: The API endpoint being called
        request_type: Type of request (generate, debug, optimize, chat, etc.)
        
    Returns:
        True if training context should be included
    """
    # Only include training context for AFL generation tasks
    afl_tasks = ["generate", "debug", "optimize", "afl", "reverse_engineer"]
    
    return request_type.lower() in afl_tasks or "afl" in endpoint.lower()
def clear_message_cache():
    """
    Clear the cached messages.
    Call this when messages are added/updated to ensure fresh data.
    """
    get_recent_messages.cache_clear()
    logger.info("Message cache cleared")