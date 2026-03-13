"""
Claude Engine Wrapper - Provides compatibility layer for ResearcherEngine
"""

import logging
from typing import Union, Generator
from core.claude_engine import ClaudeAFLEngine

logger = logging.getLogger(__name__)


class ClaudeEngineWrapper:
    """Wrapper to provide compatibility between ClaudeAFLEngine and ResearcherEngine"""
    
    def __init__(self, api_key: str = None, model: str = None):
        """Initialize the wrapper with ClaudeAFLEngine"""
        self.claude = ClaudeAFLEngine(api_key=api_key, model=model)
    
    def generate_response(self, prompt: str, stream: bool = False) -> Union[str, Generator[str, None, None]]:
        """
        Generate response using ClaudeAFLEngine.chat method.
        This provides compatibility for ResearcherEngine.
        
        Args:
            prompt: The prompt to send to Claude
            stream: Whether to return a streaming generator
            
        Returns:
            String response or generator for streaming
        """
        try:
            if stream:
                return self.claude.chat(message=prompt, stream=True)
            else:
                response = self.claude.chat(message=prompt)
                return response
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            if stream:
                yield f"Unable to generate response: {str(e)}"
            else:
                return f"Unable to generate response: {str(e)}"
    
    def __getattr__(self, name):
        """Delegate any other method calls to the underlying ClaudeAFLEngine"""
        return getattr(self.claude, name)
