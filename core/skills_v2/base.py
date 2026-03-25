"""
Skill Definition
================
Data class representing a model-agnostic skill.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class SkillDefinition:
    """
    A model-agnostic skill definition.

    Skills are executed server-side using a sub-agent conversation
    with the same provider that initiated the parent request.
    """
    slug: str  # "potomac-docx-skill"
    name: str  # "Potomac DOCX Generator"
    description: str  # What the skill does
    category: str  # "document", "analysis", "code"
    system_prompt: str  # Skill-specific system prompt
    required_tools: List[str] = field(default_factory=list)
    output_type: str = "text"  # "text", "file", "chart", "structured"
    file_extensions: List[str] = field(default_factory=list)
    max_tokens: int = 8192
    timeout: int = 120  # seconds
    enabled: bool = True

    def to_tool_definition(self) -> Dict[str, Any]:
        """
        Generate a tool definition that any model can understand.
        This is what gets added to the tools list for the model.
        """
        return {
            "name": f"invoke_{self.slug.replace('-', '_')}",
            "description": (
                f"{self.description}\n\n"
                f"Use this when the user asks for: {self._get_trigger_description()}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": f"Detailed request for the {self.name} skill",
                    },
                    "context": {
                        "type": "string",
                        "description": "Additional context or data",
                    },
                },
                "required": ["message"],
            },
        }

    def _get_trigger_description(self) -> str:
        """Generate a description of when to use this skill."""
        triggers = {
            "document": "documents, reports, memos, letters, SOPs, research write-ups",
            "presentation": "presentations, slide decks, pitch decks, investor updates",
            "spreadsheet": "spreadsheets, excel files, data tables, trackers",
            "analysis": "quantitative analysis, financial modeling, factor analysis",
            "code": "code generation, AFL, AmiBroker strategies",
            "research": "deep research, company analysis, SEC filings",
        }
        return triggers.get(self.category, self.category)