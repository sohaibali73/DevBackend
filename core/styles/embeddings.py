"""
Lightweight sentence-embedding helper for voice cloning + style fidelity.

Uses sentence-transformers (already a project dep). The model is loaded once
on first call and cached on the Railway volume at $STORAGE_ROOT/models/.
Falls back to a deterministic hash-based pseudo-embedding if the model can't
be loaded — so endpoints never fail hard in environments without disk space.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

_MODEL = None
_MODEL_LOCK = threading.Lock()
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 384-dim, fast
_DIM = 384


def _hf_cache_dir() -> str:
    root = os.getenv("STORAGE_ROOT", "/data")
    p = os.path.join(root, "models", "hf_cache")
    try:
        os.makedirs(p, exist_ok=True)
    except OSError:
        pass
    return p


def _load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        try:
            os.environ.setdefault("HF_HOME", _hf_cache_dir())
            os.environ.setdefault("TRANSFORMERS_CACHE", _hf_cache_dir())
            from sentence_transformers import SentenceTransformer
            _MODEL = SentenceTransformer(_MODEL_NAME, cache_folder=_hf_cache_dir())
            logger.info("✓ Loaded sentence-transformers model %s", _MODEL_NAME)
        except Exception as e:
            logger.warning(
                "sentence-transformers unavailable (%s) — using hash fallback embeddings",
                e,
            )
            _MODEL = "fallback"
        return _MODEL


def _hash_embedding(text: str, dim: int = _DIM) -> List[float]:
    """Deterministic fallback embedding so the pipeline never breaks."""
    h = hashlib.sha256((text or "").encode("utf-8", errors="ignore")).digest()
    # Repeat the 32-byte hash to fill `dim` floats in [-1, 1]
    out: List[float] = []
    i = 0
    while len(out) < dim:
        out.append((h[i % 32] / 127.5) - 1.0)
        i += 1
    return out


def embed(text: str) -> List[float]:
    return embed_many([text or ""])[0]


def embed_many(texts: Sequence[str]) -> List[List[float]]:
    if not texts:
        return []
    model = _load_model()
    if model == "fallback" or model is None:
        return [_hash_embedding(t) for t in texts]
    try:
        vecs = model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        return [list(map(float, v)) for v in vecs]
    except Exception as e:
        logger.warning("embed_many failed (%s) — using hash fallback", e)
        return [_hash_embedding(t) for t in texts]


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def centroid(vecs: List[List[float]]) -> List[float]:
    if not vecs:
        return []
    dim = len(vecs[0])
    out = [0.0] * dim
    for v in vecs:
        for i in range(dim):
            out[i] += v[i]
    n = float(len(vecs))
    return [x / n for x in out]
