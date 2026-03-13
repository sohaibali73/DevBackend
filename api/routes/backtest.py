"""Backtest analysis routes."""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import Optional
import json

from api.dependencies import get_current_user_id, get_user_api_keys
from core.prompts import get_backtest_analysis_prompt
from db.supabase_client import get_supabase

router = APIRouter(prefix="/backtest", tags=["Backtest Analysis"])

@router.post("/upload")
async def upload_backtest(
        file: UploadFile = File(...),
        strategy_id: Optional[str] = Form(None),
        user_id: str = Depends(get_current_user_id),
        api_keys: dict = Depends(get_user_api_keys),
):
    """Upload and analyze backtest results."""
    db = get_supabase()

    if not api_keys.get("claude"):
        raise HTTPException(
            status_code=400, 
            detail="Claude API key not configured. Please add your API key in Profile Settings."
        )

    # Read content
    content = (await file.read()).decode("utf-8", errors="ignore")

    # Create record
    backtest_result = db.table("backtest_results").insert({
        "user_id": user_id,
        "strategy_id": strategy_id,
        "raw_results": content,
        "filename": file.filename,
    }).execute()

    backtest_id = backtest_result.data[0]["id"]

    # Analyze with Claude
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_keys["claude"])

        # Get analysis
        analysis_response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            system=get_backtest_analysis_prompt(),
            messages=[{"role": "user", "content": f"Analyze these backtest results:\n\n{content[:10000]}"}],
        )

        analysis = analysis_response.content[0].text

        # Extract metrics
        metrics_prompt = f"""Extract key metrics from these backtest results as JSON:
{content[:5000]}

Return ONLY JSON:
{{"cagr": number, "sharpe_ratio": number, "max_drawdown": number, "win_rate": number, "profit_factor": number, "total_trades": number}}
"""

        metrics_response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": metrics_prompt}],
        )

        try:
            metrics_raw = metrics_response.content[0].text
            if "```" in metrics_raw:
                metrics_raw = metrics_raw.split("```")[1].split("```")[0]
                if metrics_raw.startswith("json"):
                    metrics_raw = metrics_raw[4:]
            metrics = json.loads(metrics_raw)
        except:
            metrics = {}

        # Get recommendations
        rec_prompt = f"""Based on this analysis:
{analysis[:2000]}

Provide 5 specific recommendations as JSON array:
[{{"priority": 1, "recommendation": "...", "expected_impact": "...", "implementation": "..."}}]
"""

        rec_response = await client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1500,
            messages=[{"role": "user", "content": rec_prompt}],
        )

        try:
            rec_raw = rec_response.content[0].text
            if "```" in rec_raw:
                rec_raw = rec_raw.split("```")[1].split("```")[0]
                if rec_raw.startswith("json"):
                    rec_raw = rec_raw[4:]
            recommendations = json.loads(rec_raw)
        except:
            recommendations = []

        # Update record
        db.table("backtest_results").update({
            "metrics": metrics,
            "ai_analysis": analysis,
            "recommendations": recommendations,
        }).eq("id", backtest_id).execute()

        return {
            "backtest_id": backtest_id,
            "metrics": metrics,
            "analysis": analysis,
            "recommendations": recommendations,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def list_backtests(
        user_id: str = Depends(get_current_user_id),
):
    """List all backtests for the current user."""
    db = get_supabase()

    try:
        result = db.table("backtest_results").select(
            "id, filename, metrics, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(50).execute()
        return result.data
    except Exception:
        return []


@router.get("/{backtest_id}")
async def get_backtest(
        backtest_id: str,
        user_id: str = Depends(get_current_user_id),
):
    """Get backtest analysis."""
    db = get_supabase()

    result = db.table("backtest_results").select("*").eq("id", backtest_id).eq("user_id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Backtest not found")

    return result.data[0]


@router.get("/strategy/{strategy_id}")
async def get_strategy_backtests(
        strategy_id: str,
        user_id: str = Depends(get_current_user_id),
):
    """Get all backtests for a strategy."""
    db = get_supabase()

    result = db.table("backtest_results").select("*").eq(
        "strategy_id", strategy_id
    ).order("created_at", desc=True).execute()

    return result.data
