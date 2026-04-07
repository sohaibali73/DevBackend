"""Training Courses routes — course listing, progress tracking, quiz submission."""

import logging
from datetime import datetime
from typing import Optional, Dict, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.dependencies import get_current_user_id
from db.supabase_client import get_supabase

router = APIRouter(prefix="/training", tags=["Training Courses"])
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class QuizSubmission(BaseModel):
    answers: Dict[str, str]  # {question_id: answer}


class EnrollRequest(BaseModel):
    course_id: str


# ──────────────────────────────────────────────────────────────────────────────
# Courses
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/courses")
async def list_courses(user_id: str = Depends(get_current_user_id)):
    """List all available training courses with user progress."""
    db = get_supabase()

    try:
        courses_res = db.table("courses").select(
            "id, title, description, level, duration, thumbnail_url, lessons"
        ).execute()
        courses_data = courses_res.data or []
    except Exception as e:
        logger.warning(f"courses table not available: {e}")
        # Return a helpful placeholder until the table is created
        return {
            "courses": _get_placeholder_courses(),
            "message": "courses table not yet created — run DB migration",
        }

    # Get user progress
    try:
        progress_res = (
            db.table("user_progress")
            .select("course_id, progress_percent, completed_lessons")
            .eq("user_id", user_id)
            .execute()
        )
        progress_map = {p["course_id"]: p for p in (progress_res.data or [])}
    except Exception:
        progress_map = {}

    course_list = []
    for course in courses_data:
        course_id = course["id"]
        prog = progress_map.get(course_id, {})
        lessons = course.get("lessons") or []

        course_list.append({
            "id": course_id,
            "title": course.get("title", ""),
            "description": course.get("description", ""),
            "level": course.get("level", "beginner"),
            "duration_minutes": course.get("duration", 0),
            "lessons_count": len(lessons),
            "enrolled": course_id in progress_map,
            "progress": prog.get("progress_percent", 0),
            "thumbnail": course.get("thumbnail_url"),
        })

    return {"courses": course_list}


@router.get("/courses/{course_id}")
async def get_course(course_id: str, user_id: str = Depends(get_current_user_id)):
    """Get a single course with full lesson details."""
    db = get_supabase()

    try:
        result = db.table("courses").select("*").eq("id", course_id).limit(1).execute()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"courses table unavailable: {e}")

    if not result.data:
        raise HTTPException(status_code=404, detail="Course not found")

    course = result.data[0]

    # Get user progress
    try:
        prog_res = (
            db.table("user_progress")
            .select("*")
            .eq("user_id", user_id)
            .eq("course_id", course_id)
            .limit(1)
            .execute()
        )
        progress = prog_res.data[0] if prog_res.data else {}
    except Exception:
        progress = {}

    completed_lessons = progress.get("completed_lessons") or []

    lessons = []
    for lesson in (course.get("lessons") or []):
        lessons.append({
            "id": lesson.get("id"),
            "title": lesson.get("title", ""),
            "type": lesson.get("type", "text"),
            "duration_minutes": lesson.get("duration", 5),
            "content_url": f"/training/lessons/{lesson.get('id')}/content",
            "completed": lesson.get("id") in completed_lessons,
            "quiz": lesson.get("quiz"),
        })

    return {
        "id": course_id,
        "title": course.get("title", ""),
        "description": course.get("description", ""),
        "level": course.get("level", "beginner"),
        "duration_minutes": course.get("duration", 0),
        "enrolled": bool(progress),
        "progress": progress.get("progress_percent", 0),
        "completed_lessons": completed_lessons,
        "lessons": lessons,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Lessons
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/courses/{course_id}/lessons")
async def get_course_lessons(course_id: str, user_id: str = Depends(get_current_user_id)):
    """Get all lessons for a course."""
    db = get_supabase()

    try:
        result = db.table("courses").select("lessons, title").eq("id", course_id).limit(1).execute()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"courses table unavailable: {e}")

    if not result.data:
        raise HTTPException(status_code=404, detail="Course not found")

    course = result.data[0]

    try:
        prog_res = (
            db.table("user_progress")
            .select("completed_lessons")
            .eq("user_id", user_id)
            .eq("course_id", course_id)
            .limit(1)
            .execute()
        )
        completed = (prog_res.data[0].get("completed_lessons") or []) if prog_res.data else []
    except Exception:
        completed = []

    lessons = []
    for lesson in (course.get("lessons") or []):
        lessons.append({
            "id": lesson.get("id"),
            "title": lesson.get("title", ""),
            "type": lesson.get("type", "text"),
            "duration_minutes": lesson.get("duration", 5),
            "content_url": f"/training/lessons/{lesson.get('id')}/content",
            "completed": lesson.get("id") in completed,
            "quiz": lesson.get("quiz"),
        })

    return {
        "course": {"id": course_id, "title": course.get("title", "")},
        "lessons": lessons,
    }


@router.get("/lessons/{lesson_id}/content")
async def get_lesson_content(lesson_id: str, user_id: str = Depends(get_current_user_id)):
    """Get lesson content."""
    db = get_supabase()

    try:
        # Find the lesson embedded in a course document
        result = db.table("courses").select("lessons").execute()
        for course in (result.data or []):
            for lesson in (course.get("lessons") or []):
                if lesson.get("id") == lesson_id:
                    return {
                        "id": lesson_id,
                        "title": lesson.get("title", ""),
                        "type": lesson.get("type", "text"),
                        "content": lesson.get("content", ""),
                        "video_url": lesson.get("video_url"),
                        "duration_minutes": lesson.get("duration", 5),
                    }
    except Exception as e:
        logger.warning(f"Could not fetch lesson content: {e}")

    raise HTTPException(status_code=404, detail="Lesson not found")


@router.post("/lessons/{lesson_id}/complete")
async def mark_lesson_complete(lesson_id: str, user_id: str = Depends(get_current_user_id)):
    """Mark a lesson as completed and update course progress."""
    db = get_supabase()

    # Find the course containing this lesson
    try:
        courses_res = db.table("courses").select("id, lessons").execute()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"courses table unavailable: {e}")

    course_id = None
    total_lessons = 0
    for course in (courses_res.data or []):
        for lesson in (course.get("lessons") or []):
            if lesson.get("id") == lesson_id:
                course_id = course["id"]
                total_lessons = len(course.get("lessons") or [])
                break
        if course_id:
            break

    if not course_id:
        raise HTTPException(status_code=404, detail="Lesson not found")

    # Upsert progress
    try:
        prog_res = (
            db.table("user_progress")
            .select("*")
            .eq("user_id", user_id)
            .eq("course_id", course_id)
            .limit(1)
            .execute()
        )
        existing = prog_res.data[0] if prog_res.data else None

        if existing:
            completed = list(set((existing.get("completed_lessons") or []) + [lesson_id]))
        else:
            completed = [lesson_id]

        progress_pct = round((len(completed) / total_lessons) * 100, 1) if total_lessons else 0

        upsert_data = {
            "user_id": user_id,
            "course_id": course_id,
            "completed_lessons": completed,
            "progress_percent": progress_pct,
            "updated_at": datetime.utcnow().isoformat(),
        }

        db.table("user_progress").upsert(upsert_data, on_conflict="user_id,course_id").execute()

        # Determine next lesson
        next_lesson_id = None
        for course in (courses_res.data or []):
            if course["id"] == course_id:
                lessons_list = course.get("lessons") or []
                for i, l in enumerate(lessons_list):
                    if l.get("id") == lesson_id and i + 1 < len(lessons_list):
                        next_lesson_id = lessons_list[i + 1].get("id")
                        break
                break

        return {
            "success": True,
            "next_lesson_id": next_lesson_id,
            "course_progress": progress_pct,
            "completed_count": len(completed),
            "total_lessons": total_lessons,
        }

    except Exception as e:
        logger.error(f"Failed to mark lesson complete: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update progress: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# Quiz
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/quizzes/{quiz_id}/submit")
async def submit_quiz(
    quiz_id: str,
    submission: QuizSubmission,
    user_id: str = Depends(get_current_user_id),
):
    """Submit quiz answers and return score with feedback."""
    db = get_supabase()

    try:
        quiz_res = db.table("quizzes").select("*").eq("id", quiz_id).limit(1).execute()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"quizzes table unavailable: {e}")

    if not quiz_res.data:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz = quiz_res.data[0]
    questions = quiz.get("questions") or []
    passing_score = quiz.get("passing_score", 70)

    correct_count = 0
    feedback = []

    for question in questions:
        qid = question.get("id")
        user_answer = submission.answers.get(qid, "")
        correct_answer = question.get("correct_answer", "")
        is_correct = user_answer == correct_answer

        if is_correct:
            correct_count += 1

        feedback.append({
            "question_id": qid,
            "question": question.get("question", ""),
            "correct": is_correct,
            "user_answer": user_answer,
            "correct_answer": correct_answer if not is_correct else None,
            "explanation": question.get("explanation", ""),
        })

    total = len(questions)
    score = round((correct_count / total) * 100, 1) if total > 0 else 0
    passed = score >= passing_score

    # Save result
    try:
        db.table("quiz_results").insert({
            "user_id": user_id,
            "quiz_id": quiz_id,
            "score": score,
            "passed": passed,
            "answers": submission.answers,
            "submitted_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to save quiz result: {e}")

    return {
        "quiz_id": quiz_id,
        "score": score,
        "total_questions": total,
        "correct_answers": correct_count,
        "passed": passed,
        "passing_score": passing_score,
        "feedback": feedback,
    }


@router.get("/quizzes/{quiz_id}/results")
async def get_quiz_results(quiz_id: str, user_id: str = Depends(get_current_user_id)):
    """Get the user's latest quiz result."""
    db = get_supabase()

    try:
        result = (
            db.table("quiz_results")
            .select("*")
            .eq("quiz_id", quiz_id)
            .eq("user_id", user_id)
            .order("submitted_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail="No quiz results found")
        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"quiz_results table unavailable: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# User Progress
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/progress")
async def get_overall_progress(user_id: str = Depends(get_current_user_id)):
    """Get overall training progress across all courses."""
    db = get_supabase()

    try:
        progress_res = (
            db.table("user_progress")
            .select("course_id, progress_percent, updated_at")
            .eq("user_id", user_id)
            .execute()
        )
        return {
            "courses_started": len(progress_res.data or []),
            "courses_completed": sum(
                1 for p in (progress_res.data or [])
                if (p.get("progress_percent") or 0) >= 100
            ),
            "progress": progress_res.data or [],
        }
    except Exception as e:
        logger.warning(f"user_progress table unavailable: {e}")
        return {"courses_started": 0, "courses_completed": 0, "progress": []}


# ──────────────────────────────────────────────────────────────────────────────
# Placeholder data helper
# ──────────────────────────────────────────────────────────────────────────────

def _get_placeholder_courses() -> list:
    """Return sample course data while the DB table is being set up."""
    return [
        {
            "id": "course_afl_fundamentals",
            "title": "AFL Fundamentals",
            "description": "Learn AmiBroker Formula Language from scratch.",
            "level": "beginner",
            "duration_minutes": 120,
            "lessons_count": 8,
            "enrolled": False,
            "progress": 0,
            "thumbnail": None,
        },
        {
            "id": "course_backtest_mastery",
            "title": "Backtest Mastery",
            "description": "Advanced backtesting techniques and metrics interpretation.",
            "level": "intermediate",
            "duration_minutes": 90,
            "lessons_count": 6,
            "enrolled": False,
            "progress": 0,
            "thumbnail": None,
        },
        {
            "id": "course_system_trading",
            "title": "Building Trading Systems",
            "description": "Build and deploy full automated trading systems.",
            "level": "advanced",
            "duration_minutes": 180,
            "lessons_count": 12,
            "enrolled": False,
            "progress": 0,
            "thumbnail": None,
        },
    ]
