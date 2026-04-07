"""WebSocket routes — real-time updates for generation progress, notifications."""

import asyncio
import json
import logging
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from db.supabase_client import get_supabase

router = APIRouter(tags=["WebSocket"])
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Connection Manager
# ──────────────────────────────────────────────────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections keyed by user_id."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"WS connected: {user_id} ({len(self.active_connections)} total)")

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)
        logger.info(f"WS disconnected: {user_id} ({len(self.active_connections)} remaining)")

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """Send a JSON message to a specific user. Returns True if sent."""
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(message)
                return True
            except Exception as e:
                logger.warning(f"Failed to send WS message to {user_id}: {e}")
                self.disconnect(user_id)
        return False

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        disconnected = []
        for uid, ws in list(self.active_connections.items()):
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(uid)
        for uid in disconnected:
            self.disconnect(uid)

    @property
    def connected_users(self):
        return list(self.active_connections.keys())


# Global connection manager — shared across all requests
manager = ConnectionManager()


def get_ws_manager() -> ConnectionManager:
    """Return the global WebSocket connection manager."""
    return manager


# ──────────────────────────────────────────────────────────────────────────────
# Token verification helper
# ──────────────────────────────────────────────────────────────────────────────

def _verify_token(token: str) -> Optional[str]:
    """Verify a Supabase JWT and return user_id or None."""
    try:
        db = get_supabase()
        user = db.auth.get_user(token)
        return user.user.id if user and user.user else None
    except Exception as e:
        logger.debug(f"WS token verification failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Main WebSocket endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="Supabase JWT access token"),
):
    """
    WebSocket connection for real-time updates.

    Client connects with:
        ws://<host>/ws?token=<jwt>

    Supported client → server messages:
        {"type": "ping"}
        {"type": "subscribe", "channel": "generation_progress"}

    Server → client message types:
        {"type": "pong"}
        {"type": "connected", "user_id": "..."}
        {"type": "generation_progress", "payload": {...}}
        {"type": "notification", "payload": {...}}
        {"type": "error", "message": "..."}
    """
    # Authenticate
    user_id = _verify_token(token)
    if not user_id:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return

    await manager.connect(user_id, websocket)

    # Send welcome message
    await websocket.send_json({
        "type": "connected",
        "user_id": user_id,
        "message": "WebSocket connected successfully",
    })

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # Send keepalive ping and wait for pong
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "pong":
                pass  # Heartbeat acknowledged

            elif msg_type == "subscribe":
                channel = data.get("channel", "")
                await websocket.send_json({
                    "type": "subscribed",
                    "channel": channel,
                    "message": f"Subscribed to {channel}",
                })

            elif msg_type == "unsubscribe":
                channel = data.get("channel", "")
                await websocket.send_json({
                    "type": "unsubscribed",
                    "channel": channel,
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS error for user {user_id}: {e}")
    finally:
        manager.disconnect(user_id)


# ──────────────────────────────────────────────────────────────────────────────
# Utility functions — called from other route modules
# ──────────────────────────────────────────────────────────────────────────────

async def send_generation_progress(
    user_id: str,
    generation_id: str,
    stage: str,
    progress: int,
    message: str = "",
):
    """Push generation progress to a connected user via WebSocket."""
    await manager.send_to_user(user_id, {
        "type": "generation_progress",
        "payload": {
            "generation_id": generation_id,
            "stage": stage,
            "progress": progress,
            "message": message or f"{stage.capitalize()}…",
        },
    })


async def send_notification(user_id: str, title: str, body: str, level: str = "info"):
    """Push an in-app notification to a connected user."""
    await manager.send_to_user(user_id, {
        "type": "notification",
        "payload": {
            "title": title,
            "body": body,
            "level": level,   # "info" | "success" | "warning" | "error"
        },
    })


# ──────────────────────────────────────────────────────────────────────────────
# Admin WebSocket stats endpoint (HTTP, not WS)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/ws/stats")
async def ws_stats():
    """Return current WebSocket connection statistics (unauthenticated for monitoring)."""
    return {
        "connected_users": len(manager.active_connections),
        "user_ids": manager.connected_users,
    }
