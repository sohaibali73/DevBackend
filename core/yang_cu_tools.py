"""
core.yang_cu_tools
==================

Phase 1 + 2 of YANG Autopilot: **Background Computer Use**.

The Electron client now ships three parallel control surfaces:

* ``browser``           — headless Chromium driven via Playwright.
* ``native``            — Windows app driven via UI Automation (does NOT move
                          the user's real cursor or steal focus).
* ``virtual-desktop``   — Windows app placed on a secondary virtual desktop
                          so the user's primary desktop stays untouched.

Execution stays on the client. This module only declares schemas + names so
the Claude agent loop can short-circuit these tool calls and route them to
the client (identical pause/resume mechanism as :mod:`core.desktop_tools`).

Gated by the capability flag ``"yang_cu"`` in ``ClientEnvelope.capabilities``.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Re-use the schema-flattening helpers from the desktop tools module so the
# Anthropic ``input_schema`` is built identically (no $ref, no $defs cruft).
from core.desktop_tools import _schema, _tool  # type: ignore[attr-defined]


# ────────────────────────────────────────────────────────────────────────────
# Target lifecycle
# ────────────────────────────────────────────────────────────────────────────

class CuOpenTarget(BaseModel):
    """Open a new control surface for the AI."""
    kind: Literal["browser", "native", "virtual-desktop"]
    url: Optional[str] = None            # required when kind == 'browser'
    app: Optional[str] = None            # path or name when kind in ('native','virtual-desktop')
    args: Optional[list[str]] = None
    windowTitle: Optional[str] = None    # attach to existing window by title (native/vd)


class TargetId(BaseModel):
    targetId: str


class _Empty(BaseModel):
    """No-argument tool — Anthropic requires ``{"type":"object","properties":{}}``."""
    pass


# ────────────────────────────────────────────────────────────────────────────
# Input / interaction
# ────────────────────────────────────────────────────────────────────────────

class CuXY(BaseModel):
    targetId: str
    x: int
    y: int
    button: Optional[Literal["left", "right", "middle"]] = "left"


class CuType(BaseModel):
    targetId: str
    text: str
    delayMs: Optional[int] = None


class CuKey(BaseModel):
    targetId: str
    combo: str


class CuScroll(BaseModel):
    targetId: str
    x: int
    y: int
    dx: int
    dy: int


# ────────────────────────────────────────────────────────────────────────────
# Browser-only convenience
# ────────────────────────────────────────────────────────────────────────────

class BrowserNavigate(BaseModel):
    targetId: str
    url: str


class BrowserEval(BaseModel):
    targetId: str
    script: str


class BrowserPinNote(BaseModel):
    targetId: str
    x: int
    y: int
    text: str


class BrowserFill(BaseModel):
    targetId: str
    selector: str
    value: str


class BrowserWaitFor(BaseModel):
    targetId: str
    selector: str
    timeoutMs: Optional[int] = 15000


class BrowserDownload(BaseModel):
    targetId: str
    url: str
    filename: Optional[str] = None


# ────────────────────────────────────────────────────────────────────────────
# Canonical tool-name set (kept in lock-step with the client bridge)
# ────────────────────────────────────────────────────────────────────────────

YANG_CU_TOOL_NAMES: frozenset[str] = frozenset({
    # Target lifecycle / observation
    "cu_open_target", "cu_close", "cu_list_targets",
    "cu_screenshot", "cu_get_content", "cu_size",
    # Input
    "cu_click", "cu_double_click", "cu_type", "cu_key", "cu_scroll",
    # Browser-only
    "browser_navigate", "browser_eval", "browser_pin_note", "browser_get_pins",
    "browser_fill", "browser_wait_for", "browser_download", "browser_list_downloads",
})


# ────────────────────────────────────────────────────────────────────────────
# Anthropic-shape tool definitions
# ────────────────────────────────────────────────────────────────────────────

def yang_cu_tools_for(caps: list[str] | tuple[str, ...] | None) -> list[dict[str, Any]]:
    """
    Return the Anthropic-shape tool list for the ``yang_cu`` capability.

    Returns ``[]`` when ``caps`` is empty/None or does not contain ``"yang_cu"``.
    """
    if not caps:
        return []
    if "yang_cu" not in set(caps):
        return []

    return [
        _tool(
            "cu_open_target",
            (
                "Open a new control surface. kind='browser' for a parallel "
                "headless Chromium tab (use this for web pages, app testing, "
                "dev-server preview). kind='native' for a Windows native app "
                "via UI Automation (does NOT move the user's real cursor or "
                "steal focus). kind='virtual-desktop' to run a native app on "
                "a secondary virtual desktop so the user's primary desktop is "
                "untouched. Returns { id, title, kind, ... }."
            ),
            CuOpenTarget,
        ),
        _tool("cu_close",        "Close a target by id.",                                  TargetId),
        _tool("cu_list_targets", "List all currently open targets.",                       _Empty),
        _tool(
            "cu_screenshot",
            "PNG (base64) of the target. Call this BEFORE clicking/typing to "
            "ground coordinates.",
            TargetId,
        ),
        _tool(
            "cu_get_content",
            "Logical content of the target — DOM/a11y tree for browser, UIA "
            "tree for native. Use this for richer grounding than pixels.",
            TargetId,
        ),
        _tool("cu_size",         "Get target dimensions.",                                 TargetId),
        _tool(
            "cu_click",
            "Click at (x,y) inside the target. No real cursor is moved for "
            "native/virtual-desktop targets.",
            CuXY,
        ),
        _tool("cu_double_click", "Double-click at (x,y) inside the target.",               CuXY),
        _tool("cu_type",         "Type text into the focused field of the target.",        CuType),
        _tool("cu_key",          "Press a key combo like 'Ctrl+S' or 'Enter'.",            CuKey),
        _tool("cu_scroll",       "Scroll inside the target by (dx,dy) at (x,y).",          CuScroll),

        _tool("browser_navigate", "Navigate a browser target to a URL.",                   BrowserNavigate),
        _tool("browser_eval",     "Run JavaScript in the browser target and return its result.", BrowserEval),
        _tool(
            "browser_pin_note",
            "Drop a user-comment pin (the AI uses this to surface "
            "'fix this here' feedback the human added).",
            BrowserPinNote,
        ),
        _tool("browser_get_pins", "Read any pinned user notes attached to a browser target.", TargetId),
        _tool(
            "browser_fill",
            "Fill an <input>/<textarea> by CSS selector (more reliable than coordinate typing).",
            BrowserFill,
        ),
        _tool(
            "browser_wait_for",
            "Wait for a CSS selector to appear in the browser target (default 15s timeout).",
            BrowserWaitFor,
        ),
        _tool(
            "browser_download",
            "Download a URL through the browser's session (cookies/auth carry over) "
            "and save it to the user's <workspace>/Downloads/ folder. Returns the local path.",
            BrowserDownload,
        ),
        _tool(
            "browser_list_downloads",
            "List all files downloaded by this browser session.",
            TargetId,
        ),
    ]


# ────────────────────────────────────────────────────────────────────────────
# System-prompt augmentation
# ────────────────────────────────────────────────────────────────────────────

_YANG_CU_SYSTEM_BLOCK = """\
## YANG AUTOPILOT — Background Computer Use

You have three parallel control surfaces. Open targets with cu_open_target:
  - kind='browser'           — parallel headless Chromium (Playwright). Use for
                                web pages, app testing, dev-server preview.
  - kind='native'            — Windows app via UI Automation (does NOT move
                                the user's real cursor or steal focus).
  - kind='virtual-desktop'   — Windows app placed on a secondary virtual
                                desktop, fully isolated from the user.

Workflow:
  1. cu_open_target → keep the returned `id`.
  2. cu_screenshot(id) — ALWAYS look before you touch.
  3. cu_click / cu_type / cu_key / cu_scroll with coordinates relative to the
     screenshot you just took.
  4. cu_get_content for richer grounding (a11y tree or DOM).
  5. cu_close(id) when done.

Notes:
  - When the user has dropped pin-comments on a browser target,
    browser_get_pins returns them — act on those as priority feedback.
  - You can have multiple targets open simultaneously.
  - For long-running tasks the user can press Ctrl+Shift+Esc to kill
    everything.
  - Prefer cu_* tools over the global computer_* tools whenever the user
    asks you to do something "in the background" or in a web page — the
    cu_* tools do not interfere with the user's foreground work.
"""


def build_yang_cu_system_block(caps: list[str] | tuple[str, ...] | None) -> str:
    """
    Returns the YANG Autopilot system-prompt block when ``"yang_cu"`` is in
    the advertised capabilities, otherwise an empty string.
    """
    if not caps:
        return ""
    if "yang_cu" not in set(caps):
        return ""
    return _YANG_CU_SYSTEM_BLOCK
