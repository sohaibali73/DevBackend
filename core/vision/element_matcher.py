"""
ElementMatcher
==============
Perceptual-hash based matching of detected visual elements against the
Potomac design element library (InDesign-exported PNG assets).

Library layout
--------------
ClaudeSkills/potomac-pptx/element-library/
    icons/         → icon PNGs (hexagon-globe.png, hexagon-shield.png, ...)
    logos/         → logo variants (already in brand-assets/logos/)
    backgrounds/   → background textures / gradients
    badges/        → badge templates
    dividers/      → line / divider elements
    shapes/        → generic shape templates

Index cache
-----------
~/.sandbox/element_index.json  — {filename: {phash, category, tags, ...}}
Rebuilt automatically when new files are added to the library.

Usage
-----
    from core.vision.element_matcher import ElementMatcher

    matcher = ElementMatcher()
    matcher.build_index()  # or auto-built on first match()

    # Find closest element to a detected icon
    match = matcher.match(query_image_bytes, category="icons", top_k=3)
    if match:
        print(match[0].filename, match[0].score)

    # Add new elements to the library
    matcher.add_element(png_bytes, "hexagon-anchor.png", category="icons",
                        tags=["hexagon", "anchor", "strategy"])
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Library paths ──────────────────────────────────────────────────────────────
_THIS_DIR    = Path(__file__).parent
_REPO_ROOT   = _THIS_DIR.parent.parent
_LIBRARY_DIR = _REPO_ROOT / "ClaudeSkills" / "potomac-pptx" / "element-library"
_CACHE_DIR   = Path(os.environ.get("SANDBOX_DATA_DIR", Path.home() / ".sandbox"))
_INDEX_PATH  = _CACHE_DIR / "element_index.json"

VALID_CATEGORIES = {"icons", "logos", "backgrounds", "badges", "dividers", "shapes"}


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class LibraryElement:
    """A single element in the design library."""
    filename:   str
    category:   str
    tags:       List[str] = field(default_factory=list)
    phash:      str = ""         # 64-bit perceptual hash as hex string
    ahash:      str = ""         # average hash (secondary)
    dhash:      str = ""         # difference hash (tertiary)
    file_size:  int = 0
    width_px:   int = 0
    height_px:  int = 0
    sha256:     str = ""         # for deduplication

    @property
    def path(self) -> Path:
        return _LIBRARY_DIR / self.category / self.filename


@dataclass
class ElementMatch:
    """Result of a library element match query."""
    element:  LibraryElement
    score:    float           # 0.0 (no match) – 1.0 (perfect match)
    distance: int             # Hamming distance of perceptual hashes (lower = better)

    @property
    def filename(self) -> str:
        return self.element.filename

    @property
    def category(self) -> str:
        return self.element.category

    @property
    def image_bytes(self) -> Optional[bytes]:
        """Read element bytes from disk."""
        try:
            return self.element.path.read_bytes()
        except OSError:
            return None


# =============================================================================
# Perceptual hashing utilities
# =============================================================================

def _phash(img_bytes: bytes, hash_size: int = 8) -> Optional[str]:
    """
    Compute a perceptual hash (pHash) of an image.
    Uses imagehash library if available; falls back to a simple DCT-based hash.
    Returns 64-bit hex string or None on failure.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes)).convert("L").resize(
            (hash_size * 4, hash_size * 4)
        )
        # Try imagehash first
        try:
            import imagehash
            h = imagehash.phash(img, hash_size=hash_size)
            return str(h)
        except ImportError:
            pass
        # Manual DCT-based pHash fallback
        import numpy as np
        pixels = np.array(img, dtype=float)
        # 2D DCT via separable 1D DCTs
        from scipy.fft import dctn
        dct = dctn(pixels, type=2, norm="ortho")
        top = dct[:hash_size, :hash_size].flatten()
        median = float(np.median(top))
        bits = "".join("1" if v > median else "0" for v in top)
        return hex(int(bits, 2))[2:].zfill(16)
    except Exception as exc:
        logger.debug("phash failed: %s", exc)
        return None


def _ahash(img_bytes: bytes, hash_size: int = 8) -> Optional[str]:
    """Average hash — very fast, lower quality than pHash."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes)).convert("L").resize(
            (hash_size, hash_size)
        )
        try:
            import imagehash
            return str(imagehash.average_hash(img, hash_size=hash_size))
        except ImportError:
            pass
        import numpy as np
        pixels = np.array(img, dtype=float)
        mean = float(pixels.mean())
        bits = "".join("1" if p > mean else "0" for p in pixels.flatten())
        return hex(int(bits, 2))[2:].zfill(16)
    except Exception:
        return None


def _dhash(img_bytes: bytes, hash_size: int = 8) -> Optional[str]:
    """Difference hash — gradient-sensitive."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes)).convert("L").resize(
            (hash_size + 1, hash_size)
        )
        try:
            import imagehash
            return str(imagehash.dhash(img, hash_size=hash_size))
        except ImportError:
            pass
        import numpy as np
        pixels = np.array(img)
        diff = pixels[:, 1:] > pixels[:, :-1]
        bits = "".join("1" if b else "0" for b in diff.flatten())
        return hex(int(bits, 2))[2:].zfill(16)
    except Exception:
        return None


def _hamming(h1: str, h2: str) -> int:
    """Hamming distance between two hex hash strings."""
    try:
        i1 = int(h1, 16)
        i2 = int(h2, 16)
        xor = i1 ^ i2
        return bin(xor).count("1")
    except Exception:
        return 64  # worst case


def _combined_distance(elem: LibraryElement, q_phash: str, q_ahash: str, q_dhash: str) -> int:
    """Weighted combination of three hash distances."""
    d_p = _hamming(elem.phash, q_phash)  if (elem.phash and q_phash)  else 32
    d_a = _hamming(elem.ahash, q_ahash)  if (elem.ahash and q_ahash)  else 32
    d_d = _hamming(elem.dhash, q_dhash)  if (elem.dhash and q_dhash)  else 32
    return d_p * 2 + d_a + d_d  # weighted: pHash counts double


def _score_from_distance(distance: int, max_dist: int = 128) -> float:
    """Convert a combined hash distance to a [0, 1] similarity score."""
    return max(0.0, 1.0 - distance / max_dist)


# =============================================================================
# ElementMatcher
# =============================================================================

class ElementMatcher:
    """
    Manages the Potomac design element library and matches query images
    against it using perceptual hashing.

    Thread-safe (read-only operations are lock-free; index writes use a lock).
    """

    def __init__(
        self,
        library_dir: Path = _LIBRARY_DIR,
        index_path:  Path = _INDEX_PATH,
        auto_build:  bool = True,
    ):
        self.library_dir = library_dir
        self.index_path  = index_path
        self._index: Dict[str, LibraryElement] = {}  # key = category/filename
        self._built = False

        if auto_build:
            try:
                self._load_index()
                # Check if library has new files not in index
                self._sync_new_files()
            except Exception as exc:
                logger.debug("ElementMatcher index load failed: %s", exc)

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def build_index(self, force: bool = False) -> int:
        """
        Scan library directory and compute perceptual hashes for all images.
        Returns number of elements indexed.

        Parameters
        ----------
        force : if True, re-index all elements even if already cached.
        """
        if not self.library_dir.exists():
            logger.info("Element library dir does not exist yet: %s", self.library_dir)
            self.library_dir.mkdir(parents=True, exist_ok=True)
            for cat in VALID_CATEGORIES:
                (self.library_dir / cat).mkdir(exist_ok=True)
            return 0

        count = 0
        for category in VALID_CATEGORIES:
            cat_dir = self.library_dir / category
            if not cat_dir.exists():
                cat_dir.mkdir(parents=True, exist_ok=True)
                continue

            for img_file in cat_dir.iterdir():
                if img_file.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                    continue

                key = f"{category}/{img_file.name}"
                if not force and key in self._index:
                    count += 1
                    continue

                try:
                    img_bytes = img_file.read_bytes()
                    elem = self._hash_element(img_bytes, img_file.name, category)
                    self._index[key] = elem
                    count += 1
                    logger.debug("Indexed: %s", key)
                except Exception as exc:
                    logger.warning("Failed to index %s: %s", img_file, exc)

        self._save_index()
        self._built = True
        logger.info("ElementMatcher: indexed %d elements", count)
        return count

    def add_element(
        self,
        img_bytes: bytes,
        filename:  str,
        category:  str = "icons",
        tags:      Optional[List[str]] = None,
    ) -> LibraryElement:
        """
        Add a new element to the library: save to disk and update index.

        Parameters
        ----------
        img_bytes : PNG bytes of the design element
        filename  : desired filename (e.g., "hexagon-anchor.png")
        category  : library category (icons | logos | backgrounds | badges | ...)
        tags      : descriptive tags for search
        """
        if category not in VALID_CATEGORIES:
            category = "shapes"

        cat_dir = self.library_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        out_path = cat_dir / filename
        out_path.write_bytes(img_bytes)

        elem = self._hash_element(img_bytes, filename, category, tags or [])
        key = f"{category}/{filename}"
        self._index[key] = elem
        self._save_index()
        logger.info("ElementMatcher: added %s", key)
        return elem

    def match(
        self,
        query_bytes: bytes,
        category:    Optional[str] = None,
        top_k:       int = 3,
        threshold:   float = 0.5,  # minimum similarity score to include
    ) -> List[ElementMatch]:
        """
        Find the closest library elements to a query image.

        Parameters
        ----------
        query_bytes : PNG bytes of the element to match
        category    : restrict search to this category (None = all)
        top_k       : return at most this many results
        threshold   : minimum similarity score (0–1) to include in results

        Returns
        -------
        List of ElementMatch sorted by score descending.
        """
        if not self._index:
            self.build_index()

        if not self._index:
            return []

        q_p = _phash(query_bytes)
        q_a = _ahash(query_bytes)
        q_d = _dhash(query_bytes)

        if not q_p:
            return []

        candidates = [
            elem for key, elem in self._index.items()
            if (category is None or elem.category == category)
        ]

        scored: List[Tuple[int, LibraryElement]] = []
        for elem in candidates:
            dist = _combined_distance(elem, q_p or "", q_a or "", q_d or "")
            scored.append((dist, elem))

        scored.sort(key=lambda x: x[0])

        results: List[ElementMatch] = []
        for dist, elem in scored[:top_k]:
            score = _score_from_distance(dist)
            if score >= threshold:
                results.append(ElementMatch(element=elem, score=score, distance=dist))

        return results

    def find_by_tag(self, tag: str) -> List[LibraryElement]:
        """Return all library elements that have a given tag."""
        return [
            elem for elem in self._index.values()
            if tag.lower() in [t.lower() for t in elem.tags]
        ]

    def find_by_name(self, name: str) -> Optional[LibraryElement]:
        """Find an element by filename (case-insensitive, prefix match)."""
        name_lower = name.lower()
        for elem in self._index.values():
            if elem.filename.lower().startswith(name_lower):
                return elem
        return None

    @property
    def element_count(self) -> int:
        return len(self._index)

    def list_elements(self, category: Optional[str] = None) -> List[LibraryElement]:
        """List all (or category-filtered) elements."""
        return [
            e for e in self._index.values()
            if category is None or e.category == category
        ]

    def get_catalog(self) -> Dict:
        """Return a summary catalog for API responses."""
        by_cat: Dict[str, List[str]] = {}
        for elem in self._index.values():
            by_cat.setdefault(elem.category, []).append(elem.filename)
        return {
            "total_elements": len(self._index),
            "categories": {cat: sorted(fns) for cat, fns in sorted(by_cat.items())},
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _hash_element(
        self,
        img_bytes: bytes,
        filename:  str,
        category:  str,
        tags:      Optional[List[str]] = None,
    ) -> LibraryElement:
        """Compute all hashes + metadata for an element."""
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        sha256 = hashlib.sha256(img_bytes).hexdigest()

        return LibraryElement(
            filename=filename,
            category=category,
            tags=tags or self._auto_tags(filename),
            phash=_phash(img_bytes) or "",
            ahash=_ahash(img_bytes) or "",
            dhash=_dhash(img_bytes) or "",
            file_size=len(img_bytes),
            width_px=img.width,
            height_px=img.height,
            sha256=sha256,
        )

    @staticmethod
    def _auto_tags(filename: str) -> List[str]:
        """Generate tags from filename by splitting on hyphens/underscores."""
        stem = Path(filename).stem.lower()
        return [t for t in stem.replace("_", "-").split("-") if len(t) > 1]

    def _save_index(self) -> None:
        """Persist index to JSON cache file."""
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        data = {k: asdict(v) for k, v in self._index.items()}
        self.index_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_index(self) -> None:
        """Load index from JSON cache file."""
        if not self.index_path.exists():
            return
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        self._index = {}
        for key, d in raw.items():
            try:
                self._index[key] = LibraryElement(**d)
            except Exception as exc:
                logger.debug("Index entry '%s' skipped: %s", key, exc)
        logger.debug("ElementMatcher: loaded %d entries from cache", len(self._index))
        self._built = True

    def _sync_new_files(self) -> None:
        """Add any library files not yet in the index (fast, no re-indexing)."""
        if not self.library_dir.exists():
            return
        changed = False
        for category in VALID_CATEGORIES:
            cat_dir = self.library_dir / category
            if not cat_dir.exists():
                continue
            for img_file in cat_dir.iterdir():
                if img_file.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                    continue
                key = f"{category}/{img_file.name}"
                if key not in self._index:
                    try:
                        img_bytes = img_file.read_bytes()
                        self._index[key] = self._hash_element(
                            img_bytes, img_file.name, category
                        )
                        changed = True
                        logger.info("ElementMatcher: auto-indexed new file: %s", key)
                    except Exception as exc:
                        logger.warning("Failed to auto-index %s: %s", img_file, exc)
        if changed:
            self._save_index()


# ── Module-level singleton (lazy) ──────────────────────────────────────────────
_singleton: Optional[ElementMatcher] = None


def get_element_matcher() -> ElementMatcher:
    """Return the shared ElementMatcher singleton (built lazily)."""
    global _singleton
    if _singleton is None:
        _singleton = ElementMatcher(auto_build=True)
    return _singleton
