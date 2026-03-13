"""
Admin Routes - Admin panel backend for AI training and management.

Updated to use Supabase Auth with user_profiles table.
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json

from api.dependencies import get_current_user_id, get_current_user
from db.supabase_client import get_supabase
from core.training import get_training_manager, TrainingType
from config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# =============================================================================
# Admin Authentication
# =============================================================================

def get_admin_emails() -> list:
    """
    Get list of admin emails from config and fallback defaults.
    
    Admin emails can be configured via:
    1. ADMIN_EMAILS environment variable (comma-separated)
    2. Fallback hardcoded list
    """
    settings = get_settings()
    config_emails = settings.get_admin_emails()
    
    # Fallback defaults if no config provided
    default_emails = [
        "sohaib.ali@potomac.com",
    ]
    
    # Combine and deduplicate
    all_emails = set(email.lower() for email in config_emails + default_emails)
    return list(all_emails)


async def verify_admin(user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """
    Verify that the current user is an admin.
    
    Checks:
    1. User exists in user_profiles
    2. User has is_admin flag set to True
    """
    user_id = user.get("id")
    is_admin = user.get("is_admin", False)
    email = user.get("email", "")
    
    # Check if user is admin by flag or by email
    admin_emails = get_admin_emails()
    
    if not is_admin and email.lower() not in admin_emails:
        raise HTTPException(
            status_code=403, 
            detail="Admin access required. Contact support to get admin privileges."
        )
    
    return user_id


# =============================================================================
# Pydantic Models
# =============================================================================

class TrainingExampleCreate(BaseModel):
    """Model for creating a training example."""
    training_type: str = Field(..., description="Type of training: example, rule, correction, pattern, anti_pattern, terminology")
    title: str = Field(..., min_length=5, max_length=200, description="Training example title")
    input_prompt: str = Field(..., min_length=10, max_length=1000, description="Input prompt that triggers this training")
    expected_output: str = Field(..., min_length=5, max_length=2000, description="Expected output")
    explanation: Optional[str] = Field(None, max_length=1000, description="Explanation of the training")
    category: Optional[str] = Field("afl", description="Category for organization")
    tags: Optional[List[str]] = Field(None, max_items=10, description="Tags for filtering")
    priority: Optional[int] = Field(5, ge=1, le=10, description="Priority level 1-10")


class TrainingExampleUpdate(BaseModel):
    """Model for updating a training example."""
    training_type: Optional[str] = None
    title: Optional[str] = None
    input_prompt: Optional[str] = None
    expected_output: Optional[str] = None
    explanation: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class CorrectionCreate(BaseModel):
    """Model for adding a correction from feedback."""
    original_prompt: str
    wrong_output: str
    correct_output: str
    feedback: str


class BatchImport(BaseModel):
    """Model for batch importing training data."""
    items: List[TrainingExampleCreate]


class QuickTrain(BaseModel):
    """Model for quick training - simplified input."""
    what_to_learn: str  # The rule or pattern to learn
    example_input: Optional[str] = ""
    example_output: Optional[str] = ""
    training_type: Optional[str] = "rule"


class UserUpdateRequest(BaseModel):
    """Model for updating user information."""
    name: Optional[str] = None
    email: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


class SystemConfigUpdate(BaseModel):
    """Model for updating system configuration."""
    admin_emails: Optional[List[str]] = None
    system_status: Optional[str] = None
    maintenance_mode: Optional[bool] = None


class AuditLogFilter(BaseModel):
    """Model for filtering audit logs."""
    action_type: Optional[str] = None
    user_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: Optional[int] = Field(100, ge=1, le=1000)


# =============================================================================
# Admin Status Routes
# =============================================================================

@router.get("/status")
async def admin_status(admin_id: str = Depends(verify_admin)):
    """Check admin status and get system overview."""
    db = get_supabase()
    training_manager = get_training_manager()
    
    # Get user counts from user_profiles
    users = db.table("user_profiles").select("id", count="exact").execute()
    
    # Get training stats
    training_stats = training_manager.get_training_stats()
    
    # Get document counts
    try:
        docs = db.table("brain_documents").select("id", count="exact").execute()
        doc_count = docs.count or 0
    except:
        doc_count = 0
    
    # Get recent activity
    try:
        recent_codes = db.table("afl_codes").select("id", count="exact").gte("created_at", datetime.utcnow() - timedelta(days=7)).execute()
        recent_feedback = db.table("user_feedback").select("id", count="exact").gte("created_at", datetime.utcnow() - timedelta(days=7)).execute()
    except:
        recent_codes = {"count": 0}
        recent_feedback = {"count": 0}
    
    return {
        "status": "admin",
        "admin_id": admin_id,
        "stats": {
            "total_users": users.count or 0,
            "total_documents": doc_count,
            "training": training_stats,
            "recent_activity": {
                "codes_generated_last_7_days": recent_codes.count or 0,
                "feedback_submitted_last_7_days": recent_feedback.count or 0,
            },
        }
    }


@router.post("/make-admin/{target_user_id}")
async def make_user_admin(
    target_user_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Make another user an admin."""
    db = get_supabase()
    
    result = db.table("user_profiles").update({"is_admin": True}).eq("id", target_user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Target user not found")
    
    # Log this action
    await log_admin_action(admin_id, "make_admin", {"target_user_id": target_user_id})
    
    return {"status": "success", "message": f"User {target_user_id} is now an admin"}


@router.post("/revoke-admin/{target_user_id}")
async def revoke_admin(
    target_user_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Revoke admin privileges from a user."""
    db = get_supabase()
    
    # Prevent revoking own admin
    if target_user_id == admin_id:
        raise HTTPException(status_code=400, detail="Cannot revoke your own admin privileges")
    
    result = db.table("user_profiles").update({"is_admin": False}).eq("id", target_user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Target user not found")
    
    # Log this action
    await log_admin_action(admin_id, "revoke_admin", {"target_user_id": target_user_id})
    
    return {"status": "success", "message": f"Admin privileges revoked from user {target_user_id}"}


# =============================================================================
# Training Routes
# =============================================================================

@router.post("/train")
async def add_training(
    data: TrainingExampleCreate,
    admin_id: str = Depends(verify_admin),
):
    """
    Add a new training example to teach the AI.
    
    Training types:
    - example: Input/output example pairs
    - rule: Rules the AI must follow
    - pattern: Code patterns to use
    - anti_pattern: Patterns to avoid
    - correction: Corrections to previous mistakes
    - terminology: Domain-specific terms
    """
    training_manager = get_training_manager()
    
    # Validate training type
    valid_types = [t.value for t in TrainingType]
    if data.training_type not in valid_types:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid training_type. Must be one of: {valid_types}"
        )
    
    result = training_manager.add_training_example(
        training_type=data.training_type,
        title=data.title,
        input_prompt=data.input_prompt,
        expected_output=data.expected_output,
        explanation=data.explanation,
        category=data.category,
        tags=data.tags,
        priority=data.priority,
        created_by=admin_id,
    )
    
    if result.get("status") == "success":
        await log_admin_action(admin_id, "add_training", {"training_id": result["data"]["id"], "title": data.title})
    
    return result


@router.post("/train/quick")
async def quick_train(
    data: QuickTrain,
    admin_id: str = Depends(verify_admin),
):
    """
    Quick training - simplified way to teach the AI something new.
    
    Just provide what you want the AI to learn and optionally an example.
    """
    training_manager = get_training_manager()
    
    # Create appropriate training entry based on input
    if data.example_input and data.example_output:
        # If both example input/output provided, create an example
        result = training_manager.add_training_example(
            training_type="example",
            title=data.what_to_learn[:100],
            input_prompt=data.example_input,
            expected_output=data.example_output,
            explanation=data.what_to_learn,
            category="afl",
            priority=7,
            created_by=admin_id,
        )
    else:
        # Otherwise create a rule
        result = training_manager.add_training_example(
            training_type=data.training_type,
            title=data.what_to_learn[:100],
            input_prompt=data.example_input or "Always apply this rule",
            expected_output=data.what_to_learn,
            explanation="Admin-defined rule",
            category="afl",
            priority=7,
            created_by=admin_id,
        )
    
    if result.get("status") == "success":
        await log_admin_action(admin_id, "quick_train", {"title": data.what_to_learn[:50]})
    
    return result


@router.post("/train/correction")
async def add_correction(
    data: CorrectionCreate,
    admin_id: str = Depends(verify_admin),
):
    """
    Add a correction when the AI made a mistake.
    
    Provide the original prompt, what the AI generated (wrong),
    what it should have generated (correct), and feedback explaining the issue.
    """
    training_manager = get_training_manager()
    
    result = training_manager.add_correction_from_feedback(
        original_prompt=data.original_prompt,
        wrong_output=data.wrong_output,
        correct_output=data.correct_output,
        feedback=data.feedback,
        created_by=admin_id,
    )
    
    if result.get("status") == "success":
        await log_admin_action(admin_id, "add_correction", {"feedback": data.feedback[:100]})
    
    return result


@router.post("/train/batch")
async def batch_import_training(
    data: BatchImport,
    admin_id: str = Depends(verify_admin),
):
    """Import multiple training examples at once."""
    training_manager = get_training_manager()
    
    items = [item.dict() for item in data.items]
    result = training_manager.import_training_batch(items, created_by=admin_id)
    
    if result.get("successful", 0) > 0:
        await log_admin_action(admin_id, "batch_import", {"imported": result["successful"], "failed": result["failed"]})
    
    return result


@router.get("/training")
async def list_training(
        training_type: Optional[str] = Query(None, description="Filter by training type"),
        category: Optional[str] = Query(None, description="Filter by category"),
        is_active: Optional[bool] = Query(True, description="Filter by active status"),
        limit: int = Query(100, ge=1, le=1000, description="Limit results"),
        offset: int = Query(0, ge=0, description="Offset for pagination"),
        admin_id: str = Depends(verify_admin),
):
    """List all training examples with optional filtering and pagination."""
    training_manager = get_training_manager()

    # OPTIMIZED: Specify which columns to fetch instead of SELECT *
    examples = training_manager.list_training_examples(
        training_type=training_type,
        category=category,
        is_active=is_active,
        limit=limit,
        offset=offset,  # Pass offset to training manager for better query optimization
    )

    return {
        "count": len(examples),
        "examples": examples,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": len(examples),
        }
    }


@router.get("/training/{training_id}")
async def get_training(
    training_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Get a single training example."""
    training_manager = get_training_manager()
    
    example = training_manager.get_training_example(training_id)
    
    if not example:
        raise HTTPException(status_code=404, detail="Training example not found")
    
    return example


@router.put("/training/{training_id}")
async def update_training(
    training_id: str,
    data: TrainingExampleUpdate,
    admin_id: str = Depends(verify_admin),
):
    """Update a training example."""
    training_manager = get_training_manager()
    
    # Filter out None values
    updates = {k: v for k, v in data.dict().items() if v is not None}
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    result = training_manager.update_training_example(training_id, updates)
    
    if result.get("status") == "success":
        await log_admin_action(admin_id, "update_training", {"training_id": training_id, "updates": list(updates.keys())})
    
    return result


@router.delete("/training/{training_id}")
async def delete_training(
    training_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Delete a training example."""
    training_manager = get_training_manager()
    
    result = training_manager.delete_training_example(training_id)
    
    if result.get("status") == "success":
        await log_admin_action(admin_id, "delete_training", {"training_id": training_id})
    
    return result


@router.post("/training/{training_id}/toggle")
async def toggle_training(
    training_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Toggle a training example's active status."""
    training_manager = get_training_manager()
    
    # Get current state
    example = training_manager.get_training_example(training_id)
    if not example:
        raise HTTPException(status_code=404, detail="Training example not found")
    
    # Toggle
    new_state = not example.get("is_active", True)
    result = training_manager.update_training_example(training_id, {"is_active": new_state})
    
    if result.get("status") == "success":
        await log_admin_action(admin_id, "toggle_training", {"training_id": training_id, "new_state": new_state})
    
    return {"status": "success", "is_active": new_state}


@router.get("/training/stats/overview")
async def training_stats(admin_id: str = Depends(verify_admin)):
    """Get training statistics."""
    training_manager = get_training_manager()
    return training_manager.get_training_stats()


@router.get("/training/export/all")
async def export_training(
    training_type: Optional[str] = Query(None, description="Filter by training type"),
    category: Optional[str] = Query(None, description="Filter by category"),
    admin_id: str = Depends(verify_admin),
):
    """Export all training data for backup."""
    training_manager = get_training_manager()
    
    data = training_manager.export_training_data(
        training_type=training_type,
        category=category,
    )
    
    return {"count": len(data), "data": data}


@router.get("/training/context/preview")
async def preview_training_context(
    category: Optional[str] = Query(None, description="Filter by category"),
    admin_id: str = Depends(verify_admin),
):
    """
    Preview the training context that gets injected into AI prompts.
    
    This shows you exactly what the AI "knows" from training.
    """
    training_manager = get_training_manager()
    
    context = training_manager.get_training_context(category=category)
    
    return {
        "context_length": len(context),
        "context": context,
    }


# =============================================================================
# User Management Routes
# =============================================================================

@router.get("/users")
async def list_users(
    limit: int = Query(100, ge=1, le=1000, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    admin_id: str = Depends(verify_admin),
):
    """List all users with pagination."""
    db = get_supabase()
    
    # Use user_profiles table joined with auth.users for email
    result = db.table("user_profiles").select(
        "id, name, nickname, is_admin, is_active, created_at, last_active_at"
    ).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    
    # Get total count
    total_result = db.table("user_profiles").select("id", count="exact").execute()
    
    return {
        "count": len(result.data),
        "total": total_result.count or 0,
        "users": result.data,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total_result.count or 0,
        }
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Get a specific user's details."""
    db = get_supabase()
    
    result = db.table("user_profiles").select("*").eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = result.data[0]
    # Remove encrypted API keys from admin response for security
    user.pop("claude_api_key_encrypted", None)
    user.pop("tavily_api_key_encrypted", None)

    return user


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    data: UserUpdateRequest,
    admin_id: str = Depends(verify_admin),
):
    """Update a user's information."""
    db = get_supabase()
    
    # Filter out None values
    updates = {k: v for k, v in data.dict().items() if v is not None}
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    result = db.table("user_profiles").update(updates).eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    await log_admin_action(admin_id, "update_user", {"user_id": user_id, "updates": list(updates.keys())})
    
    return {"status": "success", "message": f"User {user_id} updated"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Delete a user."""
    db = get_supabase()
    
    if user_id == admin_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    # Soft delete - mark as inactive instead of hard delete
    result = db.table("user_profiles").update({"is_active": False}).eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    await log_admin_action(admin_id, "delete_user", {"user_id": user_id})
    
    return {"status": "success", "message": f"User {user_id} marked as inactive"}


@router.post("/users/{user_id}/restore")
async def restore_user(
    user_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Restore a deleted/inactive user."""
    db = get_supabase()
    
    result = db.table("user_profiles").update({"is_active": True}).eq("id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    await log_admin_action(admin_id, "restore_user", {"user_id": user_id})
    
    return {"status": "success", "message": f"User {user_id} restored"}


# =============================================================================
# System Configuration Routes
# =============================================================================

@router.get("/config")
async def get_config(admin_id: str = Depends(verify_admin)):
    """Get system configuration (non-sensitive)."""
    return {
        "admin_emails": get_admin_emails(),
        "training_types": [t.value for t in TrainingType],
        "default_category": "afl",
        "system_status": "operational",
        "maintenance_mode": False,
    }


@router.put("/config")
async def update_config(
    data: SystemConfigUpdate,
    admin_id: str = Depends(verify_admin),
):
    """Update system configuration."""
    db = get_supabase()
    
    updates = {k: v for k, v in data.dict().items() if v is not None}
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    # Log this action
    await log_admin_action(admin_id, "update_config", {"updates": list(updates.keys())})
    
    return {"status": "success", "message": "Configuration updated", "updates": updates}


@router.post("/config/add-admin-email")
async def add_admin_email(
    email: str,
    admin_id: str = Depends(verify_admin),
):
    """
    Add an email to the admin list permanently.
    
    This adds the email to the database by setting is_admin=True for the user.
    For config-based admin emails, update ADMIN_EMAILS environment variable.
    """
    db = get_supabase()
    
    # Find user by email in auth.users via user_profiles
    # Note: We need to query auth.users for email, then update user_profiles
    # Since we can't directly query auth.users, we use the admin_user_list view
    result = db.table("user_profiles").select("id, is_admin").eq("email", email).execute()
    
    # If not found in user_profiles, check if they exist in auth.users
    if not result.data:
        # User may not have a profile yet - they need to log in first
        return {"status": "not_found", "message": f"No user found with email {email}. User may need to log in first."}
    
    user = result.data[0]
    
    if user.get("is_admin"):
        return {"status": "exists", "message": f"{email} is already an admin"}
    
    # Make them admin
    db.table("user_profiles").update({"is_admin": True}).eq("id", user["id"]).execute()
    
    await log_admin_action(admin_id, "add_admin_email", {"email": email, "user_id": user["id"]})
    
    return {"status": "success", "message": f"Added {email} as admin"}


# =============================================================================
# Feedback Review Routes (Admin Only)
# =============================================================================

@router.get("/feedback")
async def list_all_feedback(
    status: Optional[str] = Query(None, description="Filter by status"),
    feedback_type: Optional[str] = Query(None, description="Filter by feedback type"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    admin_id: str = Depends(verify_admin),
):
    """List all user feedback for review with pagination."""
    db = get_supabase()
    
    query = db.table("user_feedback").select(
        "id, user_id, feedback_type, feedback_text, rating, status, created_at, original_prompt"
    )
    
    if status:
        query = query.eq("status", status)
    if feedback_type:
        query = query.eq("feedback_type", feedback_type)
    
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    
    # Get total count
    total_query = db.table("user_feedback").select("id", count="exact")
    if status:
        total_query = total_query.eq("status", status)
    if feedback_type:
        total_query = total_query.eq("feedback_type", feedback_type)
    total_result = total_query.execute()
    
    return {
        "count": len(result.data),
        "total": total_result.count or 0,
        "feedback": result.data,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total_result.count or 0,
        }
    }


@router.get("/feedback/{feedback_id}")
async def get_feedback_details(
    feedback_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Get detailed feedback for review."""
    db = get_supabase()
    
    result = db.table("user_feedback").select("*").eq("id", feedback_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    return result.data[0]


class FeedbackReview(BaseModel):
    """Model for reviewing feedback."""
    status: str  # reviewed, implemented, rejected
    admin_notes: Optional[str] = None
    create_training: bool = False  # Whether to create training data from this


@router.post("/feedback/{feedback_id}/review")
async def review_feedback(
    feedback_id: str,
    review: FeedbackReview,
    admin_id: str = Depends(verify_admin),
):
    """
    Review and process user feedback.
    
    Can optionally create training data from the feedback.
    """
    db = get_supabase()
    training_manager = get_training_manager()
    
    # Get feedback
    feedback_result = db.table("user_feedback").select("*").eq("id", feedback_id).execute()
    
    if not feedback_result.data:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    feedback = feedback_result.data[0]
    
    # Update feedback status
    db.table("user_feedback").update({
        "status": review.status,
        "admin_notes": review.admin_notes,
        "reviewed_by": admin_id,
        "reviewed_at": "now()",
    }).eq("id", feedback_id).execute()
    
    # Create training data if requested and feedback is a correction
    training_result = None
    if review.create_training and feedback.get("correct_code") and feedback.get("feedback_type") == "correction":
        training_result = training_manager.add_correction_from_feedback(
            original_prompt=feedback["original_prompt"],
            wrong_output=feedback["generated_code"],
            correct_output=feedback["correct_code"],
            feedback=feedback["feedback_text"],
            created_by=admin_id,
        )
    
    await log_admin_action(admin_id, "review_feedback", {
        "feedback_id": feedback_id,
        "status": review.status,
        "create_training": review.create_training
    })
    
    return {
        "status": "success",
        "feedback_updated": True,
        "training_created": training_result is not None,
        "training_data": training_result,
    }


# =============================================================================
# Training Suggestions Review Routes (Admin Only)
# =============================================================================

@router.get("/suggestions")
async def list_training_suggestions(
    status: Optional[str] = Query("pending", description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    admin_id: str = Depends(verify_admin),
):
    """List training suggestions from users with pagination."""
    db = get_supabase()
    
    query = db.table("training_suggestions").select(
        "id, user_id, title, training_type, category, status, created_at"
    )
    
    if status:
        query = query.eq("status", status)
    
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    
    # Get total count
    total_query = db.table("training_suggestions").select("id", count="exact")
    if status:
        total_query = total_query.eq("status", status)
    total_result = total_query.execute()
    
    return {
        "count": len(result.data),
        "total": total_result.count or 0,
        "suggestions": result.data,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total_result.count or 0,
        }
    }


@router.get("/suggestions/{suggestion_id}")
async def get_suggestion_details(
    suggestion_id: str,
    admin_id: str = Depends(verify_admin),
):
    """Get detailed suggestion for review."""
    db = get_supabase()
    
    result = db.table("training_suggestions").select("*").eq("id", suggestion_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    return result.data[0]


class SuggestionReview(BaseModel):
    """Model for reviewing suggestions."""
    status: str  # approved, rejected, implemented
    admin_notes: Optional[str] = None
    priority: Optional[int] = None  # Override priority if approving


@router.post("/suggestions/{suggestion_id}/review")
async def review_suggestion(
    suggestion_id: str,
    review: SuggestionReview,
    admin_id: str = Depends(verify_admin),
):
    """
    Review and process training suggestion.
    
    If approved, creates actual training data from the suggestion.
    """
    db = get_supabase()
    training_manager = get_training_manager()
    
    # Get suggestion
    suggestion_result = db.table("training_suggestions").select("*").eq("id", suggestion_id).execute()
    
    if not suggestion_result.data:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    
    suggestion = suggestion_result.data[0]
    
    # If approved, create training data
    training_data_id = None
    if review.status == "approved":
        training_result = training_manager.add_training_example(
            training_type=suggestion["training_type"],
            title=suggestion["title"],
            input_prompt=suggestion["input_prompt"],
            expected_output=suggestion["expected_output"],
            explanation=suggestion.get("explanation", ""),
            category=suggestion.get("category", "afl"),
            tags=suggestion.get("tags", []),
            priority=review.priority or suggestion.get("priority", 5),
            created_by=admin_id,
        )
        
        if training_result.get("status") == "success":
            training_data_id = training_result["data"]["id"]
    
    # Update suggestion
    db.table("training_suggestions").update({
        "status": review.status,
        "admin_notes": review.admin_notes,
        "reviewed_by": admin_id,
        "reviewed_at": "now()",
        "training_data_id": training_data_id,
    }).eq("id", suggestion_id).execute()
    
    await log_admin_action(admin_id, "review_suggestion", {
        "suggestion_id": suggestion_id,
        "status": review.status,
        "training_created": training_data_id is not None
    })
    
    return {
        "status": "success",
        "suggestion_updated": True,
        "training_created": training_data_id is not None,
        "training_data_id": training_data_id,
    }


@router.post("/suggestions/{suggestion_id}/approve")
async def quick_approve_suggestion(
    suggestion_id: str,
    priority: int = 5,
    admin_id: str = Depends(verify_admin),
):
    """Quick approve - creates training data immediately."""
    return await review_suggestion(
        suggestion_id,
        SuggestionReview(status="approved", priority=priority),
        admin_id
    )


@router.post("/suggestions/{suggestion_id}/reject")
async def quick_reject_suggestion(
    suggestion_id: str,
    reason: Optional[str] = None,
    admin_id: str = Depends(verify_admin),
):
    """Quick reject with optional reason."""
    return await review_suggestion(
        suggestion_id,
        SuggestionReview(status="rejected", admin_notes=reason),
        admin_id
    )


# =============================================================================
# Analytics Routes (Admin Only)
# =============================================================================

@router.get("/analytics/overview")
async def get_analytics_overview(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    admin_id: str = Depends(verify_admin),
):
    """Get comprehensive analytics overview."""
    db = get_supabase()
    training_manager = get_training_manager()
    
    try:
        # User stats from user_profiles
        total_users = db.table("user_profiles").select("id", count="exact").execute()
        active_users = db.table("user_profiles").select("id", count="exact").gte("last_active_at", datetime.utcnow() - timedelta(days=days)).execute()
        
        # Code generation stats
        total_codes = db.table("afl_codes").select("id", count="exact").execute()
        recent_codes = db.table("afl_codes").select("id", count="exact").gte("created_at", datetime.utcnow() - timedelta(days=days)).execute()
        
        # Feedback stats
        feedback_stats = db.table("user_feedback").select("feedback_type, rating").gte("created_at", datetime.utcnow() - timedelta(days=days)).execute()
        
        # Calculate metrics
        ratings = [f.get("rating") for f in feedback_stats.data if f.get("rating")]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0
        
        corrections = len([f for f in feedback_stats.data if f.get("feedback_type") == "correction"])
        praise = len([f for f in feedback_stats.data if f.get("feedback_type") == "praise"])
        
        # Training stats
        training_stats = training_manager.get_training_stats()
        
        # Pending reviews
        pending_feedback = db.table("user_feedback").select("id", count="exact").eq("status", "pending_review").execute()
        pending_suggestions = db.table("training_suggestions").select("id", count="exact").eq("status", "pending").execute()
        
        return {
            "period": f"Last {days} days",
            "users": {
                "total": total_users.count or 0,
                "active": active_users.count or 0,
                "growth_rate": f"{((active_users.count or 0) / max(total_users.count or 1, 1)) * 100:.1f}%",
            },
            "code_generation": {
                "total_codes": total_codes.count or 0,
                "recent_codes": recent_codes.count or 0,
                "avg_per_day": f"{(recent_codes.count or 0) / max(days, 1):.1f}",
            },
            "feedback": {
                "total": len(feedback_stats.data),
                "average_rating": round(avg_rating, 2),
                "corrections": corrections,
                "praise": praise,
                "pending_review": pending_feedback.count or 0,
                "satisfaction_rate": f"{(praise / max(len(feedback_stats.data), 1)) * 100:.1f}%" if feedback_stats.data else "0%",
            },
            "training": {
                "total_examples": training_stats.get("total", 0),
                "active_examples": training_stats.get("active", 0),
                "by_type": training_stats.get("by_type", {}),
                "pending_suggestions": pending_suggestions.count or 0,
            },
        }
        
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/trends")
async def get_analytics_trends(
    days: int = Query(30, ge=7, le=90, description="Number of days to analyze"),
    admin_id: str = Depends(verify_admin),
):
    """Get usage trends over time."""
    db = get_supabase()
    
    try:
        # Generate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Daily code generation trend
        code_trend = db.table("afl_codes").select(
            "DATE(created_at) as date, COUNT(*) as count"
        ).gte("created_at", start_date).lte("created_at", end_date).group_by("DATE(created_at)").execute()
        
        # Daily feedback trend
        feedback_trend = db.table("user_feedback").select(
            "DATE(created_at) as date, COUNT(*) as count, AVG(rating) as avg_rating"
        ).gte("created_at", start_date).lte("created_at", end_date).group_by("DATE(created_at)").execute()
        
        # Daily user activity trend from user_profiles
        user_trend = db.table("user_profiles").select(
            "DATE(last_active_at) as date, COUNT(*) as active_users"
        ).gte("last_active_at", start_date).lte("last_active_at", end_date).group_by("DATE(last_active_at)").execute()
        
        return {
            "period_days": days,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "trends": {
                "code_generation": code_trend.data or [],
                "feedback": feedback_trend.data or [],
                "user_activity": user_trend.data or [],
            },
        }
        
    except Exception as e:
        logger.error(f"Error getting trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analytics/engagement")
async def get_engagement_metrics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    admin_id: str = Depends(verify_admin),
):
    """Get user engagement metrics."""
    db = get_supabase()
    
    try:
        # Active users by day from user_profiles
        daily_active = db.table("user_profiles").select(
            "DATE(last_active_at) as date, COUNT(*) as count"
        ).gte("last_active_at", datetime.utcnow() - timedelta(days=days)).group_by("DATE(last_active_at)").execute()
        
        # User retention (simplified) from user_profiles
        new_users = db.table("user_profiles").select("id, created_at").gte("created_at", datetime.utcnow() - timedelta(days=days)).execute()
        
        # Feature usage
        feature_usage = db.table("analytics_events").select(
            "event_type, COUNT(*) as count"
        ).gte("created_at", datetime.utcnow() - timedelta(days=days)).group_by("event_type").execute()
        
        return {
            "period_days": days,
            "engagement": {
                "daily_active_users": daily_active.data or [],
                "new_users": len(new_users.data or []),
                "feature_usage": feature_usage.data or [],
            },
        }
        
    except Exception as e:
        logger.error(f"Error getting engagement metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Audit Logs Routes (Admin Only)
# =============================================================================

@router.get("/audit-logs")
async def get_audit_logs(
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    admin_id: str = Depends(verify_admin),
):
    """Get admin audit logs with filtering and pagination."""
    db = get_supabase()
    
    query = db.table("analytics_events").select("*")
    
    # Apply filters
    if action_type:
        query = query.eq("event_type", action_type)
    if user_id:
        query = query.eq("user_id", user_id)
    if start_date:
        query = query.gte("created_at", start_date)
    if end_date:
        query = query.lte("created_at", end_date)
    
    # Filter to admin actions only
    query = query.in_("event_category", ["admin", "user_management", "training_management"])
    
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    
    # Get total count
    total_query = db.table("analytics_events").select("id", count="exact")
    if action_type:
        total_query = total_query.eq("event_type", action_type)
    if user_id:
        total_query = total_query.eq("user_id", user_id)
    if start_date:
        total_query = total_query.gte("created_at", start_date)
    if end_date:
        total_query = total_query.lte("created_at", end_date)
    total_query = total_query.in_("event_category", ["admin", "user_management", "training_management"])
    total_result = total_query.execute()
    
    return {
        "count": len(result.data),
        "total": total_result.count or 0,
        "audit_logs": result.data,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total_result.count or 0,
        },
        "filters": {
            "action_type": action_type,
            "user_id": user_id,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }
    }


# =============================================================================
# System Health Routes (Admin Only)
# =============================================================================

@router.get("/health/system")
async def get_system_health(admin_id: str = Depends(verify_admin)):
    """Get system health status."""
    db = get_supabase()
    
    try:
        # Database connectivity - use user_profiles
        db_test = db.table("user_profiles").select("id", count="exact").limit(1).execute()
        db_status = "healthy" if db_test.data is not None else "unhealthy"
        
        # Storage usage (approximate)
        storage_query = db.table("brain_documents").select("id", count="exact").execute()
        storage_count = storage_query.count or 0
        
        # Recent errors (if any)
        error_logs = db.table("analytics_events").select("*").eq("event_type", "error").gte("created_at", datetime.utcnow() - timedelta(hours=24)).execute()
        
        return {
            "status": "healthy",
            "components": {
                "database": db_status,
                "storage": "healthy",
                "api": "healthy",
            },
            "metrics": {
                "total_documents": storage_count,
                "recent_errors": len(error_logs.data or []),
                "last_check": datetime.utcnow().isoformat(),
            },
        }
        
    except Exception as e:
        logger.error(f"Error checking system health: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "last_check": datetime.utcnow().isoformat(),
        }


@router.post("/maintenance/toggle")
async def toggle_maintenance_mode(
    enable: bool,
    admin_id: str = Depends(verify_admin),
):
    """Toggle maintenance mode."""
    # This would typically be implemented with a config table or environment variable
    # For now, just log the action
    await log_admin_action(admin_id, "toggle_maintenance", {"enable": enable})
    
    return {
        "status": "success",
        "message": f"Maintenance mode {'enabled' if enable else 'disabled'}",
        "maintenance_mode": enable,
    }


# =============================================================================
# Utility Functions
# =============================================================================

async def log_admin_action(admin_id: str, action_type: str, details: Dict[str, Any]):
    """Log admin actions for audit trail."""
    db = get_supabase()
    
    try:
        db.table("analytics_events").insert({
            "user_id": admin_id,
            "event_type": action_type,
            "event_category": "admin",
            "event_data": details,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")


@router.get("/export/users")
async def export_users_data(
        admin_id: str = Depends(verify_admin),
):
    """Export user data for backup or analysis."""
    db = get_supabase()

    # Get users from user_profiles (no sensitive data like encrypted API keys)
    users = db.table("user_profiles").select(
        "id, name, nickname, is_admin, is_active, created_at, last_active_at"
    ).execute()

    # Get user IDs for batch queries
    user_ids = [u["id"] for u in users.data or []]

    # Get all code counts in one query
    codes_result = db.table("afl_codes").select("user_id").in_("user_id", user_ids).execute()
    codes_by_user = {}
    for code in codes_result.data or []:
        user_id = code["user_id"]
        codes_by_user[user_id] = codes_by_user.get(user_id, 0) + 1

    # Get all feedback counts in one query
    feedback_result = db.table("user_feedback").select("user_id").in_("user_id", user_ids).execute()
    feedback_by_user = {}
    for feedback in feedback_result.data or []:
        user_id = feedback["user_id"]
        feedback_by_user[user_id] = feedback_by_user.get(user_id, 0) + 1

    # Build user stats
    user_stats = []
    for user in users.data or []:
        user_stats.append({
            "user_id": user["id"],
            "name": user.get("name"),
            "nickname": user.get("nickname"),
            "is_admin": user.get("is_admin", False),
            "is_active": user.get("is_active", True),
            "created_at": user.get("created_at"),
            "last_active_at": user.get("last_active_at"),
            "codes_generated": codes_by_user.get(user["id"], 0),
            "feedback_submitted": feedback_by_user.get(user["id"], 0),
        })

    return {
        "export_date": datetime.utcnow().isoformat(),
        "total_users": len(user_stats),
        "users": user_stats,
    }


@router.get("/export/feedback")
async def export_feedback_data(
    status: Optional[str] = Query(None, description="Filter by status"),
    admin_id: str = Depends(verify_admin),
):
    """Export feedback data for analysis."""
    db = get_supabase()
    
    query = db.table("user_feedback").select("*")
    
    if status:
        query = query.eq("status", status)
    
    feedback_data = query.order("created_at", desc=True).execute()
    
    return {
        "export_date": datetime.utcnow().isoformat(),
        "total_feedback": len(feedback_data.data or []),
        "status": status,
        "feedback": feedback_data.data or [],
    }


@router.get("/export/training")
async def export_training_data(
    training_type: Optional[str] = Query(None, description="Filter by training type"),
    category: Optional[str] = Query(None, description="Filter by category"),
    admin_id: str = Depends(verify_admin),
):
    """Export training data for backup."""
    training_manager = get_training_manager()
    
    data = training_manager.export_training_data(
        training_type=training_type,
        category=category,
    )
    
    return {
        "export_date": datetime.utcnow().isoformat(),
        "total_training": len(data),
        "training_type": training_type,
        "category": category,
        "data": data,
    }