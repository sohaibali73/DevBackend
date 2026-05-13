"""
core.desktop_tools
==================

Server-side **declarations** of the desktop-agent tools.

The Electron client executes the actual filesystem / shell / computer-use
operations. This module only:

* Declares JSON schemas (via Pydantic) for each tool's input.
* Exposes :data:`DESKTOP_TOOL_NAMES` so the Claude agent loop can short-circuit
  these tool calls instead of running them server-side.
* Builds the Anthropic-shape tool definitions
  (``{"name", "description", "input_schema"}``) the model needs to know
  about, gated by the capabilities the client advertised in
  ``ClientEnvelope.capabilities``.
* Builds the system-prompt augmentation injected when ``client.kind ==
  "desktop"`` (recipe §6).

The canonical tool names match the ones the client recognises in
``src/lib/desktop/bridge.ts → DESKTOP_TOOL_NAMES``.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ────────────────────────────────────────────────────────────────────────────
# Filesystem
# ────────────────────────────────────────────────────────────────────────────

class FsRead(BaseModel):
    path: str
    encoding: Optional[str] = "utf-8"


class FsWrite(BaseModel):
    path: str
    content: str
    encoding: Optional[str] = "utf-8"
    createDirs: Optional[bool] = True


class FsAppend(BaseModel):
    path: str
    content: str


class FsPath(BaseModel):
    path: str


class FsList(BaseModel):
    path: str
    recursive: Optional[bool] = False
    maxEntries: Optional[int] = 1000


class FsMoveCopy(BaseModel):
    src: str
    dest: str


class FsPickFile(BaseModel):
    multi: Optional[bool] = False


class _Empty(BaseModel):
    """No-argument tool — Anthropic requires ``{"type":"object","properties":{}}``."""
    pass


# ────────────────────────────────────────────────────────────────────────────
# Shell
# ────────────────────────────────────────────────────────────────────────────

class ShellRun(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    cwd: Optional[str] = None
    env: Optional[dict[str, str]] = None
    timeoutMs: Optional[int] = None
    shell: Optional[bool] = False


class ShellOpen(BaseModel):
    target: str  # path or URL


# ────────────────────────────────────────────────────────────────────────────
# Computer use
# ────────────────────────────────────────────────────────────────────────────

class ComputerScreenshot(BaseModel):
    displayIndex: Optional[int] = 0


class ComputerXY(BaseModel):
    x: int
    y: int
    speed: Optional[int] = None


class ComputerClick(BaseModel):
    x: Optional[int] = None
    y: Optional[int] = None
    button: Optional[Literal["left", "right", "middle"]] = "left"


class ComputerXYOpt(BaseModel):
    x: Optional[int] = None
    y: Optional[int] = None


class _DragPoint(BaseModel):
    x: int
    y: int


class ComputerDrag(BaseModel):
    # ``from`` is a Python keyword, so use an alias.
    model_config = ConfigDict(populate_by_name=True)

    from_: _DragPoint = Field(alias="from")
    to: _DragPoint


class ComputerScroll(BaseModel):
    direction: Literal["up", "down", "left", "right"]
    amount: int


class ComputerType(BaseModel):
    text: str
    delayMs: Optional[int] = None


class ComputerKey(BaseModel):
    combo: str


# ────────────────────────────────────────────────────────────────────────────
# Canonical tool-name set (kept in lock-step with the client bridge)
# ────────────────────────────────────────────────────────────────────────────

DESKTOP_TOOL_NAMES: frozenset[str] = frozenset({
    # Filesystem
    "fs_read_file", "fs_write_file", "fs_append_file", "fs_delete",
    "fs_list_dir", "fs_stat", "fs_move", "fs_copy", "fs_mkdir",
    "fs_pick_file", "fs_pick_folder",
    # Shell
    "shell_run", "shell_open",
    # Computer use
    "computer_screenshot", "computer_screen_size", "computer_cursor_position",
    "computer_move", "computer_click", "computer_double_click",
    "computer_right_click", "computer_drag", "computer_scroll",
    "computer_type", "computer_key",
})


# ────────────────────────────────────────────────────────────────────────────
# Anthropic-shape tool definitions
# ────────────────────────────────────────────────────────────────────────────

def _schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """
    Strip Pydantic's ``$defs`` / ``title`` cruft and return a clean JSON-schema
    object suitable for Anthropic's ``input_schema`` field.

    Anthropic only requires ``{"type":"object","properties":{...},"required":[...]}``
    so we keep things minimal and predictable.
    """
    raw = model_cls.model_json_schema()
    out: dict[str, Any] = {
        "type": "object",
        "properties": raw.get("properties", {}) or {},
    }
    if raw.get("required"):
        out["required"] = raw["required"]
    # Inline any $defs so the schema is self-contained — Anthropic chokes
    # on $ref to local $defs.
    defs = raw.get("$defs") or raw.get("definitions") or {}
    if defs and out["properties"]:
        out["properties"] = _inline_refs(out["properties"], defs)
    return out


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Recursively replace ``{"$ref": "#/$defs/Foo"}`` with the actual definition."""
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str):
            ref = node["$ref"]
            # Supports "#/$defs/Foo" and "#/definitions/Foo"
            name = ref.rsplit("/", 1)[-1]
            target = defs.get(name)
            if isinstance(target, dict):
                # Merge in sibling keys (e.g. "description") on top of the
                # resolved definition.
                merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
                return _inline_refs(merged, defs)
        return {k: _inline_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def _tool(name: str, description: str, model_cls: type[BaseModel]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": _schema(model_cls),
    }


def desktop_tools_for(caps: list[str] | tuple[str, ...] | None) -> list[dict[str, Any]]:
    """
    Build the list of Anthropic-shape tool definitions for the capabilities the
    desktop client advertised. Returns ``[]`` when ``caps`` is empty/None, so
    web users see no behavior change.
    """
    if not caps:
        return []
    caps_set = set(caps)
    tools: list[dict[str, Any]] = []

    # ── Filesystem ───────────────────────────────────────────────────────
    if "fs" in caps_set:
        tools += [
            _tool("fs_read_file",
                  "Read a text file from the user's machine.",
                  FsRead),
            _tool("fs_write_file",
                  "Write a text file. Creates parent dirs by default.",
                  FsWrite),
            _tool("fs_append_file",
                  "Append to a text file.",
                  FsAppend),
            _tool("fs_delete",
                  "Delete a file or folder recursively.",
                  FsPath),
            _tool("fs_list_dir",
                  "List a directory. Set recursive=true for a tree.",
                  FsList),
            _tool("fs_stat",
                  "Stat a file/folder.",
                  FsPath),
            _tool("fs_move",
                  "Move/rename a file or folder.",
                  FsMoveCopy),
            _tool("fs_copy",
                  "Copy a file or folder (recursive for folders).",
                  FsMoveCopy),
            _tool("fs_mkdir",
                  "Create a directory (recursive).",
                  FsPath),
            _tool("fs_pick_file",
                  "Ask the user to pick a file via the OS dialog. "
                  "Use this to access paths outside the workspace.",
                  FsPickFile),
            _tool("fs_pick_folder",
                  "Ask the user to pick a folder and grant access to it.",
                  _Empty),
        ]

    # ── Shell ────────────────────────────────────────────────────────────
    if "shell" in caps_set:
        tools += [
            _tool("shell_run",
                  "Run any shell command and return stdout/stderr/exitCode.",
                  ShellRun),
            _tool("shell_open",
                  "Open a path or URL with the OS default handler.",
                  ShellOpen),
        ]

    # ── Computer use ─────────────────────────────────────────────────────
    if "computer" in caps_set:
        tools += [
            _tool("computer_screenshot",
                  "Capture a full-screen PNG (base64) of the user's primary display. "
                  "Call this BEFORE clicking to ground your coordinates.",
                  ComputerScreenshot),
            _tool("computer_screen_size",
                  "Get screen dimensions.",
                  _Empty),
            _tool("computer_cursor_position",
                  "Where the cursor currently is.",
                  _Empty),
            _tool("computer_move",
                  "Move the mouse to (x,y).",
                  ComputerXY),
            _tool("computer_click",
                  "Click; optionally move to (x,y) first.",
                  ComputerClick),
            _tool("computer_double_click",
                  "Double-click.",
                  ComputerXYOpt),
            _tool("computer_right_click",
                  "Right-click.",
                  ComputerXYOpt),
            _tool("computer_drag",
                  "Drag from one point to another.",
                  ComputerDrag),
            _tool("computer_scroll",
                  "Scroll in a direction.",
                  ComputerScroll),
            _tool("computer_type",
                  "Type a string at the cursor.",
                  ComputerType),
            _tool("computer_key",
                  "Press a key combo like 'Ctrl+Shift+T' or 'Enter'.",
                  ComputerKey),
        ]

    return tools


# ────────────────────────────────────────────────────────────────────────────
# System-prompt augmentation
# ────────────────────────────────────────────────────────────────────────────

_DESKTOP_SYSTEM_TEMPLATE = """\
## Desktop access (this user is on the Potomac desktop app)

You have access to the user's desktop through a set of tools that execute on
THEIR machine (not yours). The Potomac Workspace lives at ~/PotomacWorkspace
and is the default place to put files. Use fs_pick_file or fs_pick_folder to
gain access to paths outside the workspace.

Rules:
- Before any computer_click / computer_type, call computer_screenshot first.
- Prefer non-destructive shell commands. Destructive commands outside the
  workspace will prompt the user for approval.
- Never store secrets or credentials in files.
- If a tool returns {"error": "..."}, do not retry the same call blindly.
- If a tool is denied, explain that and offer the user a different path
  (e.g. fs_pick_folder).

Capabilities available this session: {caps}
"""


def build_desktop_system_block(caps: list[str] | tuple[str, ...] | None) -> str:
    """
    Returns the system-prompt block to append when the request comes from the
    desktop client. Returns an empty string if no desktop capabilities were
    advertised (so the agent loop can safely concatenate the result).
    """
    if not caps:
        return ""
    # NOTE: ``str.format`` would choke on the literal ``{"error": "..."}``
    # JSON example inside the template (interprets it as a named field and
    # raises ``KeyError: '"error"'``). Use a plain string replacement so the
    # template can contain arbitrary JSON snippets safely.
    return _DESKTOP_SYSTEM_TEMPLATE.replace(
        "{caps}", ", ".join(sorted(set(caps)))
    )
