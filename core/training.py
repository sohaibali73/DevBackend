"""
Training Module - Core training functionality for AI learning.
Allows admins to train the AI with examples, rules, and corrections.
"""

import logging
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import lru_cache

from db.supabase_client import get_supabase

# Configure logger level based on environment
log_level = os.getenv("LOG_LEVEL", "WARNING" if os.getenv("ENVIRONMENT") == "production" else "INFO")
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level.upper()))


class TrainingType(Enum):
    """Types of training data."""
    EXAMPLE = "example"           # Input/output example pairs
    RULE = "rule"                 # AFL rules and patterns
    CORRECTION = "correction"     # Corrections to previous outputs
    PATTERN = "pattern"           # Code patterns to follow
    ANTI_PATTERN = "anti_pattern" # Patterns to avoid
    TERMINOLOGY = "terminology"   # Domain-specific terminology


@dataclass
class TrainingExample:
    """A training example for the AI."""
    id: str
    training_type: TrainingType
    title: str
    input_prompt: str
    expected_output: str
    explanation: str
    category: str
    tags: List[str]
    priority: int  # 1-10, higher = more important
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: datetime


class TrainingManager:
    """Manages AI training data and retrieval."""

    def __init__(self):
        self.db = get_supabase()

    def add_training_example(
        self,
        training_type: str,
        title: str,
        input_prompt: str,
        expected_output: str,
        explanation: str = "",
        category: str = "general",
        tags: List[str] = None,
        priority: int = 5,
        created_by: str = None,
    ) -> Dict[str, Any]:
        """
        Add a new training example.

        Args:
            training_type: Type of training (example, rule, correction, etc.)
            title: Short descriptive title
            input_prompt: The input/prompt that triggers this training
            expected_output: The expected/correct output
            explanation: Why this is the correct approach
            category: Category for organization (afl, trading, general)
            tags: Tags for filtering
            priority: Priority level 1-10
            created_by: Admin user ID who created this

        Returns:
            Created training record
        """
        try:
            data = {
                "training_type": training_type,
                "title": title,
                "input_prompt": input_prompt,
                "expected_output": expected_output,
                "explanation": explanation,
                "category": category,
                "tags": tags or [],
                "priority": priority,
                "is_active": True,
                "created_by": created_by,
            }

            result = self.db.table("training_data").insert(data).execute()
            
            if result.data:
                if logger.isEnabledFor(logging.INFO):
                    logger.info(f"Added training example: {title}")
                return {"status": "success", "data": result.data[0]}
            else:
                return {"status": "error", "message": "Failed to insert training data"}

        except Exception as e:
            logger.error(f"Error adding training example: {e}")
            return {"status": "error", "message": str(e)}

    def update_training_example(
        self,
        training_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update an existing training example."""
        try:
            updates["updated_at"] = datetime.utcnow().isoformat()
            
            result = self.db.table("training_data").update(updates).eq("id", training_id).execute()
            
            if result.data:
                return {"status": "success", "data": result.data[0]}
            else:
                return {"status": "error", "message": "Training example not found"}

        except Exception as e:
            logger.error(f"Error updating training example: {e}")
            return {"status": "error", "message": str(e)}

    def delete_training_example(self, training_id: str) -> Dict[str, Any]:
        """Delete a training example."""
        try:
            self.db.table("training_data").delete().eq("id", training_id).execute()
            return {"status": "success", "message": "Training example deleted"}

        except Exception as e:
            logger.error(f"Error deleting training example: {e}")
            return {"status": "error", "message": str(e)}

    def get_training_example(self, training_id: str) -> Optional[Dict[str, Any]]:
        """Get a single training example by ID."""
        try:
            result = self.db.table("training_data").select("*").eq("id", training_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting training example: {e}")
            return None

    def list_training_examples(
        self,
        training_type: Optional[str] = None,
        category: Optional[str] = None,
        is_active: bool = True,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List training examples with optional filtering."""
        try:
            query = self.db.table("training_data").select("*")
            
            if training_type:
                query = query.eq("training_type", training_type)
            if category:
                query = query.eq("category", category)
            if is_active is not None:
                query = query.eq("is_active", is_active)
            
            result = query.order("priority", desc=True).order("created_at", desc=True).limit(limit).execute()
            return result.data or []

        except Exception as e:
            logger.error(f"Error listing training examples: {e}")
            return []

    def get_training_context(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
    ) -> str:
        """
        Get formatted training context for injection into prompts.

        This method retrieves relevant training data and formats it
        for inclusion in Claude's system prompt.

        Args:
            category: Filter by category
            tags: Filter by tags
            limit: Maximum number of examples to include

        Returns:
            Formatted training context string
        """
        try:
            query = self.db.table("training_data").select("*").eq("is_active", True)
            
            if category:
                query = query.eq("category", category)
            
            result = query.order("priority", desc=True).order("training_type").limit(limit).execute()
            
            if not result.data:
                return ""

            # Group by type
            examples = []
            rules = []
            patterns = []
            anti_patterns = []
            corrections = []
            terminology = []

            for item in result.data:
                t_type = item.get("training_type", "example")
                
                if t_type == "example":
                    examples.append(item)
                elif t_type == "rule":
                    rules.append(item)
                elif t_type == "pattern":
                    patterns.append(item)
                elif t_type == "anti_pattern":
                    anti_patterns.append(item)
                elif t_type == "correction":
                    corrections.append(item)
                elif t_type == "terminology":
                    terminology.append(item)

            # Build context string
            context_parts = []

            if rules:
                context_parts.append("## LEARNED RULES (Must Follow)")
                for rule in rules:
                    context_parts.append(f"\n### {rule['title']}")
                    context_parts.append(f"Rule: {rule['expected_output']}")
                    if rule.get('explanation'):
                        context_parts.append(f"Reason: {rule['explanation']}")

            if patterns:
                context_parts.append("\n## CODE PATTERNS (Preferred Approaches)")
                for pattern in patterns:
                    context_parts.append(f"\n### {pattern['title']}")
                    if pattern.get('input_prompt'):
                        context_parts.append(f"When: {pattern['input_prompt']}")
                    context_parts.append(f"Use:\n```afl\n{pattern['expected_output']}\n```")

            if anti_patterns:
                context_parts.append("\n## ANTI-PATTERNS (Avoid These)")
                for ap in anti_patterns:
                    context_parts.append(f"\n### ❌ {ap['title']}")
                    context_parts.append(f"Don't do: {ap['input_prompt']}")
                    if ap.get('expected_output'):
                        context_parts.append(f"Instead do: {ap['expected_output']}")

            if examples:
                context_parts.append("\n## TRAINING EXAMPLES (Follow These Patterns)")
                for ex in examples[:5]:  # Limit examples to avoid context overflow
                    context_parts.append(f"\n### Example: {ex['title']}")
                    context_parts.append(f"Input: {ex['input_prompt']}")
                    context_parts.append(f"Expected Output:\n```afl\n{ex['expected_output']}\n```")
                    if ex.get('explanation'):
                        context_parts.append(f"Why: {ex['explanation']}")

            if corrections:
                context_parts.append("\n## LEARNED CORRECTIONS (Important Fixes)")
                for corr in corrections:
                    context_parts.append(f"\n### Correction: {corr['title']}")
                    context_parts.append(f"Wrong: {corr['input_prompt']}")
                    context_parts.append(f"Correct: {corr['expected_output']}")

            if terminology:
                context_parts.append("\n## DOMAIN TERMINOLOGY")
                for term in terminology:
                    context_parts.append(f"- **{term['title']}**: {term['expected_output']}")

            return "\n".join(context_parts)

        except Exception as e:
            logger.error(f"Error getting training context: {e}")
            return ""

    def get_training_stats(self) -> Dict[str, Any]:
        """Get statistics about training data."""
        try:
            total = self.db.table("training_data").select("id", count="exact").execute()
            active = self.db.table("training_data").select("id", count="exact").eq("is_active", True).execute()
            
            # Get breakdown by type
            all_data = self.db.table("training_data").select("training_type, category").execute()
            
            type_counts = {}
            category_counts = {}
            
            for item in all_data.data or []:
                t_type = item.get("training_type", "unknown")
                category = item.get("category", "unknown")
                
                type_counts[t_type] = type_counts.get(t_type, 0) + 1
                category_counts[category] = category_counts.get(category, 0) + 1

            return {
                "total": total.count or 0,
                "active": active.count or 0,
                "by_type": type_counts,
                "by_category": category_counts,
            }

        except Exception as e:
            logger.error(f"Error getting training stats: {e}")
            return {"total": 0, "active": 0, "by_type": {}, "by_category": {}}

    def add_correction_from_feedback(
        self,
        original_prompt: str,
        wrong_output: str,
        correct_output: str,
        feedback: str,
        created_by: str = None,
    ) -> Dict[str, Any]:
        """
        Add a correction based on user feedback.

        This is used when the AI generates wrong code and the admin
        provides the correct version.
        """
        return self.add_training_example(
            training_type="correction",
            title=f"Correction: {feedback[:50]}...",
            input_prompt=f"Original prompt: {original_prompt}\nWrong output: {wrong_output}",
            expected_output=correct_output,
            explanation=feedback,
            category="afl",
            priority=8,  # Corrections are high priority
            created_by=created_by,
        )

    def import_training_batch(
        self,
        training_items: List[Dict[str, Any]],
        created_by: str = None,
    ) -> Dict[str, Any]:
        """
        Import multiple training items at once.

        Args:
            training_items: List of training item dictionaries
            created_by: Admin user ID

        Returns:
            Import results
        """
        results = {
            "total": len(training_items),
            "successful": 0,
            "failed": 0,
            "errors": [],
        }

        for item in training_items:
            try:
                item["created_by"] = created_by
                item["is_active"] = item.get("is_active", True)
                
                self.db.table("training_data").insert(item).execute()
                results["successful"] += 1

            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"{item.get('title', 'Unknown')}: {str(e)}")

        return results

    def export_training_data(
        self,
        training_type: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Export training data for backup or transfer."""
        return self.list_training_examples(
            training_type=training_type,
            category=category,
            is_active=None,  # Include all
            limit=1000,
        )


# Singleton instance


@lru_cache(maxsize=1)
def get_training_manager() -> TrainingManager:
    """Get the training manager singleton (thread-safe cached)."""
    return TrainingManager()