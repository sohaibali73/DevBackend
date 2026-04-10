"""
SessionManager
==============
Manages stateful editing sessions for iterative PPTX revision.

Each session tracks:
  - The current PPTX bytes
  - A revision history stack (undo/redo support)
  - Cached slide previews per revision
  - Applied operations log

This enables the "real-time revision loop" — the user makes multiple
edits in sequence, each one instantly updating only the changed slides,
with full undo/redo capability.

Sessions are stored on the Railway volume at:
  $STORAGE_ROOT/pptx_sessions/{session_id}/
    current.pptx        ← working copy
    history.json        ← revision metadata stack
    rev_000/            ← initial version previews
    rev_001/            ← after first revision
    rev_002/            ← after second revision
    ...

Usage
-----
    from core.vision.session_manager import SessionManager

    mgr = SessionManager()

    # Create a new session from a PPTX
    session = await mgr.create(pptx_bytes, user_id="user123",
                               source_filename="meet_potomac.pptx")

    # Apply a revision (returns diff + updated session)
    result = await mgr.apply_revision(
        session_id=session.session_id,
        instruction="Delete slide 7 and change Q1 to Q2",
        user_id="user123",
    )
    print(result.diff.modified, result.revision_id)

    # Undo the last revision
    undo_result = await mgr.undo(session.session_id, "user123")

    # List revision history
    history = await mgr.get_history(session.session_id)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/data"))
_SESSION_ROOT = _STORAGE_ROOT / "pptx_sessions"
_SESSION_ROOT.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class RevisionEntry:
    """A single revision in the session history."""
    revision_id:   str
    revision_num:  int                   # 0 = initial, 1 = first revision, ...
    instruction:   str                   # natural language instruction used
    operations:    List[Dict[str, Any]]  # typed operations applied
    summary:       str                   # human-readable summary
    pptx_filename: str                   # filename inside session dir
    diff:          Optional[Dict[str, Any]] = None  # DiffReport.to_dict()
    created_at:    float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "revision_id":   self.revision_id,
            "revision_num":  self.revision_num,
            "instruction":   self.instruction,
            "operations":    self.operations,
            "summary":       self.summary,
            "pptx_filename": self.pptx_filename,
            "diff":          self.diff,
            "created_at":    self.created_at,
        }


@dataclass
class Session:
    """A stateful PPTX editing session."""
    session_id:      str
    user_id:         str
    source_filename: str
    current_rev:     int          # index into history list
    history:         List[RevisionEntry] = field(default_factory=list)
    created_at:      float = field(default_factory=time.time)

    @property
    def current_revision(self) -> Optional[RevisionEntry]:
        if 0 <= self.current_rev < len(self.history):
            return self.history[self.current_rev]
        return None

    @property
    def can_undo(self) -> bool:
        return self.current_rev > 0

    @property
    def can_redo(self) -> bool:
        return self.current_rev < len(self.history) - 1

    @property
    def session_dir(self) -> Path:
        return _SESSION_ROOT / self.session_id

    def to_dict(self) -> Dict[str, Any]:
        rev = self.current_revision
        return {
            "session_id":      self.session_id,
            "user_id":         self.user_id,
            "source_filename": self.source_filename,
            "current_rev":     self.current_rev,
            "total_revisions": len(self.history),
            "can_undo":        self.can_undo,
            "can_redo":        self.can_redo,
            "current_instruction": rev.instruction if rev else None,
            "created_at":      self.created_at,
        }


@dataclass
class RevisionResult:
    """Result of applying a revision to a session."""
    success:     bool
    session:     Optional[Session]
    revision:    Optional[RevisionEntry]
    diff:        Optional[Any]          # DiffReport
    new_job_id:  str                    # job_id for preview URLs
    preview_urls: List[str] = field(default_factory=list)
    changed_slides: List[int] = field(default_factory=list)
    cached_slides:  List[int] = field(default_factory=list)
    error:       Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success":        self.success,
            "session":        self.session.to_dict() if self.session else None,
            "revision":       self.revision.to_dict() if self.revision else None,
            "diff":           self.diff.to_dict() if self.diff else None,
            "new_job_id":     self.new_job_id,
            "preview_urls":   self.preview_urls,
            "changed_slides": self.changed_slides,
            "cached_slides":  self.cached_slides,
            "error":          self.error,
        }


# =============================================================================
# SessionManager
# =============================================================================

class SessionManager:
    """
    Manages PPTX editing sessions with full undo/redo support.
    Sessions are persisted to disk and survive server restarts.
    """

    # ──────────────────────────────────────────────────────────────────────────
    # Create
    # ──────────────────────────────────────────────────────────────────────────

    async def create(
        self,
        pptx_bytes:       bytes,
        user_id:          str,
        source_filename:  str = "presentation.pptx",
        render_previews:  bool = True,
    ) -> Session:
        """
        Create a new editing session from a PPTX file.

        Parameters
        ----------
        pptx_bytes      : raw PPTX bytes
        user_id         : authenticated user ID
        source_filename : display name for the file
        render_previews : if True, render initial previews immediately
        """
        session_id = str(uuid.uuid4())
        session_dir = _SESSION_ROOT / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Write initial PPTX
        initial_fname = "rev_000.pptx"
        (session_dir / initial_fname).write_bytes(pptx_bytes)

        # Create initial revision entry
        initial_rev = RevisionEntry(
            revision_id="initial",
            revision_num=0,
            instruction="Initial upload",
            operations=[],
            summary=f"Uploaded {source_filename}",
            pptx_filename=initial_fname,
        )

        session = Session(
            session_id=session_id,
            user_id=user_id,
            source_filename=source_filename,
            current_rev=0,
            history=[initial_rev],
        )

        self._save_session(session)

        # Render initial previews
        if render_previews:
            await self._render_previews_for_revision(
                session_id=session_id,
                revision_num=0,
                pptx_bytes=pptx_bytes,
                prev_job_id=None,
                diff=None,
            )

        logger.info("SessionManager: created session %s for %s", session_id, user_id)
        return session

    # ──────────────────────────────────────────────────────────────────────────
    # Apply revision
    # ──────────────────────────────────────────────────────────────────────────

    async def apply_revision(
        self,
        session_id:  str,
        instruction: str,
        user_id:     str,
        operations:  Optional[List[Dict]] = None,  # pre-parsed ops (skip Claude)
    ) -> RevisionResult:
        """
        Apply a revision instruction to the current session state.

        1. Resolves instruction → operations (via RevisionEngine or pre-parsed ops)
        2. Applies operations via PptxReviser
        3. Diffs against previous version (only changed slides re-render)
        4. Updates session history (truncates redo branch if mid-stack)
        5. Returns RevisionResult with diff + preview URLs

        Parameters
        ----------
        session_id   : session to modify
        instruction  : natural language revision (e.g., "delete slide 5")
        user_id      : must match session.user_id
        operations   : optional pre-parsed operations list (skips Claude parsing)
        """
        session = self._load_session(session_id)
        if not session:
            return RevisionResult(False, None, None, None, "", error=f"Session {session_id} not found")
        if session.user_id != user_id:
            return RevisionResult(False, None, None, None, "", error="Access denied")

        current_rev = session.current_revision
        if not current_rev:
            return RevisionResult(False, None, None, None, "", error="No current revision")

        session_dir = session.session_dir
        current_pptx_bytes = (session_dir / current_rev.pptx_filename).read_bytes()

        # ── Parse instruction if operations not pre-provided ─────────────────
        from core.vision.revision_engine import RevisionEngine
        engine = RevisionEngine()

        if not operations:
            from core.vision.slide_renderer import SlideRenderer
            slide_count = SlideRenderer.get_slide_count(current_pptx_bytes)
            operations = await engine.parse_only(instruction, slide_count)

        if not operations:
            return RevisionResult(
                False, session, None, None, "",
                error="Could not parse any operations from instruction"
            )

        # ── Apply revision ────────────────────────────────────────────────────
        from core.sandbox.pptx_reviser import PptxReviser
        reviser = PptxReviser()
        new_rev_num = session.current_rev + 1
        new_pptx_fname = f"rev_{new_rev_num:03d}.pptx"

        revise_result = reviser.revise(
            pptx_bytes=current_pptx_bytes,
            revisions=operations,
            output_filename=new_pptx_fname,
        )

        if not revise_result.success or not revise_result.data:
            return RevisionResult(
                False, session, None, None, "",
                error=f"Revision failed: {revise_result.error}"
            )

        new_pptx_bytes = revise_result.data
        (session_dir / new_pptx_fname).write_bytes(new_pptx_bytes)

        # ── Diff against previous version ─────────────────────────────────────
        from core.vision.diff_engine import DiffEngine
        diff_engine = DiffEngine()
        loop = asyncio.get_event_loop()
        diff = await loop.run_in_executor(
            None,
            lambda: asyncio.run(diff_engine.diff(current_pptx_bytes, new_pptx_bytes))
            if False else None
        )
        # Direct async call (can't run asyncio.run inside running loop)
        diff = await diff_engine.diff(current_pptx_bytes, new_pptx_bytes)

        # ── Build revision entry ──────────────────────────────────────────────
        summary = engine._build_summary(operations, instruction)
        rev_entry = RevisionEntry(
            revision_id=str(uuid.uuid4()),
            revision_num=new_rev_num,
            instruction=instruction,
            operations=operations,
            summary=summary,
            pptx_filename=new_pptx_fname,
            diff=diff.to_dict(),
        )

        # Truncate redo branch (any revisions after current_rev are discarded)
        session.history = session.history[:session.current_rev + 1]
        session.history.append(rev_entry)
        session.current_rev = new_rev_num

        self._save_session(session)

        # ── Render previews (diff-aware) ──────────────────────────────────────
        prev_job_id = self._get_job_id_for_revision(session_id, current_rev.revision_num)
        new_job_id = await self._render_previews_for_revision(
            session_id=session_id,
            revision_num=new_rev_num,
            pptx_bytes=new_pptx_bytes,
            prev_job_id=prev_job_id,
            diff=diff,
        )

        preview_urls = [
            f"/pptx/preview/{new_job_id}/{i}"
            for i in range(1, diff.revised_count + 1)
        ]

        return RevisionResult(
            success=True,
            session=session,
            revision=rev_entry,
            diff=diff,
            new_job_id=new_job_id,
            preview_urls=preview_urls,
            changed_slides=diff.changed_indices,
            cached_slides=diff.unchanged,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Undo / Redo
    # ──────────────────────────────────────────────────────────────────────────

    async def undo(self, session_id: str, user_id: str) -> RevisionResult:
        """Undo the last revision and return previews for the previous state."""
        session = self._load_session(session_id)
        if not session or session.user_id != user_id:
            return RevisionResult(False, None, None, None, "", error="Session not found or access denied")
        if not session.can_undo:
            return RevisionResult(False, session, None, None, "", error="Nothing to undo")

        session.current_rev -= 1
        self._save_session(session)

        rev = session.current_revision
        session_dir = session.session_dir
        pptx_bytes = (session_dir / rev.pptx_filename).read_bytes()

        job_id = self._get_job_id_for_revision(session_id, rev.revision_num)
        if not job_id:
            job_id = await self._render_previews_for_revision(
                session_id=session_id,
                revision_num=rev.revision_num,
                pptx_bytes=pptx_bytes,
                prev_job_id=None,
                diff=None,
            )

        from core.vision.slide_renderer import SlideRenderer
        slide_count = SlideRenderer.get_slide_count(pptx_bytes)

        return RevisionResult(
            success=True,
            session=session,
            revision=rev,
            diff=None,
            new_job_id=job_id,
            preview_urls=[f"/pptx/preview/{job_id}/{i}" for i in range(1, slide_count + 1)],
        )

    async def redo(self, session_id: str, user_id: str) -> RevisionResult:
        """Redo the next revision in the stack."""
        session = self._load_session(session_id)
        if not session or session.user_id != user_id:
            return RevisionResult(False, None, None, None, "", error="Session not found or access denied")
        if not session.can_redo:
            return RevisionResult(False, session, None, None, "", error="Nothing to redo")

        session.current_rev += 1
        self._save_session(session)

        rev = session.current_revision
        session_dir = session.session_dir
        pptx_bytes = (session_dir / rev.pptx_filename).read_bytes()

        job_id = self._get_job_id_for_revision(session_id, rev.revision_num)
        if not job_id:
            job_id = await self._render_previews_for_revision(
                session_id=session_id,
                revision_num=rev.revision_num,
                pptx_bytes=pptx_bytes,
                prev_job_id=None,
                diff=None,
            )

        from core.vision.slide_renderer import SlideRenderer
        slide_count = SlideRenderer.get_slide_count(pptx_bytes)

        return RevisionResult(
            success=True,
            session=session,
            revision=rev,
            diff=None,
            new_job_id=job_id,
            preview_urls=[f"/pptx/preview/{job_id}/{i}" for i in range(1, slide_count + 1)],
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Accessors
    # ──────────────────────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._load_session(session_id)

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        session = self._load_session(session_id)
        if not session:
            return []
        return [
            {**rev.to_dict(), "is_current": i == session.current_rev}
            for i, rev in enumerate(session.history)
        ]

    def get_current_pptx(self, session_id: str) -> Optional[bytes]:
        """Return the current PPTX bytes for the session."""
        session = self._load_session(session_id)
        if not session:
            return None
        rev = session.current_revision
        if not rev:
            return None
        path = session.session_dir / rev.pptx_filename
        return path.read_bytes() if path.exists() else None

    def delete_session(self, session_id: str, user_id: str) -> bool:
        """Delete a session and all its files."""
        session = self._load_session(session_id)
        if not session or session.user_id != user_id:
            return False
        shutil.rmtree(session.session_dir, ignore_errors=True)
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _save_session(session: Session) -> None:
        meta = {
            "session_id":      session.session_id,
            "user_id":         session.user_id,
            "source_filename": session.source_filename,
            "current_rev":     session.current_rev,
            "created_at":      session.created_at,
            "history":         [r.to_dict() for r in session.history],
        }
        session.session_dir.mkdir(parents=True, exist_ok=True)
        (session.session_dir / "session.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _load_session(session_id: str) -> Optional[Session]:
        path = _SESSION_ROOT / session_id / "session.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            history = []
            for r in raw.get("history", []):
                history.append(RevisionEntry(
                    revision_id=r.get("revision_id", ""),
                    revision_num=r.get("revision_num", 0),
                    instruction=r.get("instruction", ""),
                    operations=r.get("operations", []),
                    summary=r.get("summary", ""),
                    pptx_filename=r.get("pptx_filename", ""),
                    diff=r.get("diff"),
                    created_at=r.get("created_at", 0.0),
                ))
            return Session(
                session_id=raw["session_id"],
                user_id=raw["user_id"],
                source_filename=raw.get("source_filename", ""),
                current_rev=raw.get("current_rev", 0),
                history=history,
                created_at=raw.get("created_at", 0.0),
            )
        except Exception as exc:
            logger.warning("SessionManager: failed to load session %s: %s", session_id, exc)
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # Preview helpers
    # ──────────────────────────────────────────────────────────────────────────

    async def _render_previews_for_revision(
        self,
        session_id:   str,
        revision_num: int,
        pptx_bytes:   bytes,
        prev_job_id:  Optional[str],
        diff,                            # Optional[DiffReport]
    ) -> str:
        """
        Render previews for a revision. Uses DiffEngine to only re-render changed slides.
        Returns a job_id that can be used with /pptx/preview/{job_id}/{idx}.
        """
        from core.vision.diff_engine import DiffEngine
        from core.vision.slide_renderer import SlideRenderer
        import uuid as _uuid

        job_id = str(_uuid.uuid4())

        if diff and prev_job_id and diff.has_changes:
            # Diff-aware: copy cached slides + render only changed ones
            diff_engine = DiffEngine()
            await diff_engine.build_full_manifest_from_cache(
                original_job_id=prev_job_id,
                revised_bytes=pptx_bytes,
                diff_report=diff,
                new_job_id=job_id,
            )
        else:
            # Full render (initial upload or no cache available)
            renderer = SlideRenderer(render_dpi=150)
            manifest = await renderer.render(
                file_bytes=pptx_bytes,
                file_type="pptx",
                filename=f"session_{session_id}_rev{revision_num}.pptx",
            )
            job_dir = _SESSION_ROOT.parent / "pptx_jobs" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            for slide in manifest.slides:
                (job_dir / f"slide_{slide.index:04d}.png").write_bytes(slide.image_bytes)

        # Record the job_id for this revision
        self._set_job_id_for_revision(session_id, revision_num, job_id)
        return job_id

    def _get_job_id_for_revision(self, session_id: str, revision_num: int) -> Optional[str]:
        path = _SESSION_ROOT / session_id / f"rev_{revision_num:03d}_job.txt"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return None

    def _set_job_id_for_revision(self, session_id: str, revision_num: int, job_id: str) -> None:
        path = _SESSION_ROOT / session_id / f"rev_{revision_num:03d}_job.txt"
        path.write_text(job_id, encoding="utf-8")
