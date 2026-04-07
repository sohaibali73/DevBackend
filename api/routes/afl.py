"""AFL code generation routes."""

from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic import Field
import json
import logging
import base64

from api.dependencies import get_current_user_id, get_user_api_keys
from core.claude_engine import ClaudeAFLEngine, StrategyType, BacktestSettings, DEFAULT_MODEL
from core.context_manager import build_optimized_context
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/afl", tags=["AFL Generation"])


class GenerationPhase(str, Enum):
    """Phases of AFL generation workflow."""
    INITIAL = "initial"
    AWAITING_ANSWERS = "awaiting_answers"
    GENERATING = "generating"
    COMPLETE = "complete"


class BacktestSettingsInput(BaseModel):
    """User-provided backtest settings for AFL generation."""
    initial_equity: float = 100000
    position_size: str = "100"
    # FIX-02: position_size_type kept for API compatibility but BacktestSettings.to_afl()
    # no longer uses it — PositionSize is now a plain assignment, not SetPositionSize().
    position_size_type: str = "spsPercentOfEquity"
    max_positions: int = 10
    # FIX-02: commission default corrected from 0.001 to 0.0005 (0.05% per trade).
    # Matches BacktestSettings dataclass, afl.py BACKTEST_SETTINGS, and SKILL.md.
    commission: float = 0.0005
    trade_delays: Tuple[int, int, int, int] = (0, 0, 0, 0)
    margin_requirement: float = 100

    class Config:
        json_schema_extra = {
            "example": {
                "initial_equity": 100000,
                "position_size": "100",
                "position_size_type": "spsPercentOfEquity",
                "max_positions": 10,
                "commission": 0.0005,
                "trade_delays": [0, 0, 0, 0],
                "margin_requirement": 100
            }
        }


class GenerateRequest(BaseModel):
    """Request model for AFL generation."""
    prompt: str = Field(..., min_length=10, max_length=1000, description="Strategy description")
    strategy_type: str = Field("standalone", description="Strategy type: standalone or composite")
    settings: Optional[Dict[str, Any]] = None  # Legacy settings dict
    backtest_settings: Optional[BacktestSettingsInput] = None  # Structured backtest settings
    conversation_id: Optional[str] = None
    answers: Optional[Dict[str, str]] = None  # {"strategy_type": "standalone", "trade_timing": "close"}
    stream: Optional[bool] = Field(False, description="Enable streaming responses")
    uploaded_file_ids: Optional[List[str]] = None  # File references for context
    kb_context: Optional[str] = None  # Additional knowledge base context
    use_kb: Optional[bool] = Field(False, description="Set to true to include KB context in generation")
    thinking_mode: Optional[str] = Field(None, description="Extended thinking mode: enabled or disabled")
    thinking_budget: Optional[int] = Field(None, description="Thinking budget tokens (if enabled)")


class OptimizeRequest(BaseModel):
    """Request model for AFL optimization."""
    code: str


class DebugRequest(BaseModel):
    """Request model for AFL debugging."""
    code: str
    error_message: Optional[str] = ""


class ExplainRequest(BaseModel):
    """Request model for AFL explanation."""
    code: str


class ValidateRequest(BaseModel):
    """Request model for AFL validation."""
    code: str


@router.post("/generate")
async def generate_afl(
        request: GenerateRequest,
        user_id: str = Depends(get_current_user_id),
        api_keys: dict = Depends(get_user_api_keys),
):
    """Generate AFL code with optional mandatory question flow."""

    if not api_keys.get("claude"):
        raise HTTPException(
            status_code=400,
            detail="Claude API key not configured. Please add your API key in Profile Settings."
        )

    db = get_supabase()

    # Determine if we're using the conversation workflow or simple generation
    if request.conversation_id or request.answers:
        # Conversation-based workflow with mandatory questions
        return await _generate_with_conversation(request, user_id, api_keys, db)
    else:
        # Simple one-shot generation
        return await _generate_simple(request, user_id, api_keys, db)


async def _generate_simple(
        request: GenerateRequest,
        user_id: str,
        api_keys: dict,
        db,
) -> Dict[str, Any]:
    """Simple one-shot AFL generation without conversation workflow."""
    try:
        # Create thinking config if provided
        thinking_config = None
        if request.thinking_mode:
            from core.claude_engine import ThinkingMode, ThinkingConfig
            mode = ThinkingMode.ENABLED if request.thinking_mode.lower() == "enabled" else ThinkingMode.DISABLED
            thinking_config = ThinkingConfig(
                mode=mode,
                budget_tokens=request.thinking_budget
            )
        
        engine = ClaudeAFLEngine(api_key=api_keys["claude"], thinking_config=thinking_config)

        # Parse strategy type
        strat_type = StrategyType.STANDALONE
        if request.strategy_type.lower() == "composite":
            strat_type = StrategyType.COMPOSITE

        # Convert BacktestSettingsInput to BacktestSettings if provided
        settings = None
        if request.backtest_settings:
            settings = BacktestSettings(
                initial_equity=request.backtest_settings.initial_equity,
                position_size=request.backtest_settings.position_size,
                position_size_type=request.backtest_settings.position_size_type,
                max_positions=request.backtest_settings.max_positions,
                commission=request.backtest_settings.commission,
                trade_delays=request.backtest_settings.trade_delays,
                margin_requirement=request.backtest_settings.margin_requirement,
            )
        elif request.settings:
            # Legacy settings dict support
            settings = BacktestSettings(**request.settings)

        # Build file context from uploaded files
        file_context = ""
        if request.uploaded_file_ids:
            file_context = _build_file_context(db, user_id, request.uploaded_file_ids)

        # Build combined context:
        # - Files uploaded → use ONLY file context (user provided direct context)
        # - use_kb=True → include KB context (user explicitly requested it)
        # - Otherwise → no context
        combined_context = ""
        if file_context:
            combined_context = "\n\nUPLOADED FILES:\n" + file_context
        elif request.use_kb and request.kb_context:
            combined_context = request.kb_context

        # Check if streaming is requested
        if request.stream:
            # Return streaming response
            async def generate_stream():
                try:
                    # FIX: removed strategy_type=strat_type — generate_afl() has no such parameter.
                    # FIX: added kb_context=combined_context so file/KB context reaches the engine
                    #      in streaming mode (it was built above but never passed before).
                    generator = await engine.generate_afl(
                        request=request.prompt,
                        settings=settings,
                        kb_context=combined_context,
                        stream=True,
                    )

                    async for chunk in generator:
                        yield f"data: {json.dumps(chunk)}\n\n"

                        # Save to database when complete
                        if chunk.get("type") == "complete":
                            try:
                                db.table("afl_codes").insert({
                                    "user_id": user_id,
                                    "name": request.prompt[:100],
                                    "description": request.prompt,
                                    "code": chunk.get("afl_code", ""),
                                    "strategy_type": request.strategy_type,
                                    "quality_score": chunk.get("stats", {}).get("quality_score", 0),
                                }).execute()
                            except Exception as db_error:
                                logger.warning(f"Failed to save AFL code to database: {db_error}")
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                }
            )

        # Non-streaming generation
        result = await engine.generate_afl(
            request=request.prompt,
            settings=settings,
            kb_context=combined_context,
            stream=False,
        )

        afl_code = result.get("afl_code", "")

        # Save to database (with error handling for missing table)
        try:
            db.table("afl_codes").insert({
                "user_id": user_id,
                "name": request.prompt[:100],
                "description": request.prompt,
                "code": afl_code,
                "strategy_type": request.strategy_type,
                "quality_score": result.get("stats", {}).get("quality_score", 0),
            }).execute()
        except Exception as db_error:
            logger.warning(f"Failed to save AFL code to database: {db_error}")

        # Save to history (auto-save on generation)
        try:
            db.table("afl_history").insert({
                "user_id": user_id,
                "strategy_description": request.prompt,
                "generated_code": afl_code,
                "strategy_type": request.strategy_type,
                "timestamp": datetime.utcnow().isoformat(),
            }).execute()
            logger.info(f"AFL history saved successfully for user {user_id}")
        except Exception as e:
            error_detail = str(e)
            if "PGRST205" in error_detail:
                logger.error(
                    f"afl_history table not found in database. "
                    f"Run migration 004_history_tables_FIXED.sql in Supabase. Error: {error_detail}"
                )
            elif "violates foreign key constraint" in error_detail:
                logger.error(f"User {user_id} not found in users table. Error: {error_detail}")
            else:
                logger.warning(f"Failed to save AFL history: {error_detail}")

        # Return response with 'code' field for frontend compatibility
        return {
            "code": afl_code,
            "afl_code": afl_code,  # Keep for backward compatibility
            "explanation": result.get("explanation", ""),
            "stats": result.get("stats", {}),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _generate_with_conversation(
        request: GenerateRequest,
        user_id: str,
        api_keys: dict,
        db,
) -> Dict[str, Any]:
    """AFL generation with conversation workflow and mandatory questions."""

    # Get or create conversation
    if request.conversation_id:
        conv = db.table("conversations").select("*").eq("id", request.conversation_id).execute()
        conversation = conv.data[0] if conv.data else None
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        phase = conversation.get("phase", GenerationPhase.INITIAL)
    else:
        # Create new conversation
        conv_result = db.table("conversations").insert({
            "user_id": user_id,
            "title": request.prompt[:50],
            "conversation_type": "afl_generation",
            "phase": GenerationPhase.INITIAL,
        }).execute()
        conversation = conv_result.data[0]
        request.conversation_id = conversation["id"]
        phase = GenerationPhase.INITIAL

    try:
        # Create thinking config if provided
        thinking_config = None
        if request.thinking_mode:
            from core.claude_engine import ThinkingMode, ThinkingConfig
            mode = ThinkingMode.ENABLED if request.thinking_mode.lower() == "enabled" else ThinkingMode.DISABLED
            thinking_config = ThinkingConfig(
                mode=mode,
                budget_tokens=request.thinking_budget
            )
        
        engine = ClaudeAFLEngine(api_key=api_keys["claude"], thinking_config=thinking_config)

        # PHASE 1: Ask mandatory questions
        if phase == GenerationPhase.INITIAL:
            questions_prompt = f"""The user wants to create an AFL strategy: "{request.prompt}"

⚠️ CRITICAL: Before writing ANY code, you MUST ask these two questions IF THE USER HAS NOT SPECIEIFIED IT ALREADY IF THEY DID JUST ACKNOLWEDGE IT:

IF THEY DIDNT SPECIFIFY THEN
1. "Do you want this to be a **standalone strategy** in one AFL file, or part of a **composite** system?"
   - Standalone = Complete strategy with all sections (buy/sell, plotting, exploration, backtest settings)
   - Composite = Module to be included in a master template (only strategy logic, no plotting/settings)

2. "Do you want to trade on the **OPEN** or the **CLOSE** of the bar?"
   - CLOSE = SetTradeDelays(0, 0, 0, 0)
   - OPEN = SetTradeDelays(1, 1, 1, 1)

Please ask these questions clearly and wait for the user's response. Do NOT generate any code yet."""

            import anthropic
            client = anthropic.Anthropic(api_key=api_keys["claude"])

            # FIX-12: was hardcoded to claude-haiku-4-5-20251001.
            # Now uses DEFAULT_MODEL (claude-sonnet-4-6) imported from claude_engine,
            # so this stays in sync automatically whenever the engine model is updated.
            response = client.messages.create(
                model=DEFAULT_MODEL,
                max_tokens=1000,
                messages=[{"role": "user", "content": questions_prompt}],
            )

            questions = response.content[0].text

            # Save messages
            db.table("messages").insert([
                {"conversation_id": request.conversation_id, "role": "user", "content": request.prompt},
                {"conversation_id": request.conversation_id, "role": "assistant", "content": questions},
            ]).execute()

            # Update phase
            db.table("conversations").update({
                "phase": GenerationPhase.AWAITING_ANSWERS
            }).eq("id", request.conversation_id).execute()

            return {
                "conversation_id": request.conversation_id,
                "phase": GenerationPhase.AWAITING_ANSWERS,
                "response": questions,
                "needs_answers": True,
            }

        # PHASE 2: Generate code with answers
        elif phase == GenerationPhase.AWAITING_ANSWERS and request.answers:
            # Validate answers
            if not request.answers.get("strategy_type") or not request.answers.get("trade_timing"):
                raise HTTPException(
                    status_code=400,
                    detail="Missing required answers: strategy_type and trade_timing"
                )

            # Map answers
            strategy_type = StrategyType.STANDALONE if "standalone" in request.answers[
                "strategy_type"].lower() else StrategyType.COMPOSITE

            if "close" in request.answers["trade_timing"].lower():
                trade_delays = (0, 0, 0, 0)
            else:
                trade_delays = (1, 1, 1, 1)

            settings = BacktestSettings(trade_delays=trade_delays)
            if request.settings:
                # Merge with provided settings
                for key, value in request.settings.items():
                    if hasattr(settings, key):
                        setattr(settings, key, value)

            # Get conversation history with optimization
            from core.context_manager import get_recent_messages
            conversation_history = get_recent_messages(request.conversation_id)

            # Use streaming to prevent client timeout (Skills API can take 20-40s)
            async def conversation_generate_stream():
                try:
                    generator = await engine.generate_afl(
                        request=request.prompt,
                        settings=settings,
                        conversation_history=conversation_history,
                        user_answers=request.answers,
                        stream=True,
                    )

                    async for chunk in generator:
                        yield f"data: {json.dumps(chunk)}\n\n"

                        # When generation completes, save to database
                        if chunk.get("type") == "complete":
                            afl_code = chunk.get("afl_code", "")
                            stats = chunk.get("stats", {})

                            try:
                                # Save to afl_codes
                                code_result = db.table("afl_codes").insert({
                                    "user_id": user_id,
                                    "conversation_id": request.conversation_id,
                                    "name": request.prompt[:100],
                                    "description": request.prompt,
                                    "code": afl_code,
                                    "strategy_type": strategy_type.value,
                                    "quality_score": stats.get("quality_score", 0),
                                }).execute()

                                # Save assistant message
                                db.table("messages").insert({
                                    "conversation_id": request.conversation_id,
                                    "role": "assistant",
                                    "content": f"## Generated AFL Code\n\n```afl\n{afl_code}\n```",
                                }).execute()

                                # Update conversation phase
                                db.table("conversations").update({
                                    "phase": GenerationPhase.COMPLETE
                                }).eq("id", request.conversation_id).execute()

                                # Send final metadata event
                                code_id = code_result.data[0]["id"] if code_result.data else None
                                yield f"data: {json.dumps({'type': 'saved', 'conversation_id': request.conversation_id, 'code_id': code_id, 'phase': GenerationPhase.COMPLETE})}\n\n"

                            except Exception as db_error:
                                logger.warning(f"Failed to save conversation AFL code: {db_error}")
                                yield f"data: {json.dumps({'type': 'warning', 'message': f'Code generated but DB save failed: {db_error}'})}\n\n"

                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

            return StreamingResponse(
                conversation_generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                }
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid phase transition. Current phase: {phase}, Has answers: {bool(request.answers)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize")
async def optimize_afl(
        request: OptimizeRequest,
        api_keys: dict = Depends(get_user_api_keys),
):
    """Optimize existing AFL code."""

    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key not configured")

    try:
        engine = ClaudeAFLEngine(api_key=api_keys["claude"])
        optimized = await engine.optimize_code(request.code)

        return {"optimized_code": optimized}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/debug")
async def debug_afl(
        request: DebugRequest,
        api_keys: dict = Depends(get_user_api_keys),
):
    """Debug AFL code and fix errors."""

    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key not configured")

    try:
        engine = ClaudeAFLEngine(api_key=api_keys["claude"])
        debugged = await engine.debug_code(request.code, request.error_message)

        return {"debugged_code": debugged}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/explain")
async def explain_afl(
        request: ExplainRequest,
        api_keys: dict = Depends(get_user_api_keys),
):
    """Explain AFL code in plain English."""

    if not api_keys.get("claude"):
        raise HTTPException(status_code=400, detail="Claude API key not configured")

    try:
        engine = ClaudeAFLEngine(api_key=api_keys["claude"])
        explanation = await engine.explain_code(request.code)

        return {"explanation": explanation}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_afl(request: ValidateRequest):
    """Validate AFL code syntax without API call."""

    engine = ClaudeAFLEngine()  # No API key needed for validation
    result = engine.validate_code(request.code)

    return result


@router.get("/codes")
async def list_codes(
        user_id: str = Depends(get_current_user_id),
        limit: int = 50,
):
    """List user's saved AFL codes."""
    db = get_supabase()

    result = db.table("afl_codes").select(
        "id, name, description, strategy_type, quality_score, created_at"
    ).eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()

    return result.data


@router.get("/codes/{code_id}")
async def get_code(
        code_id: str,
        user_id: str = Depends(get_current_user_id),
):
    """Get a specific AFL code."""
    db = get_supabase()

    result = db.table("afl_codes").select("*").eq("id", code_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Code not found")

    return result.data[0]


@router.delete("/codes/{code_id}")
async def delete_code(
        code_id: str,
        user_id: str = Depends(get_current_user_id),
):
    """Delete an AFL code."""
    db = get_supabase()

    # Verify ownership
    existing = db.table("afl_codes").select("user_id").eq("id", code_id).execute()
    if not existing.data or existing.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Code not found")

    db.table("afl_codes").delete().eq("id", code_id).execute()

    return {"status": "deleted"}


# ===== AFL History Endpoints =====

class AFLHistoryEntry(BaseModel):
    """Request model for AFL history entry."""
    strategy_description: str
    generated_code: str
    strategy_type: str
    timestamp: Optional[str] = None


@router.post("/history")
async def save_afl_history(
    entry: AFLHistoryEntry,
    user_id: str = Depends(get_current_user_id),
):
    """Save AFL generation to history."""
    db = get_supabase()

    result = db.table("afl_history").insert({
        "user_id": user_id,
        "strategy_description": entry.strategy_description,
        "generated_code": entry.generated_code,
        "strategy_type": entry.strategy_type,
        "timestamp": entry.timestamp or datetime.utcnow().isoformat(),
    }).execute()

    return result.data[0]


@router.get("/history")
async def get_afl_history(
    user_id: str = Depends(get_current_user_id),
    limit: int = 50,
):
    """Get AFL generation history for user."""
    db = get_supabase()

    result = db.table("afl_history").select("*").eq(
        "user_id", user_id
    ).order("timestamp", desc=True).limit(limit).execute()

    return result.data


@router.delete("/history/{history_id}")
async def delete_afl_history(
    history_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete an AFL history entry."""
    db = get_supabase()

    # Verify ownership
    entry = db.table("afl_history").select("user_id").eq("id", history_id).execute()

    if not entry.data or entry.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="History entry not found")

    db.table("afl_history").delete().eq("id", history_id).execute()

    return {"status": "deleted", "id": history_id}


# ===== File Upload Endpoints =====

@router.post("/upload")
async def upload_afl_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload a file for AFL generation context.
    Accepts any file type.
    """
    db = get_supabase()

    # Validate file size (max 50MB)
    max_size = 50 * 1024 * 1024  # 50MB
    content = await file.read()

    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 50MB"
        )

    try:
        # Process based on file type - handle text vs binary
        file_data = {}

        # Text-based content types that can be decoded as UTF-8
        text_types = [
            'text/', 'application/json', 'application/xml', 'application/javascript',
            'application/typescript', 'application/x-httpd-php', 'application/sql',
            'application/graphql', 'application/x-yaml', 'application/yaml',
        ]
        
        # Also treat common text-based extensions as text
        text_extensions = ['.csv', '.txt', '.afl', '.json', '.xml', '.html', '.htm', 
                          '.css', '.js', '.ts', '.py', '.java', '.c', '.cpp', '.h',
                          '.md', '.sql', '.yaml', '.yml', '.toml', '.ini', '.cfg',
                          '.log', '.sh', '.bat', '.ps1', '.rb', '.go', '.rs', '.php']
        
        filename_lower = (file.filename or '').lower()
        content_type = file.content_type or "application/octet-stream"
        
        is_text = (
            any(content_type.startswith(t) for t in text_types) or
            any(filename_lower.endswith(ext) for ext in text_extensions)
        )

        if is_text:
            # Decode as text
            text_content = content.decode('utf-8', errors='ignore')
            file_data = {
                "filename": file.filename,
                "content_type": content_type,
                "text_content": text_content,
                "preview": text_content[:500] + "..." if len(text_content) > 500 else text_content,
            }
        else:
            # Store binary files as base64
            base64_content = base64.b64encode(content).decode('utf-8')
            file_data = {
                "filename": file.filename,
                "content_type": content_type,
                "base64_content": base64_content,
                "size_bytes": len(content),
            }

        # Store in database
        result = db.table("afl_uploaded_files").insert({
            "user_id": user_id,
            "filename": file.filename,
            "content_type": file.content_type,
            "file_data": file_data,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()

        logger.info(f"File uploaded successfully: {file.filename} by user {user_id}")

        return {
            "file_id": result.data[0]["id"],
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": len(content),
            "preview": file_data.get("preview", ""),
        }
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/files")
async def get_uploaded_files(
    user_id: str = Depends(get_current_user_id),
    limit: int = 50,
):
    """Get all uploaded files for user."""
    db = get_supabase()

    result = db.table("afl_uploaded_files").select(
        "id, filename, content_type, created_at"
    ).eq(
        "user_id", user_id
    ).order("created_at", desc=True).limit(limit).execute()

    return result.data


@router.get("/files/{file_id}")
async def get_file_details(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get detailed file information."""
    db = get_supabase()

    result = db.table("afl_uploaded_files").select("*").eq("id", file_id).execute()

    if not result.data or result.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="File not found")

    return result.data[0]


@router.delete("/files/{file_id}")
async def delete_uploaded_file(
    file_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete an uploaded file."""
    db = get_supabase()

    # Verify ownership
    file = db.table("afl_uploaded_files").select("user_id").eq("id", file_id).execute()

    if not file.data or file.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="File not found")

    db.table("afl_uploaded_files").delete().eq("id", file_id).execute()

    return {"status": "deleted", "file_id": file_id}


# ===== Helper Function for File Context =====

def _build_file_context(db, user_id: str, file_ids: List[str]) -> str:
    """Build context string from uploaded files."""
    if not file_ids:
        return ""

    file_context = ""
    files = db.table("afl_uploaded_files").select("*").in_(
        "id", file_ids
    ).eq("user_id", user_id).execute()

    for file in files.data:
        file_data = file.get("file_data", {})
        file_context += f"\n\n--- File: {file['filename']} ---\n"

        if "text_content" in file_data:
            text = file_data["text_content"]
            if len(text) > 5000:
                text = text[:5000] + "\n... (truncated for context)"
            file_context += text
        elif "preview" in file_data:
            file_context += file_data["preview"]
        elif "base64_content" in file_data:
            file_context += f"[Binary file: {file['filename']} ({file.get('content_type', 'unknown')})]"
        else:
            file_context += f"[File: {file['filename']}]"

    return file_context


# ===== Settings Presets Endpoints =====

class SettingsPreset(BaseModel):
    """Request model for saving settings preset."""
    name: str = Field(..., min_length=1, max_length=100, description="Preset name")
    settings: BacktestSettingsInput
    is_default: Optional[bool] = Field(False, description="Set as default preset")


@router.post("/settings/presets")
async def save_settings_preset(
    preset: SettingsPreset,
    user_id: str = Depends(get_current_user_id),
):
    """
    Save a settings preset for the user.
    If is_default is True, unsets any existing default first.
    """
    db = get_supabase()

    try:
        if preset.is_default:
            db.table("afl_settings_presets").update({
                "is_default": False
            }).eq("user_id", user_id).eq("is_default", True).execute()

        settings_dict = {
            "initial_equity": preset.settings.initial_equity,
            "position_size": preset.settings.position_size,
            "position_size_type": preset.settings.position_size_type,
            "max_positions": preset.settings.max_positions,
            "commission": preset.settings.commission,
            "trade_delays": list(preset.settings.trade_delays),
            "margin_requirement": preset.settings.margin_requirement,
        }

        result = db.table("afl_settings_presets").insert({
            "user_id": user_id,
            "name": preset.name,
            "settings": settings_dict,
            "is_default": preset.is_default,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()

        logger.info(f"Settings preset '{preset.name}' saved for user {user_id}")

        return {
            "id": result.data[0]["id"],
            "name": preset.name,
            "settings": settings_dict,
            "is_default": preset.is_default,
        }

    except Exception as e:
        logger.error(f"Failed to save settings preset: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save preset: {str(e)}")


@router.get("/settings/presets")
async def get_settings_presets(
    user_id: str = Depends(get_current_user_id),
):
    """Get all settings presets for the user."""
    db = get_supabase()

    result = db.table("afl_settings_presets").select("*").eq(
        "user_id", user_id
    ).order("created_at", desc=True).execute()

    return result.data


@router.get("/settings/presets/{preset_id}")
async def get_settings_preset(
    preset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a specific settings preset."""
    db = get_supabase()

    result = db.table("afl_settings_presets").select("*").eq("id", preset_id).execute()

    if not result.data or result.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Preset not found")

    return result.data[0]


@router.put("/settings/presets/{preset_id}")
async def update_settings_preset(
    preset_id: str,
    preset: SettingsPreset,
    user_id: str = Depends(get_current_user_id),
):
    """Update an existing settings preset."""
    db = get_supabase()

    existing = db.table("afl_settings_presets").select("user_id").eq("id", preset_id).execute()
    if not existing.data or existing.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Preset not found")

    try:
        if preset.is_default:
            db.table("afl_settings_presets").update({
                "is_default": False
            }).eq("user_id", user_id).eq("is_default", True).neq("id", preset_id).execute()

        settings_dict = {
            "initial_equity": preset.settings.initial_equity,
            "position_size": preset.settings.position_size,
            "position_size_type": preset.settings.position_size_type,
            "max_positions": preset.settings.max_positions,
            "commission": preset.settings.commission,
            "trade_delays": list(preset.settings.trade_delays),
            "margin_requirement": preset.settings.margin_requirement,
        }

        result = db.table("afl_settings_presets").update({
            "name": preset.name,
            "settings": settings_dict,
            "is_default": preset.is_default,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", preset_id).execute()

        return result.data[0]

    except Exception as e:
        logger.error(f"Failed to update settings preset: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update preset: {str(e)}")


@router.delete("/settings/presets/{preset_id}")
async def delete_settings_preset(
    preset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a settings preset."""
    db = get_supabase()

    existing = db.table("afl_settings_presets").select("user_id").eq("id", preset_id).execute()
    if not existing.data or existing.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Preset not found")

    db.table("afl_settings_presets").delete().eq("id", preset_id).execute()

    return {"status": "deleted", "preset_id": preset_id}


@router.post("/settings/presets/{preset_id}/set-default")
async def set_default_preset(
    preset_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Set a preset as the default."""
    db = get_supabase()

    existing = db.table("afl_settings_presets").select("*").eq("id", preset_id).execute()
    if not existing.data or existing.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Preset not found")

    db.table("afl_settings_presets").update({
        "is_default": False
    }).eq("user_id", user_id).eq("is_default", True).execute()

    result = db.table("afl_settings_presets").update({
        "is_default": True
    }).eq("id", preset_id).execute()

    return result.data[0]


# =============================================================================
# ── Generation aliases (frontend-facing endpoints) ────────────────────────────
# =============================================================================

@router.get("/generation/{generation_id}")
async def get_generation(
    generation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Retrieve a specific AFL generation (alias for /afl/codes/{id})."""
    db = get_supabase()

    # Check afl_history first (newer schema)
    try:
        result = db.table("afl_history").select("*").eq("id", generation_id).eq("user_id", user_id).limit(1).execute()
        if result.data:
            rec = result.data[0]
            return {
                "id": str(rec["id"]),
                "request": rec.get("strategy_description", ""),
                "afl_code": rec.get("generated_code", ""),
                "code": rec.get("generated_code", ""),
                "strategy_type": rec.get("strategy_type", "standalone"),
                "timestamp": rec.get("timestamp", rec.get("created_at", "")),
                "backtest_settings": {},
            }
    except Exception:
        pass

    # Fall back to afl_codes
    result = db.table("afl_codes").select("*").eq("id", generation_id).eq("user_id", user_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Generation not found")

    rec = result.data[0]
    return {
        "id": str(rec["id"]),
        "request": rec.get("description", "") or rec.get("name", ""),
        "afl_code": rec.get("code", ""),
        "code": rec.get("code", ""),
        "strategy_type": rec.get("strategy_type", "standalone"),
        "timestamp": rec.get("created_at", ""),
        "backtest_settings": {},
    }


@router.delete("/generation/{generation_id}")
async def delete_generation(
    generation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a generation (checks both afl_history and afl_codes)."""
    db = get_supabase()

    deleted = False

    # Try afl_history first
    try:
        entry = db.table("afl_history").select("user_id").eq("id", generation_id).limit(1).execute()
        if entry.data and entry.data[0]["user_id"] == user_id:
            db.table("afl_history").delete().eq("id", generation_id).execute()
            deleted = True
    except Exception:
        pass

    # Try afl_codes
    if not deleted:
        try:
            entry = db.table("afl_codes").select("user_id").eq("id", generation_id).limit(1).execute()
            if entry.data and entry.data[0]["user_id"] == user_id:
                db.table("afl_codes").delete().eq("id", generation_id).execute()
                deleted = True
        except Exception:
            pass

    if not deleted:
        raise HTTPException(status_code=404, detail="Generation not found")

    return {"success": True, "message": "Generation deleted successfully"}


# =============================================================================
# ── Feedback ──────────────────────────────────────────────────────────────────
# =============================================================================

class FeedbackRequest(BaseModel):
    generation_id: str
    feedback: str   # "positive" | "negative"
    comment: Optional[str] = None


@router.post("/feedback")
async def submit_afl_feedback(
    request: FeedbackRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Submit thumbs-up/thumbs-down feedback on a generated AFL code."""
    db = get_supabase()

    if request.feedback not in ("positive", "negative"):
        raise HTTPException(status_code=400, detail="feedback must be 'positive' or 'negative'")

    # Save feedback record
    try:
        db.table("afl_feedback").insert({
            "generation_id": request.generation_id,
            "user_id": user_id,
            "feedback": request.feedback,
            "comment": request.comment,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.warning(f"afl_feedback table may not exist yet: {e}")

    # Also annotate the source record
    for table in ("afl_history", "afl_codes"):
        try:
            db.table(table).update({"feedback": request.feedback}).eq(
                "id", request.generation_id
            ).eq("user_id", user_id).execute()
        except Exception:
            pass

    return {"success": True, "message": "Thank you for your feedback!"}


# =============================================================================
# ── Format Code ───────────────────────────────────────────────────────────────
# =============================================================================

class FormatRequest(BaseModel):
    code: str


@router.post("/format")
async def format_afl_code(request: FormatRequest):
    """Format / pretty-print AFL code."""
    formatted = _format_afl(request.code)
    return {"success": True, "formatted_code": formatted}


def _format_afl(code: str) -> str:
    """Basic AFL code formatter — normalises indentation around braces."""
    lines = code.split("\n")
    result = []
    indent = 0

    for raw in lines:
        line = raw.strip()

        # Decrease indent before closing brace lines
        if line.startswith("}"):
            indent = max(0, indent - 1)

        result.append("    " * indent + line)

        # Increase indent after opening brace lines
        if line.endswith("{"):
            indent += 1

    return "\n".join(result)
