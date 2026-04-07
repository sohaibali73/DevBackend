"""Dashboard routes - Statistics and activity feed."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends

from api.dependencies import get_current_user_id
from db.supabase_client import get_supabase

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
logger = logging.getLogger(__name__)


def _calc_change(current: int, previous: int) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


@router.get("/stats")
async def get_dashboard_stats(user_id: str = Depends(get_current_user_id)):
    """Get user's dashboard statistics."""
    db = get_supabase()

    # ── Total strategies (afl_history first, fall back to afl_codes) ─────────
    total_strategies = 0
    try:
        res = db.table("afl_history").select("id", count="exact").eq("user_id", user_id).execute()
        total_strategies = res.count or 0
    except Exception:
        try:
            res = db.table("afl_codes").select("id", count="exact").eq("user_id", user_id).execute()
            total_strategies = res.count or 0
        except Exception:
            pass

    # ── Total backtests ───────────────────────────────────────────────────────
    total_backtests = 0
    try:
        res = db.table("backtest_results").select("id", count="exact").eq("user_id", user_id).execute()
        total_backtests = res.count or 0
    except Exception:
        pass

    # ── Win rate & total trades from backtest metrics ─────────────────────────
    win_rate = 0.0
    total_trades = 0
    try:
        bt_data = db.table("backtest_results").select("metrics").eq("user_id", user_id).execute()
        if bt_data.data:
            win_rates = []
            for bt in bt_data.data:
                m = bt.get("metrics") or {}
                if isinstance(m, dict):
                    if m.get("win_rate") is not None:
                        win_rates.append(float(m["win_rate"]))
                    if m.get("total_trades") is not None:
                        total_trades += int(m["total_trades"])
            if win_rates:
                win_rate = round(sum(win_rates) / len(win_rates), 1)
    except Exception:
        pass

    # ── 30-day change for strategies ─────────────────────────────────────────
    strategy_change = 0.0
    try:
        cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
        prev_res = (
            db.table("afl_history")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .lt("timestamp", cutoff)
            .execute()
        )
        prev_strategies = prev_res.count or 0
        strategy_change = _calc_change(total_strategies, prev_strategies)
    except Exception:
        pass

    return {
        "total_strategies": total_strategies,
        "total_backtests": total_backtests,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "change_from_last_period": {
            "strategies": strategy_change,
            "backtests": 0.0,
            "win_rate": 0.0,
            "trades": 0.0,
        },
    }


@router.get("/activity")
async def get_recent_activity(
    limit: int = 10,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """Get user's recent activity feed."""
    db = get_supabase()
    activities = []

    # Recent AFL generations
    try:
        gens = (
            db.table("afl_history")
            .select("id, strategy_description, timestamp")
            .eq("user_id", user_id)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        for g in gens.data or []:
            activities.append({
                "id": f"gen_{g['id']}",
                "type": "code_generation",
                "title": f"Generated: {(g.get('strategy_description') or 'AFL Strategy')[:60]}",
                "timestamp": g.get("timestamp") or datetime.utcnow().isoformat(),
                "icon": "code",
                "color": "#FEC00F",
            })
    except Exception as e:
        logger.debug(f"activity – afl_history unavailable: {e}")

    # Recent backtests
    try:
        bts = (
            db.table("backtest_results")
            .select("id, filename, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        for bt in bts.data or []:
            activities.append({
                "id": f"bt_{bt['id']}",
                "type": "backtest",
                "title": f"Backtest analysed: {bt.get('filename', 'Results')}",
                "timestamp": bt.get("created_at") or datetime.utcnow().isoformat(),
                "icon": "trending-up",
                "color": "#22C55E",
            })
    except Exception as e:
        logger.debug(f"activity – backtest_results unavailable: {e}")

    # Recent KB uploads
    try:
        docs = (
            db.table("brain_documents")
            .select("id, title, created_at")
            .eq("uploaded_by", user_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        for doc in docs.data or []:
            activities.append({
                "id": f"doc_{doc['id']}",
                "type": "document_upload",
                "title": f"Uploaded: {doc.get('title', 'Document')}",
                "timestamp": doc.get("created_at") or datetime.utcnow().isoformat(),
                "icon": "file-text",
                "color": "#60A5FA",
            })
    except Exception as e:
        logger.debug(f"activity – brain_documents unavailable: {e}")

    # Sort by timestamp descending and paginate
    activities.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    total = len(activities)
    page = activities[offset: offset + limit]

    return {"activities": page, "total": total, "has_more": total > offset + limit}
