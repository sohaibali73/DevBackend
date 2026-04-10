"""
RenderCache
===========
SHA256-based slide render cache for the PPTX Intelligence Pipeline.

Prevents duplicate rendering when the same PPTX file is uploaded multiple
times or when the same slide range is requested repeatedly.

Cache layout
------------
$STORAGE_ROOT/pptx_render_cache/
  {file_hash}/{dpi}/{slide_index:04d}.png   → cached slide PNG

The cache key is:
  SHA256(file_bytes) + DPI + slide_index

This means:
  - Identical PPTX files → cache hit regardless of filename
  - Different DPI → separate cache entries
  - Slide-level granularity (only render slides that aren't cached)

Cache stats
-----------
The cache tracks:
  - hit_count / miss_count (in-memory, reset on restart)
  - Total cached files and disk usage

Usage
-----
    from core.vision.render_cache import RenderCache

    cache = RenderCache()

    # Check which slides need rendering
    missing = cache.get_missing_slides(file_bytes, slide_indices, dpi=150)

    # Store rendered slides
    cache.store_slides(file_hash, dpi, {1: png_bytes_1, 5: png_bytes_5})

    # Retrieve cached slide
    png = cache.get_slide(file_hash, slide_index=1, dpi=150)

    # Use in SlideRenderer pipeline
    manifest = await cache.render_with_cache(renderer, file_bytes, filename, dpi=150)
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/data"))
_CACHE_ROOT   = _STORAGE_ROOT / "pptx_render_cache"
_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

# Max cache size (2 GB default)
MAX_CACHE_BYTES = int(os.environ.get("PPTX_RENDER_CACHE_MAX_BYTES", 2 * 1024 * 1024 * 1024))


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class CacheStats:
    """Render cache statistics."""
    hit_count:    int
    miss_count:   int
    cached_files: int
    cache_bytes:  int

    @property
    def hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        return (self.hit_count / total * 100) if total > 0 else 0.0

    def to_dict(self):
        return {
            "hit_count":   self.hit_count,
            "miss_count":  self.miss_count,
            "hit_rate_pct": round(self.hit_rate, 1),
            "cached_files": self.cached_files,
            "cache_mb":    round(self.cache_bytes / (1024 * 1024), 2),
        }


# =============================================================================
# RenderCache
# =============================================================================

class RenderCache:
    """
    SHA256-based PNG render cache for slide images.

    Thread-safe for reads. Writes use atomic rename.
    """

    def __init__(self, cache_root: Path = _CACHE_ROOT):
        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._hit_count  = 0
        self._miss_count = 0

    # ──────────────────────────────────────────────────────────────────────────
    # Hash helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def file_hash(file_bytes: bytes) -> str:
        """Compute SHA256 hex digest of file bytes (first 8 chars for path)."""
        return hashlib.sha256(file_bytes).hexdigest()

    def _slide_path(self, file_hash: str, slide_index: int, dpi: int) -> Path:
        """Return the cache path for a specific slide."""
        # Use first 8 chars of hash as directory name to keep paths short
        prefix = file_hash[:2]    # 2-char prefix for filesystem distribution
        return (
            self.cache_root / prefix / file_hash / str(dpi)
            / f"slide_{slide_index:04d}.png"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Get / Store
    # ──────────────────────────────────────────────────────────────────────────

    def get_slide(
        self,
        file_hash:   str,
        slide_index: int,
        dpi:         int = 150,
    ) -> Optional[bytes]:
        """
        Return cached PNG bytes for a slide, or None if not cached.

        Increments hit_count or miss_count accordingly.
        """
        path = self._slide_path(file_hash, slide_index, dpi)
        if path.exists():
            self._hit_count += 1
            try:
                return path.read_bytes()
            except OSError:
                pass
        self._miss_count += 1
        return None

    def store_slide(
        self,
        file_hash:   str,
        slide_index: int,
        dpi:         int,
        png_bytes:   bytes,
    ) -> None:
        """
        Store PNG bytes in the cache using an atomic write.
        Silently ignores write failures (cache is best-effort).
        """
        path = self._slide_path(file_hash, slide_index, dpi)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write via temp file + rename
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(png_bytes)
            tmp.rename(path)
        except Exception as exc:
            logger.debug("RenderCache.store_slide failed: %s", exc)

    def store_slides(
        self,
        file_hash: str,
        dpi:       int,
        slides:    Dict[int, bytes],  # {slide_index: png_bytes}
    ) -> None:
        """Store multiple slides at once."""
        for idx, png in slides.items():
            self.store_slide(file_hash, idx, dpi, png)

    def get_missing_slides(
        self,
        file_hash:     str,
        slide_indices: List[int],
        dpi:           int = 150,
    ) -> List[int]:
        """
        Return the subset of slide_indices that are NOT cached.

        Use this to determine which slides need to be rendered.
        """
        missing = []
        for idx in slide_indices:
            path = self._slide_path(file_hash, idx, dpi)
            if not path.exists():
                missing.append(idx)
        return missing

    def has_slide(self, file_hash: str, slide_index: int, dpi: int = 150) -> bool:
        return self._slide_path(file_hash, slide_index, dpi).exists()

    # ──────────────────────────────────────────────────────────────────────────
    # High-level: render with cache
    # ──────────────────────────────────────────────────────────────────────────

    async def render_with_cache(
        self,
        renderer,                   # SlideRenderer instance
        file_bytes:  bytes,
        filename:    str = "doc",
        file_type:   str = "pptx",
        dpi:         int = 150,
        slide_range: Optional[tuple] = None,
    ):
        """
        Render slides using cache — only render slides not already cached.

        Returns a SlideManifest where each slide's image_bytes may come
        from cache (fast) or freshly rendered (slow).
        """
        from core.vision.slide_renderer import SlideRenderer, SlideManifest, SlideImageInfo

        fhash = self.file_hash(file_bytes)

        # Get slide count first (cheap)
        if file_type in ("pptx", "ppt"):
            total = SlideRenderer.get_slide_count(file_bytes)
        else:
            total = SlideRenderer.get_pdf_page_count(file_bytes)

        if total == 0:
            return SlideManifest(
                source_filename=filename, source_type=file_type,
                slide_count=0, error="Could not determine slide count",
            )

        # Which slides do we need?
        if slide_range:
            wanted = list(range(slide_range[0], slide_range[1] + 1))
        else:
            wanted = list(range(1, total + 1))

        # Check cache
        missing = self.get_missing_slides(fhash, wanted, dpi)
        cached_indices = [i for i in wanted if i not in missing]

        slides = []

        # ── Fetch cached slides ───────────────────────────────────────────────
        for idx in cached_indices:
            png = self.get_slide(fhash, idx, dpi)
            if png:
                from core.vision.slide_renderer import SlideRenderer as SR
                w, h = SR._image_dimensions(png)
                slides.append(SlideImageInfo(
                    index=idx, image_bytes=png,
                    width_px=w, height_px=h,
                    source_type="cache",
                ))

        # ── Render missing slides ─────────────────────────────────────────────
        if missing:
            # Render only the missing range(s)
            if len(missing) == len(wanted):
                # All missing — render everything
                manifest = await renderer.render(
                    file_bytes=file_bytes, file_type=file_type,
                    filename=filename, slide_range=slide_range,
                )
            else:
                # Scattered missing — render each individually
                from core.vision.slide_renderer import SlideManifest as SM
                import asyncio
                manifests = await asyncio.gather(*[
                    renderer.render(
                        file_bytes=file_bytes, file_type=file_type,
                        filename=filename, slide_range=(idx, idx),
                    )
                    for idx in missing
                ])
                all_new_slides = []
                for m in manifests:
                    all_new_slides.extend(m.slides)
                manifest = SM(
                    source_filename=filename, source_type=file_type,
                    slide_count=total, slides=all_new_slides,
                    render_strategy="partial_cache",
                )

            # Store newly rendered slides in cache
            for slide in manifest.slides:
                self.store_slide(fhash, slide.index, dpi, slide.image_bytes)
                slides.append(slide)

        slides.sort(key=lambda s: s.index)

        from core.vision.slide_renderer import SlideManifest
        return SlideManifest(
            source_filename=filename,
            source_type=file_type,
            slide_count=total,
            slides=slides,
            render_strategy=f"cache({len(cached_indices)}_hit/{len(missing)}_miss)",
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Cache management
    # ──────────────────────────────────────────────────────────────────────────

    def invalidate(self, file_hash: str, dpi: Optional[int] = None) -> int:
        """
        Remove all cached slides for a file hash.
        If dpi is specified, only remove that DPI level.
        Returns number of files removed.
        """
        prefix = file_hash[:2]
        base = self.cache_root / prefix / file_hash
        if not base.exists():
            return 0

        count = 0
        if dpi is not None:
            dpi_dir = base / str(dpi)
            if dpi_dir.exists():
                for f in dpi_dir.glob("*.png"):
                    f.unlink(missing_ok=True)
                    count += 1
        else:
            import shutil
            try:
                count = sum(1 for _ in base.rglob("*.png"))
                shutil.rmtree(base, ignore_errors=True)
            except Exception:
                pass

        return count

    def prune_lru(self, max_bytes: int = MAX_CACHE_BYTES) -> int:
        """
        Prune cache to stay under max_bytes using LRU (oldest access time).
        Returns number of files deleted.
        """
        if not self.cache_root.exists():
            return 0

        # Collect all PNG files with atime
        files = []
        for p in self.cache_root.rglob("*.png"):
            try:
                files.append((p.stat().st_atime, p.stat().st_size, p))
            except OSError:
                pass

        files.sort()  # oldest access first

        total_size = sum(f[1] for f in files)
        deleted = 0

        for atime, size, path in files:
            if total_size <= max_bytes * 0.9:  # 90% threshold
                break
            try:
                path.unlink(missing_ok=True)
                total_size -= size
                deleted += 1
            except OSError:
                pass

        if deleted:
            logger.info("RenderCache.prune_lru: deleted %d files", deleted)
        return deleted

    @property
    def stats(self) -> CacheStats:
        """Compute current cache statistics."""
        count = 0
        total_bytes = 0
        try:
            for p in self.cache_root.rglob("*.png"):
                count += 1
                try:
                    total_bytes += p.stat().st_size
                except OSError:
                    pass
        except Exception:
            pass
        return CacheStats(
            hit_count=self._hit_count,
            miss_count=self._miss_count,
            cached_files=count,
            cache_bytes=total_bytes,
        )

    def clear_all(self) -> None:
        """⚠️ Clear the entire render cache. Use with caution."""
        import shutil
        try:
            shutil.rmtree(self.cache_root, ignore_errors=True)
            self.cache_root.mkdir(parents=True, exist_ok=True)
            logger.warning("RenderCache.clear_all: cache cleared")
        except Exception as exc:
            logger.error("RenderCache.clear_all failed: %s", exc)


# ── Module-level singleton ────────────────────────────────────────────────────
_singleton: Optional[RenderCache] = None


def get_render_cache() -> RenderCache:
    """Return the shared RenderCache singleton."""
    global _singleton
    if _singleton is None:
        _singleton = RenderCache()
    return _singleton
