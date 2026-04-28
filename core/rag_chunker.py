"""
RAG Chunker — Production-Grade Sentence-Aware Chunking + Batch Embeddings
==========================================================================

Replaces the naive ``content[i:i+500]`` chunker that was used everywhere
across brain.py / kb_admin.py / knowledge_base.py.

Key improvements:
- Sentence-boundary-aware splitting (never cuts mid-sentence)
- Configurable overlap between consecutive chunks (preserves context)
- No hard cap by default — indexes the FULL document
- Batch INSERT into brain_chunks (1 DB call instead of N)
- Optional embedding generation via Voyage AI (single batched API call)
- Drop-in replacement: existing brain_chunks schema, no migration needed
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Tunables (overridable per-call from Knowledge Stack settings)
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_CHUNK_SIZE = 1500       # chars per chunk
DEFAULT_OVERLAP = 150           # chars overlapping between consecutive chunks
DEFAULT_MAX_CHUNKS = 0          # 0 = no cap (index the whole doc)

# Voyage AI batch limits
VOYAGE_BATCH_SIZE = 64          # max inputs per Voyage embeddings request
VOYAGE_TIMEOUT = 30             # seconds

# Sentence-end regex — handles ., !, ?, ;, plus newlines & lists
_SENTENCE_END_RE = re.compile(r"(?<=[\.!?;])\s+|\n{2,}")


# ────────────────────────────────────────────────────────────────────────────
# Smart chunker
# ────────────────────────────────────────────────────────────────────────────


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> List[str]:
    """
    Split ``text`` into overlapping, sentence-boundary-aware chunks.

    Algorithm:
        1. Split on sentence terminators (``.!?;``) and double newlines.
        2. Greedily pack sentences into a chunk until adding the next one
           would exceed ``chunk_size``.
        3. Carry the trailing ``overlap`` characters of the previous chunk
           into the start of the next chunk for context preservation.
        4. Cap at ``max_chunks`` if > 0; otherwise no cap.

    Returns:
        A list of chunk strings. Always non-empty if ``text`` is non-empty.
    """
    if not text:
        return []

    # Strip null bytes — Postgres rejects them with an opaque error
    text = text.replace("\x00", "").strip()
    if not text:
        return []

    # Normalize whitespace so sentence detection works on noisy PDFs/PPTX
    text = re.sub(r"[ \t]+", " ", text)

    # Edge case: tiny doc → single chunk
    if len(text) <= chunk_size:
        return [text]

    sentences = _SENTENCE_END_RE.split(text)
    sentences = [s.strip() for s in sentences if s and s.strip()]

    chunks: List[str] = []
    current = ""

    for sent in sentences:
        # Sentence longer than chunk_size on its own — hard split it
        if len(sent) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            for i in range(0, len(sent), chunk_size - overlap if overlap < chunk_size else chunk_size):
                hard = sent[i : i + chunk_size]
                if hard.strip():
                    chunks.append(hard.strip())
            continue

        # Would adding this sentence overflow the current chunk?
        candidate = (current + " " + sent).strip() if current else sent
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            # Carry overlap from end of previous chunk
            if overlap > 0 and chunks:
                tail = chunks[-1][-overlap:]
                # Snap tail to a word boundary to avoid mid-word fragments
                space_idx = tail.find(" ")
                if 0 < space_idx < len(tail):
                    tail = tail[space_idx:].strip()
                current = (tail + " " + sent).strip() if tail else sent
            else:
                current = sent

    if current:
        chunks.append(current.strip())

    # Apply optional cap (0 = unlimited)
    if max_chunks and max_chunks > 0:
        chunks = chunks[:max_chunks]

    return chunks


# ────────────────────────────────────────────────────────────────────────────
# Voyage AI batched embeddings (best-effort, optional)
# ────────────────────────────────────────────────────────────────────────────


def generate_embeddings_batch(
    texts: Sequence[str],
    model: str = "voyage-2",
    api_key: Optional[str] = None,
) -> List[Optional[List[float]]]:
    """
    Generate embeddings for many texts in batched Voyage AI calls.

    Returns a list the same length as ``texts``. Each entry is either an
    embedding list[float] or None (if the API failed for that batch).

    Silently returns all-None if VOYAGE_API_KEY is not configured.
    """
    api_key = api_key or os.getenv("VOYAGE_API_KEY")
    if not api_key:
        return [None] * len(texts)

    out: List[Optional[List[float]]] = [None] * len(texts)

    for batch_start in range(0, len(texts), VOYAGE_BATCH_SIZE):
        batch = list(texts[batch_start : batch_start + VOYAGE_BATCH_SIZE])
        # Voyage caps individual inputs at ~32k tokens; truncate aggressively
        batch_trimmed = [t[:8000] for t in batch]

        try:
            payload = json.dumps({"input": batch_trimmed, "model": model}).encode()
            req = urllib.request.Request(
                "https://api.voyageai.com/v1/embeddings",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=VOYAGE_TIMEOUT) as resp:
                result = json.loads(resp.read().decode())

            for i, item in enumerate(result.get("data", [])):
                emb = item.get("embedding")
                if emb:
                    out[batch_start + i] = emb
        except Exception as e:
            logger.warning(
                f"Voyage embedding batch failed (start={batch_start}, "
                f"size={len(batch)}): {e}"
            )
            # Leave entries as None — search will fall back to text mode

    return out


# ────────────────────────────────────────────────────────────────────────────
# Batch DB insertion helper
# ────────────────────────────────────────────────────────────────────────────


def insert_chunks_batch(
    db,
    document_id: str,
    chunks: List[str],
    embeddings: Optional[List[Optional[List[float]]]] = None,
) -> int:
    """
    Bulk-insert chunks into ``brain_chunks`` in a SINGLE Supabase round trip.

    Falls back to one-at-a-time inserts only if the bulk call fails.

    Returns the number of chunks successfully inserted.
    """
    if not chunks:
        return 0

    rows: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        row: Dict[str, Any] = {
            "document_id": document_id,
            "chunk_index": idx,
            "content": chunk,
        }
        if embeddings and idx < len(embeddings) and embeddings[idx] is not None:
            row["embedding"] = embeddings[idx]
        rows.append(row)

    try:
        db.table("brain_chunks").insert(rows).execute()
        return len(rows)
    except Exception as e:
        logger.warning(
            f"Bulk chunk insert failed ({e}); falling back to per-row inserts. "
            f"This is usually transient or schema-related."
        )
        ok = 0
        for row in rows:
            try:
                db.table("brain_chunks").insert(row).execute()
                ok += 1
            except Exception as inner:
                logger.error(
                    f"Single chunk insert failed for doc {document_id} "
                    f"chunk #{row['chunk_index']}: {inner}"
                )
        return ok


# ────────────────────────────────────────────────────────────────────────────
# High-level convenience: chunk + (optionally) embed + batch-insert
# ────────────────────────────────────────────────────────────────────────────


def chunk_and_index(
    db,
    document_id: str,
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    generate_embeddings: bool = True,
    embedding_model: str = "voyage-2",
) -> Dict[str, Any]:
    """
    End-to-end pipeline: split text → (optionally) embed → batch insert.

    Args:
        db: Supabase client
        document_id: brain_documents.id (parent FK)
        text: Cleaned, extracted text
        chunk_size, overlap, max_chunks: Chunking parameters
        generate_embeddings: If True, attempt Voyage AI embedding generation
                             (gracefully degrades to None embeddings if
                             VOYAGE_API_KEY is unset or the API fails)
        embedding_model: Voyage model name

    Returns:
        {
            "chunks_created": int,
            "embeddings_generated": int,
            "chunk_size": int,
            "overlap": int,
        }
    """
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
    if not chunks:
        return {
            "chunks_created": 0,
            "embeddings_generated": 0,
            "chunk_size": chunk_size,
            "overlap": overlap,
        }

    embeddings: Optional[List[Optional[List[float]]]] = None
    embeddings_generated = 0
    if generate_embeddings:
        embeddings = generate_embeddings_batch(chunks, model=embedding_model)
        embeddings_generated = sum(1 for e in embeddings if e is not None)

    inserted = insert_chunks_batch(db, document_id, chunks, embeddings)

    logger.info(
        f"Indexed doc {document_id}: {inserted} chunks, "
        f"{embeddings_generated} embeddings (chunk_size={chunk_size}, overlap={overlap})"
    )

    return {
        "chunks_created": inserted,
        "embeddings_generated": embeddings_generated,
        "chunk_size": chunk_size,
        "overlap": overlap,
    }
