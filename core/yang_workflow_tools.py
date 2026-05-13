"""
core.yang_workflow_tools
========================

YANG Autopilot — Phase 5 (Developer Workflow) tools.

Adds three new client-executed tool families gated by the ``"yang_workflow"``
capability flag:

* ``terminal_*`` — interactive terminal sessions (open/list/write/read/close).
* ``github_*``   — git + GitHub operations (clone / commit / push / PR …).
* ``ssh_*``      — remote SSH sessions (open/exec/upload/download/close).

The server **only declares schemas**. Execution lives on the Electron client
and the result is routed back via the same pause/resume mechanism as
:mod:`core.desktop_tools` and :mod:`core.yang_cu_tools`.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel

# Re-use the helpers from desktop_tools so every Anthropic input_schema is
# flattened identically (no $ref / $defs cruft).
from core.desktop_tools import _tool  # type: ignore[attr-defined]


# ────────────────────────────────────────────────────────────────────────────
# Terminal
# ────────────────────────────────────────────────────────────────────────────

class TerminalOpen(BaseModel):
    cwd: Optional[str] = None
    shell: Optional[str] = None     # 'powershell' | 'cmd' | 'bash' …
    cols: Optional[int] = None
    rows: Optional[int] = None
    env: Optional[dict[str, str]] = None


class TerminalId(BaseModel):
    terminalId: str


class TerminalWrite(BaseModel):
    terminalId: str
    data: str                       # raw bytes to send to stdin (include "\n" to submit)


class TerminalRead(BaseModel):
    terminalId: str
    sinceCursor: Optional[int] = None  # opaque cursor returned by previous read
    waitMs: Optional[int] = None       # block up to N ms for new output


class TerminalResize(BaseModel):
    terminalId: str
    cols: int
    rows: int


# ────────────────────────────────────────────────────────────────────────────
# GitHub / Git
# ────────────────────────────────────────────────────────────────────────────

class GithubClone(BaseModel):
    repo: str                       # 'owner/name' or full URL
    dest: Optional[str] = None
    branch: Optional[str] = None
    depth: Optional[int] = None


class GithubRepoPath(BaseModel):
    repoPath: str


class GithubBranch(BaseModel):
    repoPath: str
    name: Optional[str] = None      # omit → list branches
    checkout: Optional[bool] = False
    create: Optional[bool] = False


class GithubCommit(BaseModel):
    repoPath: str
    message: str
    addAll: Optional[bool] = True
    paths: Optional[list[str]] = None


class GithubPush(BaseModel):
    repoPath: str
    remote: Optional[str] = "origin"
    branch: Optional[str] = None
    setUpstream: Optional[bool] = False


class GithubPull(BaseModel):
    repoPath: str
    remote: Optional[str] = "origin"
    branch: Optional[str] = None
    rebase: Optional[bool] = False


class GithubPullRequest(BaseModel):
    repoPath: str
    title: str
    body: Optional[str] = None
    base: Optional[str] = "main"
    head: Optional[str] = None
    draft: Optional[bool] = False


class GithubDiff(BaseModel):
    repoPath: str
    ref: Optional[str] = None       # 'HEAD~1' / 'main' / commit sha


# ────────────────────────────────────────────────────────────────────────────
# SSH
# ────────────────────────────────────────────────────────────────────────────

class SshOpen(BaseModel):
    host: str
    port: Optional[int] = 22
    user: Optional[str] = None
    keyPath: Optional[str] = None
    password: Optional[str] = None  # avoid; prefer keyPath
    knownHostsPolicy: Optional[Literal["strict", "accept-new", "off"]] = "accept-new"


class SshSessionId(BaseModel):
    sessionId: str


class SshExec(BaseModel):
    sessionId: str
    command: str
    timeoutMs: Optional[int] = None


class SshTransfer(BaseModel):
    sessionId: str
    localPath: str
    remotePath: str
    recursive: Optional[bool] = False


# ────────────────────────────────────────────────────────────────────────────
# Canonical tool-name set
# ────────────────────────────────────────────────────────────────────────────

YANG_WORKFLOW_TOOL_NAMES: frozenset[str] = frozenset({
    # Terminal
    "terminal_open", "terminal_list", "terminal_write", "terminal_read",
    "terminal_resize", "terminal_close",
    # GitHub / Git
    "github_clone", "github_status", "github_branch", "github_commit",
    "github_push", "github_pull", "github_pull_request", "github_diff",
    "github_log",
    # SSH
    "ssh_open", "ssh_exec", "ssh_upload", "ssh_download", "ssh_close",
    "ssh_list",
})


# ────────────────────────────────────────────────────────────────────────────
# Anthropic-shape tool definitions
# ────────────────────────────────────────────────────────────────────────────

def yang_workflow_tools_for(caps: list[str] | tuple[str, ...] | None) -> list[dict[str, Any]]:
    """
    Return the Anthropic-shape tool list for the ``yang_workflow`` capability.
    Returns ``[]`` when the capability is absent or ``caps`` is empty.
    """
    if not caps or "yang_workflow" not in set(caps):
        return []
    return [
        # ── Terminal ────────────────────────────────────────────────────────
        _tool("terminal_open",
              "Open an interactive PTY session. Returns { terminalId, … }.",
              TerminalOpen),
        _tool("terminal_list",
              "List currently open terminal sessions for this user.",
              type("_Empty", (BaseModel,), {})),
        _tool("terminal_write",
              "Send raw bytes to a terminal's stdin. Append '\\n' to submit a command.",
              TerminalWrite),
        _tool("terminal_read",
              "Read accumulated output from a terminal. Use sinceCursor to page.",
              TerminalRead),
        _tool("terminal_resize",
              "Resize a terminal's PTY (cols/rows).",
              TerminalResize),
        _tool("terminal_close",
              "Close a terminal session.",
              TerminalId),

        # ── GitHub / Git ────────────────────────────────────────────────────
        _tool("github_clone",
              "Clone a GitHub repo to a local path.",
              GithubClone),
        _tool("github_status",
              "git status for the given local repo path.",
              GithubRepoPath),
        _tool("github_branch",
              "List/create/checkout a branch (omit name to list).",
              GithubBranch),
        _tool("github_commit",
              "Stage and commit changes with a message.",
              GithubCommit),
        _tool("github_push",
              "Push to a remote.",
              GithubPush),
        _tool("github_pull",
              "Pull from a remote (optionally rebase).",
              GithubPull),
        _tool("github_pull_request",
              "Open a GitHub pull request (uses the user's gh credentials).",
              GithubPullRequest),
        _tool("github_diff",
              "Get the unified diff relative to ref (default HEAD).",
              GithubDiff),
        _tool("github_log",
              "Get the last N commits of the repo's current branch.",
              GithubRepoPath),

        # ── SSH ─────────────────────────────────────────────────────────────
        _tool("ssh_open",
              "Open an SSH session to a remote host.",
              SshOpen),
        _tool("ssh_list",
              "List currently open SSH sessions.",
              type("_Empty", (BaseModel,), {})),
        _tool("ssh_exec",
              "Run a command on the remote host and return stdout/stderr/exitCode.",
              SshExec),
        _tool("ssh_upload",
              "Upload a local file/folder to the remote host (SFTP).",
              SshTransfer),
        _tool("ssh_download",
              "Download a remote file/folder to the local machine (SFTP).",
              SshTransfer),
        _tool("ssh_close",
              "Close an SSH session.",
              SshSessionId),
    ]


# ────────────────────────────────────────────────────────────────────────────
# System-prompt augmentation
# ────────────────────────────────────────────────────────────────────────────

_YANG_WORKFLOW_SYSTEM_BLOCK = """\
## YANG AUTOPILOT — Developer Workflow

You can drive the user's developer environment via three families of tools:

* ``terminal_*`` — Open an interactive shell with terminal_open, then
  terminal_write commands and terminal_read the output.  Use terminal_close
  when finished.  Prefer non-destructive commands; ask before rm/format/etc.
* ``github_*``   — Clone, branch, commit, push, and open pull requests on the
  user's GitHub via their local ``gh`` credentials.  Always run
  github_status / github_diff before committing.
* ``ssh_*``      — Connect to remote hosts with ssh_open and run commands
  with ssh_exec.  Treat remote machines as production — be cautious.

Workflow notes:
  - Always check terminal_list / ssh_list before opening a new session.
  - Capture command exit codes and surface failures clearly.
  - Long-running commands stream output; poll terminal_read with sinceCursor.
"""


def build_yang_workflow_system_block(caps: list[str] | tuple[str, ...] | None) -> str:
    """Return the Phase-5 system block when ``yang_workflow`` is advertised."""
    if not caps or "yang_workflow" not in set(caps):
        return ""
    return _YANG_WORKFLOW_SYSTEM_BLOCK
