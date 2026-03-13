"""
Train Routes - AI Training and Feedback System
Separate from admin, these routes handle training interaction, testing, and feedback.
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pydantic import Field
from datetime import datetime

from api.dependencies import get_current_user_id, get_user_api_keys
from db.supabase_client import get_supabase
from config import get_settings
from core.training import get_training_manager
from core.claude_engine import ClaudeAFLEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/train", tags=["Training"])


# =============================================================================
# Helper Functions
# =============================================================================



# =============================================================================
# Pydantic Models
# =============================================================================

class FeedbackSubmit(BaseModel):
    """User feedback on AI-generated code."""
    code_id: Optional[str] = Field(None, description="ID of the generated code")
    conversation_id: Optional[str] = Field(None, description="ID of the conversation")
    original_prompt: str = Field(..., min_length=5, max_length=1000, description="Original user prompt")
    generated_code: str = Field(..., min_length=10, max_length=5000, description="Generated AFL code")
    feedback_type: str = Field(..., description="Type of feedback: correction, improvement, bug, praise")
    feedback_text: str = Field(..., min_length=10, max_length=1000, description="Detailed feedback text")
    correct_code: Optional[str] = Field(None, max_length=5000, description="Corrected code if applicable")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating 1-5")


class TestTrainingRequest(BaseModel):
    """Test how training affects AI output."""
    prompt: str
    category: Optional[str] = "afl"
    include_training: bool = True


class TrainingSuggestion(BaseModel):
    """Suggest a training example."""
    title: str
    description: str
    example_input: Optional[str] = ""
    example_output: Optional[str] = ""
    reason: str


# =============================================================================
# Feedback Collection Routes
# =============================================================================

@router.post("/feedback")
async def submit_feedback(
    data: FeedbackSubmit,
    user_id: str = Depends(get_current_user_id),
):
    """
    Submit feedback on AI-generated code.
    
    This helps improve the AI by learning from mistakes and user corrections.
    Feedback can automatically create training data for admins to review.
    """
    db = get_supabase()
    
    try:
        # Save feedback
        feedback_result = db.table("user_feedback").insert({
            "user_id": user_id,
            "code_id": data.code_id,
            "conversation_id": data.conversation_id,
            "original_prompt": data.original_prompt,
            "generated_code": data.generated_code,
            "feedback_type": data.feedback_type,
            "feedback_text": data.feedback_text,
            "correct_code": data.correct_code,
            "rating": data.rating,
            "status": "pending_review",
        }).execute()
        
        feedback_id = feedback_result.data[0]["id"]
        
        # If it's a correction with correct code, create a pending training suggestion
        if data.feedback_type == "correction" and data.correct_code:
            db.table("training_suggestions").insert({
                "user_id": user_id,
                "feedback_id": feedback_id,
                "title": f"Correction: {data.original_prompt[:50]}...",
                "training_type": "correction",
                "input_prompt": f"User prompt: {data.original_prompt}\nWrong output: {data.generated_code}",
                "expected_output": data.correct_code,
                "explanation": data.feedback_text,
                "category": "afl",
                "status": "pending",
            }).execute()
        
        return {
            "status": "success",
            "feedback_id": feedback_id,
            "message": "Thank you for your feedback! This will help improve the AI.",
        }
        
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/my")
async def get_my_feedback(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    """Get user's submitted feedback history."""
    db = get_supabase()
    
    result = db.table("user_feedback").select(
        "id, original_prompt, feedback_type, feedback_text, rating, status, created_at"
    ).eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
    
    return {"count": len(result.data), "feedback": result.data}


@router.get("/feedback/{feedback_id}")
async def get_feedback_detail(
    feedback_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get detailed feedback information."""
    db = get_supabase()
    
    result = db.table("user_feedback").select("*").eq("id", feedback_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    feedback = result.data[0]
    
    # Check ownership
    if feedback["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return feedback


# =============================================================================
# Training Testing Routes
# =============================================================================

@router.post("/test")
async def test_training(
    data: TestTrainingRequest,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """
    Test how training affects AI code generation.
    
    Generates code with and without training context to show the difference.
    Useful for admins to verify training is working.
    """
    if not api_keys.get("claude"):
        raise HTTPException(
            status_code=400, 
            detail="Claude API key not configured. Please add your API key in Profile Settings."
        )
    
    try:
        engine = ClaudeAFLEngine(api_key=api_keys["claude"])
        training_manager = get_training_manager()
        
        # Generate WITHOUT training
        result_without = engine.generate_afl(
            request=data.prompt,
            include_training=False,
        )
        
        # Generate WITH training
        result_with = engine.generate_afl(
            request=data.prompt,
            include_training=data.include_training,
        )
        
        # Get training context used
        training_context = ""
        if data.include_training:
            training_context = training_manager.get_training_context(category=data.category)
        
        return {
            "prompt": data.prompt,
            "without_training": {
                "code": result_without.get("afl_code", ""),
                "explanation": result_without.get("explanation", ""),
            },
            "with_training": {
                "code": result_with.get("afl_code", ""),
                "explanation": result_with.get("explanation", ""),
            },
            "training_context_used": training_context[:500] + "..." if len(training_context) > 500 else training_context,
            "differences_detected": result_without.get("afl_code") != result_with.get("afl_code"),
        }
        
    except Exception as e:
        logger.error(f"Error testing training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/effectiveness")
async def get_training_effectiveness(
    category: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get training effectiveness metrics.
    
    Shows how training improves code quality over time.
    """
    db = get_supabase()
    
    try:
        # Get feedback stats
        feedback_stats = db.table("user_feedback").select(
            "feedback_type, rating", count="exact"
        ).execute()
        
        # Calculate average ratings
        ratings = [f.get("rating") for f in feedback_stats.data if f.get("rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        
        # Get correction rate (lower is better - means less corrections needed)
        corrections = len([f for f in feedback_stats.data if f.get("feedback_type") == "correction"])
        total_feedback = len(feedback_stats.data)
        correction_rate = (corrections / total_feedback * 100) if total_feedback > 0 else 0
        
        # Get training data stats
        training_manager = get_training_manager()
        training_stats = training_manager.get_training_stats()
        
        return {
            "average_rating": round(avg_rating, 2),
            "total_feedback": total_feedback,
            "correction_rate": round(correction_rate, 2),
            "corrections_count": corrections,
            "training_examples": training_stats.get("total", 0),
            "active_training": training_stats.get("active", 0),
            "training_by_type": training_stats.get("by_type", {}),
        }
        
    except Exception as e:
        logger.error(f"Error getting training effectiveness: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Training Suggestions Routes
# =============================================================================

@router.post("/suggest")
async def suggest_training(
    data: TrainingSuggestion,
    user_id: str = Depends(get_current_user_id),
):
    """
    Suggest a training example for admins to review.
    
    Users can contribute to training by suggesting patterns, rules, or examples
    they've discovered. Admins review and approve these.
    """
    db = get_supabase()
    
    try:
        result = db.table("training_suggestions").insert({
            "user_id": user_id,
            "title": data.title,
            "training_type": "suggestion",
            "input_prompt": data.example_input or data.description,
            "expected_output": data.example_output,
            "explanation": f"{data.description}\n\nReason: {data.reason}",
            "category": "afl",
            "status": "pending",
        }).execute()
        
        return {
            "status": "success",
            "suggestion_id": result.data[0]["id"],
            "message": "Thank you for your suggestion! An admin will review it soon.",
        }
        
    except Exception as e:
        logger.error(f"Error submitting suggestion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions/my")
async def get_my_suggestions(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
):
    """Get user's training suggestions and their status."""
    db = get_supabase()
    
    result = db.table("training_suggestions").select(
        "id, title, status, created_at, reviewed_at, admin_notes"
    ).eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
    
    return {"count": len(result.data), "suggestions": result.data}


# =============================================================================
# Learning Analytics Routes
# =============================================================================

@router.get("/analytics/learning-curve")
async def get_learning_curve(
    days: int = 30,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get user's learning curve - how code quality improves over time.
    
    Tracks ratings, corrections, and code complexity over time.
    """
    db = get_supabase()
    
    try:
        # Get user's codes over time with quality scores
        codes = db.table("afl_codes").select(
            "created_at, quality_score, name"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(100).execute()
        
        # Get feedback over time
        feedback = db.table("user_feedback").select(
            "created_at, rating, feedback_type"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(100).execute()
        
        # Calculate trends
        quality_scores = [c.get("quality_score", 0) for c in codes.data if c.get("quality_score")]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        ratings = [f.get("rating") for f in feedback.data if f.get("rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        
        return {
            "total_codes_generated": len(codes.data),
            "average_quality_score": round(avg_quality, 2),
            "average_user_rating": round(avg_rating, 2),
            "recent_codes": codes.data[:10],
            "recent_feedback": feedback.data[:10],
            "trend": "improving" if avg_quality > 70 else "needs_work",
        }
        
    except Exception as e:
        logger.error(f"Error getting learning curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/popular-patterns")
async def get_popular_patterns(
    limit: int = 10,
    user_id: str = Depends(get_current_user_id),
):
    """
    Get most popular training patterns and rules.
    
    Shows which training examples are most frequently used.
    """
    training_manager = get_training_manager()
    
    # Get all training examples
    examples = training_manager.list_training_examples(
        is_active=True,
        limit=100,
    )
    
    # Sort by priority and usage
    popular = sorted(examples, key=lambda x: x.get("priority", 0), reverse=True)[:limit]
    
    return {
        "popular_patterns": popular,
        "count": len(popular),
    }


# =============================================================================
# Training Knowledge Base Routes
# =============================================================================

@router.get("/knowledge/search")
async def search_training_knowledge(
    query: str,
    category: Optional[str] = None,
    limit: int = 10,
    user_id: str = Depends(get_current_user_id),
):
    """
    Search training knowledge base.
    
    Find relevant training examples, rules, and patterns by keyword.
    """
    training_manager = get_training_manager()
    
    # Get all training examples matching category
    examples = training_manager.list_training_examples(
        category=category,
        is_active=True,
        limit=100,
    )
    
    # Simple keyword search
    query_lower = query.lower()
    matches = []
    
    for example in examples:
        score = 0
        if query_lower in example.get("title", "").lower():
            score += 3
        if query_lower in example.get("input_prompt", "").lower():
            score += 2
        if query_lower in example.get("expected_output", "").lower():
            score += 1
        if query_lower in example.get("explanation", "").lower():
            score += 1
        
        if score > 0:
            matches.append({**example, "relevance_score": score})
    
    # Sort by relevance
    matches.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    
    return {
        "query": query,
        "matches": matches[:limit],
        "total_matches": len(matches),
    }


@router.get("/knowledge/categories")
async def get_training_categories(
    user_id: str = Depends(get_current_user_id),
):
    """Get all available training categories with counts."""
    training_manager = get_training_manager()
    stats = training_manager.get_training_stats()
    
    return {
        "categories": stats.get("by_category", {}),
        "total": stats.get("total", 0),
    }


@router.get("/knowledge/types")
async def get_training_types(
    user_id: str = Depends(get_current_user_id),
):
    """Get all training types with counts and descriptions."""
    training_manager = get_training_manager()
    stats = training_manager.get_training_stats()
    
    type_descriptions = {
        "example": "Input/output example pairs showing how to solve specific problems",
        "rule": "Mandatory rules the AI must always follow",
        "pattern": "Recommended code patterns and best practices",
        "anti_pattern": "Patterns to avoid and why they're problematic",
        "correction": "Corrections to previous AI mistakes",
        "terminology": "Domain-specific terms and their definitions",
    }
    
    types_with_info = []
    for t_type, count in stats.get("by_type", {}).items():
        types_with_info.append({
            "type": t_type,
            "count": count,
            "description": type_descriptions.get(t_type, ""),
        })
    
    return {
        "training_types": types_with_info,
        "total": stats.get("total", 0),
    }


# =============================================================================
# Quick Learning Routes
# =============================================================================

@router.post("/quick-learn")
async def quick_learn_from_example(
    code: str,
    explanation: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Quick learn from an example.
    
    Users can flag good code examples they want the AI to learn from.
    Creates a suggestion for admin review.
    """
    db = get_supabase()
    
    try:
        result = db.table("training_suggestions").insert({
            "user_id": user_id,
            "title": f"User example: {explanation[:50]}...",
            "training_type": "example",
            "input_prompt": f"Generate code that: {explanation}",
            "expected_output": code,
            "explanation": f"User-provided example: {explanation}",
            "category": "afl",
            "status": "pending",
        }).execute()
        
        return {
            "status": "success",
            "suggestion_id": result.data[0]["id"],
            "message": "Example submitted for AI learning. An admin will review it.",
        }
        
    except Exception as e:
        logger.error(f"Error in quick learn: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_training_stats(
    user_id: str = Depends(get_current_user_id),
):
    """Get comprehensive training statistics."""
    training_manager = get_training_manager()
    
    return training_manager.get_training_stats()