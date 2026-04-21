"""
core/yang/settings.py — YANG Feature Configuration
===================================================
Loads per-user settings from the `user_yang_settings` table and merges
them with any per-request overrides supplied in ChatAgentRequest.yang.

Usage:
    from core.yang.settings import load_yang_config, save_yang_settings, YangConfig

    cfg = await load_yang_config(user_id, overrides=request.yang)
    if cfg.yolo_mode:
        ...
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ─── Frozen config dataclass ─────────────────────────────────────────────────

@dataclass(frozen=True)
class YangConfig:
    """
    Immutable snapshot of all YANG feature flags for a single request.
    Created by merging DB defaults with per-request overrides.
    """
    subagents:        bool = True
    parallel_tools:   bool = True
    plan_mode:        bool = False
    tool_search:      bool = True
    auto_compact:     bool = True
    focus_chain:      bool = True
    background_edit:  bool = False
    checkpoints:      bool = True
    yolo_mode:        bool = False
    double_check:     bool = False
    # Advanced tunables from the `advanced` jsonb column
    subagent_max:          int   = 5        # max concurrent subagents
    subagent_timeout_s:    int   = 45       # per-subagent timeout
    subagent_max_tokens:   int   = 2048     # per-subagent output budget
    compact_token_threshold: int = 30_000   # payload tokens before compaction
    compact_message_min:   int   = 20       # min messages before compaction
    compact_debounce_min:  int   = 10       # minutes between compactions
    focus_llm_every_n:     int   = 5        # turns between LLM focus polish
    double_check_model:    str   = "claude-haiku-4-5"
    compact_model:         str   = "claude-haiku-4-5"
    focus_model:           str   = "claude-haiku-4-5"


    @classmethod
    def defaults(cls) -> "YangConfig":
        """Return a config with all default values."""
        return cls()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API responses and logging."""
        return {
            "subagents":        self.subagents,
            "parallel_tools":   self.parallel_tools,
            "plan_mode":        self.plan_mode,
            "tool_search":      self.tool_search,
            "auto_compact":     self.auto_compact,
            "focus_chain":      self.focus_chain,
            "background_edit":  self.background_edit,
            "checkpoints":      self.checkpoints,
            "yolo_mode":        self.yolo_mode,
            "double_check":     self.double_check,
            "advanced": {
                "subagent_max":           self.subagent_max,
                "subagent_timeout_s":     self.subagent_timeout_s,
                "subagent_max_tokens":    self.subagent_max_tokens,
                "compact_token_threshold": self.compact_token_threshold,
                "compact_message_min":    self.compact_message_min,
                "compact_debounce_min":   self.compact_debounce_min,
                "focus_llm_every_n":      self.focus_llm_every_n,
                "double_check_model":     self.double_check_model,
                "compact_model":          self.compact_model,
                "focus_model":            self.focus_model,
            },
        }


# ─── DB helpers ───────────────────────────────────────────────────────────────

_BOOL_FIELDS = {
    "subagents", "parallel_tools", "plan_mode", "tool_search",
    "auto_compact", "focus_chain", "background_edit",
    "checkpoints", "yolo_mode", "double_check",
}

_ADVANCED_INT_FIELDS = {
    "subagent_max", "subagent_timeout_s", "subagent_max_tokens",
    "compact_token_threshold", "compact_message_min",
    "compact_debounce_min", "focus_llm_every_n",
}

_ADVANCED_STR_FIELDS = {
    "double_check_model", "compact_model", "focus_model",
}


def _build_config(row: Dict[str, Any]) -> YangConfig:
    """Build a YangConfig from a DB row dict."""
    advanced = row.get("advanced") or {}

    def adv_int(key: str, default: int) -> int:
        try:
            return int(advanced.get(key, default))
        except (TypeError, ValueError):
            return default

    def adv_str(key: str, default: str) -> str:
        return str(advanced.get(key, default))

    return YangConfig(
        subagents=bool(row.get("subagents", True)),
        parallel_tools=bool(row.get("parallel_tools", True)),
        plan_mode=bool(row.get("plan_mode", False)),
        tool_search=bool(row.get("tool_search", True)),
        auto_compact=bool(row.get("auto_compact", True)),
        focus_chain=bool(row.get("focus_chain", True)),
        background_edit=bool(row.get("background_edit", False)),
        checkpoints=bool(row.get("checkpoints", True)),
        yolo_mode=bool(row.get("yolo_mode", False)),
        double_check=bool(row.get("double_check", False)),
        subagent_max=adv_int("subagent_max", 5),
        subagent_timeout_s=adv_int("subagent_timeout_s", 45),
        subagent_max_tokens=adv_int("subagent_max_tokens", 2048),
        compact_token_threshold=adv_int("compact_token_threshold", 30_000),
        compact_message_min=adv_int("compact_message_min", 20),
        compact_debounce_min=adv_int("compact_debounce_min", 10),
        focus_llm_every_n=adv_int("focus_llm_every_n", 5),
        # Use Anthropic model aliases — they auto-resolve to the latest published
        # version, so we never 404 on a stale dated slug.
        double_check_model=adv_str("double_check_model", "claude-haiku-4-5"),
        compact_model=adv_str("compact_model", "claude-haiku-4-5"),
        focus_model=adv_str("focus_model", "claude-haiku-4-5"),

    )


def _apply_overrides(base: YangConfig, overrides: Optional[Any]) -> YangConfig:
    """
    Merge per-request overrides (YangOverrides Pydantic model or dict)
    onto an existing YangConfig.  Only non-None override values win.
    """
    if overrides is None:
        return base

    # Support both Pydantic model and plain dict
    if hasattr(overrides, "model_dump"):
        ov = overrides.model_dump(exclude_none=True)
    elif hasattr(overrides, "dict"):
        ov = {k: v for k, v in overrides.dict().items() if v is not None}
    elif isinstance(overrides, dict):
        ov = {k: v for k, v in overrides.items() if v is not None}
    else:
        logger.warning("yang overrides has unexpected type %s — ignored", type(overrides))
        return base

    if not ov:
        return base

    # dataclass is frozen — rebuild from dict representation
    base_dict = base.to_dict()
    advanced = dict(base_dict.pop("advanced"))

    for field, value in ov.items():
        if field in _BOOL_FIELDS:
            base_dict[field] = bool(value)
        # per-request advanced overrides (if passed as dict)
        elif field == "advanced" and isinstance(value, dict):
            advanced.update(value)

    # Rebuild config with merged values (advanced stays as separate kwarg)
    return _build_config({**base_dict, "advanced": advanced})


# ─── Public API ───────────────────────────────────────────────────────────────

def load_yang_config(
    user_id: str,
    overrides: Optional[Any] = None,
) -> YangConfig:
    """
    Load per-user YANG settings from the DB and merge with request overrides.

    - If no DB row exists for the user, auto-creates one with all defaults
      and returns the default config.
    - On any DB error, logs a warning and falls back to defaults.
    - Overrides are applied last so request-level flags always win.

    Args:
        user_id:   Authenticated user's UUID.
        overrides: Optional YangOverrides Pydantic model or dict with
                   per-request flag overrides.

    Returns:
        Frozen YangConfig for this request.
    """
    try:
        from db.supabase_client import get_supabase
        db = get_supabase()

        result = db.table("user_yang_settings").select("*").eq(
            "user_id", user_id
        ).single().execute()

        if result.data:
            cfg = _build_config(result.data)
        else:
            # Auto-create default row for new user
            try:
                db.table("user_yang_settings").insert(
                    {"user_id": user_id}
                ).execute()
                logger.info("Created default yang_settings for user %s", user_id)
            except Exception as insert_err:
                # Might fail if another request beat us to it (race) — safe to ignore
                logger.debug("yang_settings auto-create race: %s", insert_err)
            cfg = YangConfig.defaults()

    except Exception as e:
        logger.warning("load_yang_config failed for %s — using defaults: %s", user_id, e)
        cfg = YangConfig.defaults()

    return _apply_overrides(cfg, overrides)


def save_yang_settings(user_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist a partial update to the user's yang settings.

    Args:
        user_id: Authenticated user's UUID.
        patch:   Dict of fields to update.  Only recognised fields are written.
                 Unknown keys are silently ignored.

    Returns:
        The updated DB row as a dict.

    Raises:
        RuntimeError: if the DB write fails.
    """
    from db.supabase_client import get_supabase
    db = get_supabase()

    safe_patch: Dict[str, Any] = {}

    for key, val in patch.items():
        if key in _BOOL_FIELDS:
            safe_patch[key] = bool(val)
        elif key == "advanced" and isinstance(val, dict):
            # Merge into existing advanced jsonb column via DB upsert
            safe_patch["advanced"] = val  # caller should pass full advanced dict

    if not safe_patch:
        raise ValueError("No recognised fields in patch")

    try:
        result = db.table("user_yang_settings").upsert(
            {"user_id": user_id, **safe_patch},
            on_conflict="user_id",
        ).execute()
        return result.data[0] if result.data else safe_patch
    except Exception as e:
        raise RuntimeError(f"Failed to save yang settings: {e}") from e
