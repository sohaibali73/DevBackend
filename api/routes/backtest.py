"""Backtest analysis routes."""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import Optional
import json

from api.dependencies import get_current_user_id, get_user_api_keys
from core.prompts import get_backtest_analysis_prompt
from db.supabase_client import get_supabase

router = APIRouter(prefix="/backtest", tags=["Backtest Analysis"])

# Model to use for all backtest analysis
BACKTEST_MODEL = "claude-opus-4-6"


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

    # Analyze with Claude Opus 4
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_keys["claude"])

        # Get analysis
        analysis_response = await client.messages.create(
            model=BACKTEST_MODEL,
            max_tokens=8000,
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
            model=BACKTEST_MODEL,
            max_tokens=1000,
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
            model=BACKTEST_MODEL,
            max_tokens=2000,
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


# =============================================================================
# ── Extended backtest endpoints ───────────────────────────────────────────────
# =============================================================================

@router.get("/{backtest_id}/results")
async def get_backtest_results(
    backtest_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get detailed backtest results (structured for frontend charts/tables)."""
    db = get_supabase()

    result = db.table("backtest_results").select("*").eq("id", backtest_id).eq("user_id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Backtest not found")

    bt = result.data[0]
    metrics = bt.get("metrics") or {}

    return {
        "id": str(bt["id"]),
        "strategy_name": bt.get("filename", "Unnamed Strategy"),
        "filename": bt.get("filename", ""),
        "date_range": {
            "start": bt.get("start_date"),
            "end": bt.get("end_date"),
        },
        "summary": {
            "total_return": metrics.get("total_return") or metrics.get("cagr", 0),
            "annual_return": metrics.get("annual_return") or metrics.get("cagr", 0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
            "max_drawdown": metrics.get("max_drawdown", 0),
            "win_rate": metrics.get("win_rate", 0),
            "profit_factor": metrics.get("profit_factor", 0),
            "total_trades": metrics.get("total_trades", 0),
            "winning_trades": metrics.get("winning_trades", 0),
            "losing_trades": metrics.get("losing_trades", 0),
        },
        "monthly_returns": bt.get("monthly_returns") or [],
        "equity_curve": bt.get("equity_curve") or [],
        "trades": bt.get("trades") or [],
        "ai_analysis": bt.get("ai_analysis", ""),
        "recommendations": bt.get("recommendations") or [],
        "created_at": bt.get("created_at", ""),
    }


@router.post("/{backtest_id}/insights")
async def generate_backtest_insights(
    backtest_id: str,
    user_id: str = Depends(get_current_user_id),
    api_keys: dict = Depends(get_user_api_keys),
):
    """Generate AI-powered insights from backtest results."""
    db = get_supabase()

    result = db.table("backtest_results").select("*").eq("id", backtest_id).eq("user_id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Backtest not found")

    bt = result.data[0]
    metrics = bt.get("metrics") or {}

    # Rule-based insights (always generated, no API key needed)
    insights = []

    win_rate = float(metrics.get("win_rate", 0) or 0)
    sharpe = float(metrics.get("sharpe_ratio", 0) or 0)
    max_dd = float(metrics.get("max_drawdown", 0) or 0)
    total_trades = int(metrics.get("total_trades", 0) or 0)

    if win_rate > 60:
        insights.append({
            "type": "strength",
            "title": "Strong Win Rate",
            "description": f"Your strategy maintains a {win_rate:.1f}% win rate, which is excellent.",
            "icon": "trending-up",
            "color": "#22C55E",
        })
    elif win_rate < 45:
        insights.append({
            "type": "warning",
            "title": "Low Win Rate",
            "description": f"Win rate of {win_rate:.1f}% suggests room for improvement in signal quality.",
            "icon": "alert-triangle",
            "color": "#FF9800",
        })

    if abs(max_dd) > 20:
        insights.append({
            "type": "warning",
            "title": "Large Drawdown Risk",
            "description": f"Maximum drawdown of {max_dd:.1f}% may be uncomfortable for many traders.",
            "icon": "alert-triangle",
            "color": "#FF9800",
        })
    elif abs(max_dd) < 10:
        insights.append({
            "type": "strength",
            "title": "Controlled Risk",
            "description": f"Max drawdown of only {max_dd:.1f}% shows excellent capital preservation.",
            "icon": "shield",
            "color": "#22C55E",
        })

    if sharpe > 1.5:
        insights.append({
            "type": "strength",
            "title": "Excellent Risk-Adjusted Returns",
            "description": f"Sharpe ratio of {sharpe:.2f} indicates strong performance vs volatility.",
            "icon": "star",
            "color": "#22C55E",
        })
    elif sharpe < 0.5:
        insights.append({
            "type": "warning",
            "title": "Poor Risk-Adjusted Returns",
            "description": f"Sharpe ratio of {sharpe:.2f} suggests high volatility relative to returns.",
            "icon": "alert-triangle",
            "color": "#FF9800",
        })

    if total_trades < 20:
        insights.append({
            "type": "info",
            "title": "Low Trade Count",
            "description": f"Only {total_trades} trades — results may not be statistically significant.",
            "icon": "info",
            "color": "#60A5FA",
        })

    insights.append({
        "type": "recommendation",
        "title": "Consider Position Sizing",
        "description": "Implementing Kelly Criterion or fixed fractional sizing can optimise risk-adjusted returns.",
        "icon": "lightbulb",
        "color": "#60A5FA",
    })

    # Calculate overall rating
    score = 5.0
    if win_rate > 60: score += 1.5
    elif win_rate > 50: score += 0.5
    elif win_rate < 40: score -= 1.0
    if sharpe > 2.0: score += 2.0
    elif sharpe > 1.0: score += 1.0
    elif sharpe < 0.5: score -= 1.5
    dd = abs(max_dd)
    if dd < 10: score += 1.5
    elif dd > 25: score -= 1.5
    score = max(0, min(10, score))

    overall = "excellent" if score > 8 else "good" if score > 6 else "fair" if score > 4 else "poor"

    return {
        "backtest_id": backtest_id,
        "insights": insights,
        "overall_rating": overall,
        "rating_score": round(score, 1),
    }


from pydantic import BaseModel as _BaseModel
from typing import List as _List


class CompareBacktestsRequest(_BaseModel):
    backtest_ids: _List[str]


@router.post("/compare")
async def compare_backtests(
    request: CompareBacktestsRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Compare multiple backtests side by side."""
    if len(request.backtest_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 backtests required for comparison")

    db = get_supabase()
    backtests = []

    for bt_id in request.backtest_ids:
        res = db.table("backtest_results").select("id, filename, metrics, created_at").eq(
            "id", bt_id
        ).eq("user_id", user_id).limit(1).execute()
        if res.data:
            bt = res.data[0]
            m = bt.get("metrics") or {}
            backtests.append({
                "id": str(bt["id"]),
                "name": bt.get("filename", "Unnamed"),
                "total_return": float(m.get("total_return") or m.get("cagr", 0) or 0),
                "sharpe_ratio": float(m.get("sharpe_ratio", 0) or 0),
                "max_drawdown": float(m.get("max_drawdown", 0) or 0),
                "win_rate": float(m.get("win_rate", 0) or 0),
                "profit_factor": float(m.get("profit_factor", 0) or 0),
                "total_trades": int(m.get("total_trades", 0) or 0),
                "created_at": bt.get("created_at", ""),
            })

    if not backtests:
        raise HTTPException(status_code=404, detail="No backtests found")

    best_return = max(backtests, key=lambda x: x["total_return"])
    best_sharpe = max(backtests, key=lambda x: x["sharpe_ratio"])
    best_drawdown = max(backtests, key=lambda x: -abs(x["max_drawdown"]))

    return {
        "comparison": {
            "backtests": backtests,
            "winner": {
                "by_return": best_return["id"],
                "by_sharpe": best_sharpe["id"],
                "by_drawdown": best_drawdown["id"],
            },
        }
    }


@router.get("/{backtest_id}/export")
async def export_backtest_report(
    backtest_id: str,
    format: str = "json",
    user_id: str = Depends(get_current_user_id),
):
    """Export backtest report (json, csv). PDF/Excel are stubs pending library setup."""
    from fastapi.responses import Response, StreamingResponse as _StreamingResponse
    import io

    db = get_supabase()
    result = db.table("backtest_results").select("*").eq("id", backtest_id).eq("user_id", user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Backtest not found")

    bt = result.data[0]

    if format == "json":
        import json as _json
        content = _json.dumps(bt, indent=2, default=str).encode("utf-8")
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=backtest_{backtest_id}.json"},
        )

    elif format == "csv":
        metrics = bt.get("metrics") or {}
        lines = ["metric,value"]
        for k, v in metrics.items():
            lines.append(f"{k},{v}")
        content = "\n".join(lines).encode("utf-8")
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=backtest_{backtest_id}.csv"},
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{format}'. Use 'json' or 'csv'.")


@router.delete("/{backtest_id}")
async def delete_backtest(
    backtest_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a backtest result."""
    db = get_supabase()

    existing = db.table("backtest_results").select("user_id").eq("id", backtest_id).limit(1).execute()
    if not existing.data or existing.data[0]["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Backtest not found")

    db.table("backtest_results").delete().eq("id", backtest_id).execute()

    return {"success": True, "message": "Backtest deleted successfully"}
