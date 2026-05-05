"""
Lightweight sentence-embedding helper for voice cloning + style fidelity.

Uses sentence-transformers (already a project dep). The model is loaded once
on first call and cached on the Railway volume at $STORAGE_ROOT/models/.
Falls back to a deterministic hash-based pseudo-embedding if the model can't
be loaded — so endpoints never fail hard in environments without disk space.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
from typing import Any, List, Optional, Sequence

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


# -----------------------------------------------------------------------------
# Vector coercion + math
# -----------------------------------------------------------------------------

def coerce_vector(v: Any) -> List[float]:
    """
    Normalize an embedding to List[float].

    Postgres pgvector via supabase-py returns vectors as JSON-formatted strings
    like "[0.1, 0.2, ...]". Other paths may give lists, tuples, or numpy
    arrays. Anything that can't be parsed becomes [].
    """
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        # pgvector text format: "[0.1,0.2,...]"
        try:
            parsed = json.loads(s)
        except Exception:
            try:
                inner = s.strip("[]() ").strip()
                if not inner:
                    return []
                parsed = [p.strip() for p in inner.split(",") if p.strip()]
            except Exception:
                return []
        if isinstance(parsed, list):
            out: List[float] = []
            for x in parsed:
                try:
                    out.append(float(x))
                except (TypeError, ValueError):
                    return []
            return out
        return []
    if isinstance(v, (list, tuple)):
        out2: List[float] = []
        for x in v:
            try:
                out2.append(float(x))
            except (TypeError, ValueError):
                return []
        return out2
    # numpy / other iterables
    try:
        return [float(x) for x in list(v)]
    except Exception:
        return []


def cosine(a: Any, b: Any) -> float:
    a = coerce_vector(a)
    b = coerce_vector(b)
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def centroid(vecs: Sequence[Any]) -> List[float]:
    cleaned: List[List[float]] = []
    dim: Optional[int] = None
    for raw in vecs or []:
        v = coerce_vector(raw)
        if not v:
            continue
        if dim is None:
            dim = len(v)
        if len(v) != dim:
            continue
        cleaned.append(v)
    if not cleaned or dim is None:
        return []
    out = [0.0] * dim
    for v in cleaned:
        for i in range(dim):
            out[i] += v[i]
    n = float(len(cleaned))
    return [x / n for x in out]
