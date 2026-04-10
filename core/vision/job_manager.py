"""
JobManager
==========
Production job lifecycle management for the PPTX Intelligence Pipeline.

Responsibilities
----------------
- List all jobs for a user with metadata (action, status, size, age)
- Delete individual jobs + their files
- Auto-cleanup jobs older than a configurable TTL
- Storage quota enforcement per user
- Storage statistics (total size, job count, oldest/newest)

Storage layout
--------------
$STORAGE_ROOT/pptx_jobs/{job_id}/
  meta.json          → job metadata (status, action, user_id, created_at)
  slide_*.png        → rendered slide previews
  *.pptx             → generated output files
  *.pdf              → exported files
  *.zip              → exported ZIPs

$STORAGE_ROOT/pptx_sessions/{session_id}/
  session.json       → session metadata
  rev_*.pptx         → revision history files
  rev_*_job.txt      → job ID cross-references

Usage
-----
    from core.vision.job_manager import JobManager

    mgr = JobManager()

    # List all jobs for a user
    jobs = mgr.list_jobs(user_id="user123", limit=20)

    # Delete a specific job
    mgr.delete_job(job_id="abc-123", user_id="user123")

    # Auto-cleanup old jobs (call from cron or startup)
    deleted_count = mgr.cleanup_expired_jobs(max_age_hours=72)

    # Storage stats for a user
    stats = mgr.storage_stats(user_id="user123")
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_STORAGE_ROOT  = Path(os.environ.get("STORAGE_ROOT", "/data"))
_JOB_STORE     = _STORAGE_ROOT / "pptx_jobs"
_SESSION_STORE = _STORAGE_ROOT / "pptx_sessions"

# Default TTL for auto-cleanup (72 hours)
DEFAULT_TTL_HOURS = int(os.environ.get("PPTX_JOB_TTL_HOURS", 72))

# Default max storage per user (500 MB)
DEFAULT_MAX_BYTES_PER_USER = int(os.environ.get("PPTX_MAX_BYTES_PER_USER", 500 * 1024 * 1024))


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class JobInfo:
    """Summary metadata for a single PPTX intelligence job."""
    job_id:     str
    user_id:    str
    action:     str            # "merge" | "reconstruct" | "analyze" | ...
    status:     str            # "complete" | "running" | "error"
    created_at: float          # Unix timestamp
    size_bytes: int            # total disk usage for this job
    slide_count: int           # number of rendered slide PNGs
    has_pptx:   bool           # output .pptx file present
    age_hours:  float          # how old the job is

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id":      self.job_id,
            "user_id":     self.user_id,
            "action":      self.action,
            "status":      self.status,
            "created_at":  self.created_at,
            "created_at_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.created_at)
            ) if self.created_at else "",
            "size_bytes":  self.size_bytes,
            "size_mb":     round(self.size_bytes / (1024 * 1024), 2),
            "slide_count": self.slide_count,
            "has_pptx":    self.has_pptx,
            "age_hours":   round(self.age_hours, 1),
        }


@dataclass
class StorageStats:
    """Storage statistics for a user."""
    user_id:         str
    job_count:       int
    session_count:   int
    total_bytes:     int
    max_bytes:       int
    jobs:            List[JobInfo] = field(default_factory=list)

    @property
    def usage_pct(self) -> float:
        return (self.total_bytes / self.max_bytes * 100) if self.max_bytes > 0 else 0.0

    @property
    def is_over_quota(self) -> bool:
        return self.total_bytes > self.max_bytes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id":      self.user_id,
            "job_count":    self.job_count,
            "session_count": self.session_count,
            "total_bytes":  self.total_bytes,
            "total_mb":     round(self.total_bytes / (1024 * 1024), 2),
            "max_bytes":    self.max_bytes,
            "max_mb":       round(self.max_bytes / (1024 * 1024), 2),
            "usage_pct":    round(self.usage_pct, 1),
            "is_over_quota": self.is_over_quota,
        }


# =============================================================================
# JobManager
# =============================================================================

class JobManager:
    """
    Manages PPTX intelligence job lifecycle and storage.

    All operations are synchronous (safe to call from background tasks or
    FastAPI background workers).
    """

    def __init__(
        self,
        job_store:     Path = _JOB_STORE,
        session_store: Path = _SESSION_STORE,
        ttl_hours:     int  = DEFAULT_TTL_HOURS,
        max_bytes:     int  = DEFAULT_MAX_BYTES_PER_USER,
    ):
        self.job_store     = job_store
        self.session_store = session_store
        self.ttl_hours     = ttl_hours
        self.max_bytes     = max_bytes
        self.job_store.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────────────────────────────
    # List jobs
    # ──────────────────────────────────────────────────────────────────────────

    def list_jobs(
        self,
        user_id:       Optional[str] = None,
        action_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit:         int = 50,
        offset:        int = 0,
        sort_by:       str = "created_at",   # "created_at" | "size" | "action"
        sort_desc:     bool = True,
    ) -> List[JobInfo]:
        """
        List all jobs, optionally filtered by user_id, action, or status.

        Returns JobInfo objects sorted by created_at descending by default.
        """
        jobs = []
        if not self.job_store.exists():
            return []

        for job_dir in self.job_store.iterdir():
            if not job_dir.is_dir():
                continue
            info = self._read_job_info(job_dir)
            if info is None:
                continue
            if user_id and info.user_id != user_id:
                continue
            if action_filter and info.action != action_filter:
                continue
            if status_filter and info.status != status_filter:
                continue
            jobs.append(info)

        # Sort
        key_map = {
            "created_at": lambda j: j.created_at,
            "size":       lambda j: j.size_bytes,
            "action":     lambda j: j.action,
        }
        key_fn = key_map.get(sort_by, lambda j: j.created_at)
        jobs.sort(key=key_fn, reverse=sort_desc)

        return jobs[offset: offset + limit]

    def get_job(self, job_id: str, user_id: Optional[str] = None) -> Optional[JobInfo]:
        """Get a single job's info."""
        job_dir = self.job_store / job_id
        if not job_dir.exists():
            return None
        info = self._read_job_info(job_dir)
        if info and user_id and info.user_id != user_id:
            return None
        return info

    # ──────────────────────────────────────────────────────────────────────────
    # Delete jobs
    # ──────────────────────────────────────────────────────────────────────────

    def delete_job(self, job_id: str, user_id: Optional[str] = None) -> bool:
        """
        Delete a job directory and all its files.

        Parameters
        ----------
        job_id  : job to delete
        user_id : if provided, only delete if job belongs to this user

        Returns True if deleted, False if not found or access denied.
        """
        job_dir = self.job_store / job_id
        if not job_dir.exists():
            return False

        if user_id:
            info = self._read_job_info(job_dir)
            if info and info.user_id != user_id:
                logger.warning("delete_job: access denied for job %s (user %s)", job_id, user_id)
                return False

        shutil.rmtree(job_dir, ignore_errors=True)
        logger.info("JobManager: deleted job %s", job_id)
        return True

    def delete_all_user_jobs(self, user_id: str) -> int:
        """Delete ALL jobs for a user. Returns count deleted."""
        jobs = self.list_jobs(user_id=user_id, limit=10000)
        count = 0
        for job in jobs:
            if self.delete_job(job.job_id, user_id=user_id):
                count += 1
        logger.info("JobManager: deleted %d jobs for user %s", count, user_id)
        return count

    # ──────────────────────────────────────────────────────────────────────────
    # Auto-cleanup
    # ──────────────────────────────────────────────────────────────────────────

    def cleanup_expired_jobs(
        self,
        max_age_hours: Optional[int] = None,
        dry_run:       bool = False,
    ) -> int:
        """
        Delete all jobs older than max_age_hours.

        Parameters
        ----------
        max_age_hours : TTL in hours (defaults to self.ttl_hours)
        dry_run       : if True, count but don't delete

        Returns number of jobs deleted (or would be deleted in dry run).
        """
        ttl = max_age_hours or self.ttl_hours
        cutoff = time.time() - (ttl * 3600)
        count = 0

        if not self.job_store.exists():
            return 0

        for job_dir in self.job_store.iterdir():
            if not job_dir.is_dir():
                continue
            info = self._read_job_info(job_dir)
            if info and info.created_at < cutoff:
                if not dry_run:
                    shutil.rmtree(job_dir, ignore_errors=True)
                count += 1

        if not dry_run:
            logger.info("JobManager: cleanup deleted %d expired jobs (TTL=%dh)", count, ttl)
        else:
            logger.info("JobManager: dry-run would delete %d expired jobs (TTL=%dh)", count, ttl)

        return count

    def cleanup_user_over_quota(self, user_id: str) -> int:
        """
        If user is over storage quota, delete oldest jobs until under quota.
        Returns number of jobs deleted.
        """
        stats = self.storage_stats(user_id)
        if not stats.is_over_quota:
            return 0

        # Sort jobs oldest first
        jobs = sorted(stats.jobs, key=lambda j: j.created_at)
        deleted = 0

        for job in jobs:
            if self.delete_job(job.job_id, user_id=user_id):
                deleted += 1
                # Recalculate remaining usage
                remaining = stats.total_bytes - sum(
                    j.size_bytes for j in jobs[:deleted]
                )
                if remaining <= self.max_bytes * 0.8:  # 80% threshold
                    break

        logger.info(
            "JobManager: evicted %d jobs to bring user %s under quota", deleted, user_id
        )
        return deleted

    # ──────────────────────────────────────────────────────────────────────────
    # Storage stats
    # ──────────────────────────────────────────────────────────────────────────

    def storage_stats(self, user_id: Optional[str] = None) -> StorageStats:
        """
        Compute storage statistics for a user (or all users if user_id=None).

        Returns StorageStats with job_count, total_bytes, usage_pct, etc.
        """
        jobs = self.list_jobs(user_id=user_id, limit=10000)
        total_bytes = sum(j.size_bytes for j in jobs)

        # Count sessions
        session_count = 0
        if self.session_store.exists():
            for s in self.session_store.iterdir():
                if s.is_dir():
                    meta_path = s / "session.json"
                    if meta_path.exists():
                        try:
                            meta = json.loads(meta_path.read_text(encoding="utf-8"))
                            if user_id is None or meta.get("user_id") == user_id:
                                session_count += 1
                                # Add session dir size to total
                                total_bytes += self._dir_size(s)
                        except Exception:
                            pass

        return StorageStats(
            user_id=user_id or "all",
            job_count=len(jobs),
            session_count=session_count,
            total_bytes=total_bytes,
            max_bytes=self.max_bytes,
            jobs=jobs,
        )

    def global_stats(self) -> Dict[str, Any]:
        """Return system-wide storage statistics (admin use)."""
        if not self.job_store.exists():
            return {"total_jobs": 0, "total_bytes": 0, "users": {}}

        user_map: Dict[str, Dict] = {}
        for job_dir in self.job_store.iterdir():
            if not job_dir.is_dir():
                continue
            info = self._read_job_info(job_dir)
            if not info:
                continue
            uid = info.user_id or "unknown"
            if uid not in user_map:
                user_map[uid] = {"job_count": 0, "total_bytes": 0}
            user_map[uid]["job_count"] += 1
            user_map[uid]["total_bytes"] += info.size_bytes

        total_jobs  = sum(u["job_count"] for u in user_map.values())
        total_bytes = sum(u["total_bytes"] for u in user_map.values())

        return {
            "total_jobs":  total_jobs,
            "total_bytes": total_bytes,
            "total_mb":    round(total_bytes / (1024 * 1024), 2),
            "user_count":  len(user_map),
            "users":       {
                uid: {
                    "job_count":  d["job_count"],
                    "total_mb":   round(d["total_bytes"] / (1024 * 1024), 2),
                }
                for uid, d in sorted(
                    user_map.items(),
                    key=lambda x: x[1]["total_bytes"],
                    reverse=True,
                )
            },
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _read_job_info(self, job_dir: Path) -> Optional[JobInfo]:
        """Read job metadata and compute size from a job directory."""
        meta_path = job_dir / "meta.json"
        try:
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            else:
                meta = {}
        except Exception:
            meta = {}

        try:
            size  = self._dir_size(job_dir)
            slides = len(list(job_dir.glob("slide_*.png")))
            pptxs  = list(job_dir.glob("*.pptx"))
            created_at = float(meta.get("created_at", job_dir.stat().st_mtime))
            age_hours  = (time.time() - created_at) / 3600.0

            return JobInfo(
                job_id=job_dir.name,
                user_id=meta.get("user_id", ""),
                action=meta.get("action", "unknown"),
                status=meta.get("status", "unknown"),
                created_at=created_at,
                size_bytes=size,
                slide_count=slides,
                has_pptx=len(pptxs) > 0,
                age_hours=age_hours,
            )
        except Exception as exc:
            logger.debug("JobManager._read_job_info failed for %s: %s", job_dir.name, exc)
            return None

    @staticmethod
    def _dir_size(path: Path) -> int:
        """Recursively compute total size of a directory in bytes."""
        total = 0
        try:
            for p in path.rglob("*"):
                if p.is_file():
                    try:
                        total += p.stat().st_size
                    except OSError:
                        pass
        except Exception:
            pass
        return total
