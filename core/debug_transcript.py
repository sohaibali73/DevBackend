"""
Debug Transcript System
=======================
Captures every step of every backend process when DEBUG_TRANSCRIPTS_ENABLED=1.

Records:
  - System prompt
  - Full message history fed to the LLM
  - Every streamed text token (buffered)
  - Every tool call — name + full JSON input + full JSON output
  - Every sandbox execution — code + stdout/stderr + exit code
  - Skill invocations
  - Per-iteration token usage
  - Final response + total usage

Storage:  $STORAGE_ROOT/debug_transcripts/<user_id>/<conv_id>/<req_id>.{json,txt}

Zero overhead when disabled — all hooks are `if _dt:` guarded.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ContextVar — automatically propagates through asyncio.to_thread copies
# ---------------------------------------------------------------------------
_current_transcript: ContextVar[Optional["DebugTranscript"]] = ContextVar(
    "_current_transcript", default=None
)


def is_debug_enabled() -> bool:
    """Return True if DEBUG_TRANSCRIPTS_ENABLED=1."""
    return os.getenv("DEBUG_TRANSCRIPTS_ENABLED", "0").strip() == "1"


def get_current_transcript() -> Optional["DebugTranscript"]:
    """Return the DebugTranscript for the current request context, or None."""
    return _current_transcript.get()


def set_current_transcript(dt: Optional["DebugTranscript"]) -> None:
    """Set the DebugTranscript for the current request context."""
    _current_transcript.set(dt)


# ---------------------------------------------------------------------------
# DebugTranscript
# ---------------------------------------------------------------------------

class DebugTranscript:
    """
    Thread-safe container for all debug events in a single request.

    Create one per request inside generate_stream(), set it on the ContextVar,
    then call write() when the stream finishes.
    """

    def __init__(
        self,
        conversation_id: str = "",
        user_id: str = "",
        storage_root: Optional[str] = None,
    ) -> None:
        self.request_id = f"req_{uuid.uuid4().hex[:12]}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.conversation_id = conversation_id or "unknown"
        self.user_id = user_id or "unknown"
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: Optional[datetime] = None
        self.model: str = ""

        self._events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._text_buffer: str = ""
        self._text_buffer_start: Optional[datetime] = None
        self._TEXT_FLUSH_SIZE = 300  # flush buffer at this many chars

        _root = storage_root or os.getenv("STORAGE_ROOT", "/data")
        self._base_dir = (
            Path(_root)
            / "debug_transcripts"
            / self.user_id
            / self.conversation_id
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append(self, event: Dict[str, Any]) -> None:
        event.setdefault("ts", self._now_ts())
        with self._lock:
            self._events.append(event)

    def _flush_text_buffer(self) -> None:
        """Flush accumulated text delta to events (call with lock held or after buffer check)."""
        if self._text_buffer:
            with self._lock:
                if self._text_buffer:
                    self._events.append({
                        "type": "text_delta",
                        "ts": (self._text_buffer_start or datetime.now(timezone.utc)).isoformat(),
                        "text": self._text_buffer,
                    })
                    self._text_buffer = ""
                    self._text_buffer_start = None

    # ------------------------------------------------------------------
    # Logging methods
    # ------------------------------------------------------------------

    def log_request(
        self,
        method: str,
        path: str,
        model: str,
        content: str,
        skill_slug: str = "",
    ) -> None:
        self._append({
            "type": "request",
            "method": method,
            "path": path,
            "model_requested": model,
            "content": content[:500],  # truncate very long prompts in header
            "content_len": len(content),
            "skill_slug": skill_slug,
        })

    def log_model_resolved(self, model: str) -> None:
        self.model = model
        self._append({"type": "model_resolved", "model": model})

    def log_system_prompt(self, prompt: str) -> None:
        self._append({
            "type": "system_prompt",
            "prompt": prompt,
            "length": len(prompt),
        })

    def log_messages(self, messages: List[Dict]) -> None:
        """Log the full message array fed to the LLM."""
        summaries = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, str):
                length = len(content)
                preview = content[:200]
            elif isinstance(content, list):
                length = sum(
                    len(b.get("text", "") if isinstance(b, dict) else str(b))
                    for b in content
                )
                preview = f"[{len(content)} blocks]"
            else:
                length = len(str(content))
                preview = str(content)[:200]
            summaries.append({
                "index": i,
                "role": role,
                "length": length,
                "preview": preview,
            })
        self._append({
            "type": "messages",
            "count": len(messages),
            "messages": summaries,
            # also store the full payload for JSON download
            "full_messages": messages,
        })

    def log_text_delta(self, text: str) -> None:
        """Buffer text deltas; flush when buffer exceeds threshold."""
        if not text:
            return
        if self._text_buffer_start is None:
            self._text_buffer_start = datetime.now(timezone.utc)
        self._text_buffer += text
        if len(self._text_buffer) >= self._TEXT_FLUSH_SIZE:
            self._flush_text_buffer()

    def log_tool_call_start(
        self,
        tool_call_id: str,
        tool_name: str,
        tool_input: Any,
    ) -> None:
        self._flush_text_buffer()
        self._append({
            "type": "tool_call_start",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "input": tool_input,
        })

    def log_tool_call_end(
        self,
        tool_name: str,
        output: Any,
        duration_ms: float,
    ) -> None:
        self._append({
            "type": "tool_call_end",
            "tool_name": tool_name,
            "output": output,
            "duration_ms": duration_ms,
        })

    def log_sandbox_exec(
        self,
        language: str,
        code: str,
        stdout: str,
        stderr: str,
        exit_code: int,
        duration_ms: float,
    ) -> None:
        self._append({
            "type": "sandbox_exec",
            "language": language,
            "code": code,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
        })

    def log_skill_invocation(self, skill_slug: str, context: Any = None) -> None:
        self._append({
            "type": "skill_invocation",
            "skill_slug": skill_slug,
            "context": context,
        })

    def log_iteration(
        self,
        iteration: int,
        duration_ms: float,
        usage: Optional[Dict] = None,
    ) -> None:
        self._flush_text_buffer()
        self._append({
            "type": "iteration",
            "iteration": iteration,
            "duration_ms": duration_ms,
            "usage": usage or {},
        })

    def log_final_response(
        self,
        content: str,
        tools_used: List,
        total_usage: Optional[Dict] = None,
        iterations: int = 0,
    ) -> None:
        self._flush_text_buffer()
        self._append({
            "type": "final_response",
            "content": content,
            "content_length": len(content),
            "tools_used": [
                t.get("tool") if isinstance(t, dict) else str(t) for t in tools_used
            ],
            "total_usage": total_usage or {},
            "iterations": iterations,
        })

    def log_error(self, error_type: str, message: str) -> None:
        self._flush_text_buffer()
        self._append({
            "type": "error",
            "error_type": error_type,
            "message": message,
        })

    def log_custom(self, label: str, data: Any) -> None:
        self._append({"type": "custom", "label": label, "data": data})

    # ------------------------------------------------------------------
    # Finalize & write
    # ------------------------------------------------------------------

    def finalize(self) -> None:
        """Mark the transcript as finished."""
        self._flush_text_buffer()
        self.finished_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Return full transcript as a JSON-serializable dict."""
        self.finalize()
        started = self.started_at
        finished = self.finished_at or datetime.now(timezone.utc)
        duration_ms = round((finished - started).total_seconds() * 1000, 2)
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "model": self.model,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_ms": duration_ms,
            "event_count": len(self._events),
            "has_error": any(e.get("type") == "error" for e in self._events),
            "events": self._events,
        }

    def to_text(self) -> str:
        """Return a human-readable transcript."""
        self.finalize()
        started = self.started_at
        finished = self.finished_at or datetime.now(timezone.utc)
        duration_ms = round((finished - started).total_seconds() * 1000, 2)

        lines: List[str] = []
        SEP = "=" * 60

        lines.append(SEP)
        lines.append("DEBUG TRANSCRIPT")
        lines.append(f"Request ID  : {self.request_id}")
        lines.append(f"User        : {self.user_id}")
        lines.append(f"Conversation: {self.conversation_id}")
        lines.append(f"Started     : {started.isoformat()}")
        lines.append(SEP)
        lines.append("")

        for ev in self._events:
            ev_type = ev.get("type", "unknown")
            ts_raw = ev.get("ts", "")
            # Format: [HH:MM:SS.mmm]
            try:
                ts_dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                ts_label = ts_dt.strftime("%H:%M:%S.") + f"{ts_dt.microsecond // 1000:03d}"
            except Exception:
                ts_label = ts_raw[:19]

            if ev_type == "request":
                lines.append(f"[{ts_label}] REQUEST")
                lines.append(f"  Method: {ev.get('method')} {ev.get('path')}")
                lines.append(f"  Model requested: {ev.get('model_requested')}")
                if ev.get("skill_slug"):
                    lines.append(f"  Skill: {ev.get('skill_slug')}")
                lines.append(f"  Content ({ev.get('content_len', 0)} chars): {ev.get('content', '')[:300]}")

            elif ev_type == "model_resolved":
                lines.append(f"[{ts_label}] MODEL_RESOLVED")
                lines.append(f"  Model: {ev.get('model')}")

            elif ev_type == "system_prompt":
                prompt = ev.get("prompt", "")
                lines.append(f"[{ts_label}] SYSTEM_PROMPT ({ev.get('length', len(prompt))} chars)")
                lines.append(f"  {prompt[:500]}{'...' if len(prompt) > 500 else ''}")

            elif ev_type == "messages":
                lines.append(f"[{ts_label}] MESSAGES ({ev.get('count', 0)} messages)")
                for m in ev.get("messages", []):
                    lines.append(f"  [{m['index']}] {m['role']}: ({m['length']} chars) {m['preview'][:120]}")

            elif ev_type == "text_delta":
                text = ev.get("text", "")
                lines.append(f"[{ts_label}] TEXT_DELTA ({len(text)} chars)")
                lines.append(f"  {text[:400]}{'...' if len(text) > 400 else ''}")

            elif ev_type == "tool_call_start":
                inp = ev.get("input", {})
                inp_str = json.dumps(inp, indent=2, default=str) if isinstance(inp, dict) else str(inp)
                lines.append(f"[{ts_label}] TOOL_CALL_START")
                lines.append(f"  Tool: {ev.get('tool_name')}  (id: {ev.get('tool_call_id', '')})")
                lines.append("  Input:")
                for ln in inp_str.splitlines():
                    lines.append(f"    {ln}")

            elif ev_type == "tool_call_end":
                out = ev.get("output", {})
                out_str = json.dumps(out, indent=2, default=str) if isinstance(out, (dict, list)) else str(out)
                lines.append(f"[{ts_label}] TOOL_CALL_END")
                lines.append(f"  Tool: {ev.get('tool_name')}  ({ev.get('duration_ms', 0):.2f} ms)")
                lines.append("  Output:")
                for ln in out_str[:2000].splitlines():
                    lines.append(f"    {ln}")
                if len(out_str) > 2000:
                    lines.append("    ... (truncated)")

            elif ev_type == "sandbox_exec":
                code = ev.get("code", "")
                stdout = ev.get("stdout", "") or ""
                stderr = ev.get("stderr", "") or ""
                lines.append(f"[{ts_label}] SANDBOX_EXEC  [{ev.get('language')}]  ({ev.get('duration_ms', 0):.2f} ms)")
                lines.append(f"  Code ({len(code)} chars):")
                for ln in code[:1500].splitlines():
                    lines.append(f"    {ln}")
                if len(code) > 1500:
                    lines.append("    ... (truncated)")
                lines.append(f"  STDOUT:")
                if stdout.strip():
                    for ln in stdout[:1000].splitlines():
                        lines.append(f"    {ln}")
                else:
                    lines.append("    (none)")
                lines.append(f"  STDERR:")
                if stderr.strip():
                    for ln in stderr[:500].splitlines():
                        lines.append(f"    {ln}")
                else:
                    lines.append("    (none)")
                lines.append(f"  Exit Code: {ev.get('exit_code', '?')}")

            elif ev_type == "skill_invocation":
                lines.append(f"[{ts_label}] SKILL_INVOCATION")
                lines.append(f"  Skill: {ev.get('skill_slug')}")

            elif ev_type == "iteration":
                usage = ev.get("usage") or {}
                lines.append(f"[{ts_label}] ITERATION {ev.get('iteration')}  ({ev.get('duration_ms', 0):.2f} ms)")
                if usage:
                    lines.append(f"  Input tokens : {usage.get('input_tokens', '?')}")
                    lines.append(f"  Output tokens: {usage.get('output_tokens', '?')}")
                    total = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
                    lines.append(f"  Total tokens : {total}")

            elif ev_type == "final_response":
                content = ev.get("content", "")
                usage = ev.get("total_usage") or {}
                tools = ev.get("tools_used") or []
                lines.append(f"[{ts_label}] FINAL RESPONSE")
                lines.append(f"  Iterations  : {ev.get('iterations', 0)}")
                if usage:
                    total = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
                    lines.append(f"  Total tokens: {total}  (in={usage.get('input_tokens', '?')}, out={usage.get('output_tokens', '?')})")
                if tools:
                    lines.append(f"  Tools used  : {', '.join(str(t) for t in tools)}")
                lines.append(f"  Content ({len(content)} chars):")
                lines.append(f"  {content[:600]}{'...' if len(content) > 600 else ''}")

            elif ev_type == "error":
                lines.append(f"[{ts_label}] *** ERROR: {ev.get('error_type')} ***")
                lines.append(f"  {ev.get('message', '')[:500]}")

            elif ev_type == "custom":
                lines.append(f"[{ts_label}] CUSTOM: {ev.get('label')}")
                lines.append(f"  {str(ev.get('data', ''))[:300]}")

            else:
                lines.append(f"[{ts_label}] {ev_type.upper()}")
                lines.append(f"  {json.dumps(ev, default=str)[:300]}")

            lines.append("")

        lines.append(SEP)
        lines.append(f"FINISHED: {finished.isoformat()}  (duration: {duration_ms:.2f} ms)")
        lines.append(SEP)

        return "\n".join(lines)

    def write(self) -> None:
        """Write .json and .txt transcript files to disk. Silently ignores errors."""
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            json_path = self._base_dir / f"{self.request_id}.json"
            txt_path  = self._base_dir / f"{self.request_id}.txt"

            data = self.to_dict()
            json_path.write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8"
            )
            txt_path.write_text(self.to_text(), encoding="utf-8")
            logger.debug(
                "Debug transcript written: %s  (%d events)",
                self.request_id,
                len(self._events),
            )
        except Exception as exc:
            # Never let debug code crash production
            logger.warning("Failed to write debug transcript: %s", exc)


# ---------------------------------------------------------------------------
# Listing & pruning helpers
# ---------------------------------------------------------------------------

def list_transcripts(
    storage_root: str,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    List transcript metadata from disk.

    Scans $storage_root/debug_transcripts/<user_id>/<conv_id>/*.json
    Returns list of dicts sorted by started_at descending.
    """
    base = Path(storage_root) / "debug_transcripts"
    if not base.exists():
        return []

    results: List[Dict[str, Any]] = []

    # Determine which user dirs to scan
    if user_id:
        user_dirs = [base / user_id] if (base / user_id).is_dir() else []
    else:
        user_dirs = [d for d in base.iterdir() if d.is_dir()]

    for ud in user_dirs:
        uid = ud.name
        # Determine which conversation dirs to scan
        if conversation_id:
            conv_dirs = [ud / conversation_id] if (ud / conversation_id).is_dir() else []
        else:
            conv_dirs = [d for d in ud.iterdir() if d.is_dir()]

        for cd in conv_dirs:
            cid = cd.name
            for jf in cd.glob("*.json"):
                try:
                    raw = json.loads(jf.read_text(encoding="utf-8"))
                    txt_path = jf.with_suffix(".txt")
                    results.append({
                        "request_id": raw.get("request_id", jf.stem),
                        "user_id": raw.get("user_id", uid),
                        "conversation_id": raw.get("conversation_id", cid),
                        "model": raw.get("model", ""),
                        "started_at": raw.get("started_at", ""),
                        "finished_at": raw.get("finished_at", ""),
                        "duration_ms": raw.get("duration_ms", 0),
                        "event_count": raw.get("event_count", 0),
                        "has_error": raw.get("has_error", False),
                        "json_path": str(jf),
                        "txt_path": str(txt_path) if txt_path.exists() else None,
                    })
                except Exception:
                    pass

    results.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return results[:limit]


def prune_old_transcripts(storage_root: str, max_age_days: int = 7) -> int:
    """
    Delete transcript files older than max_age_days.
    Returns the number of files deleted.
    """
    base = Path(storage_root) / "debug_transcripts"
    if not base.exists():
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    deleted = 0

    for json_file in base.rglob("*.json"):
        try:
            if json_file.stat().st_mtime < cutoff:
                txt_file = json_file.with_suffix(".txt")
                json_file.unlink(missing_ok=True)
                txt_file.unlink(missing_ok=True)
                deleted += 2 if txt_file.exists() else 1
        except Exception:
            pass

    return deleted
