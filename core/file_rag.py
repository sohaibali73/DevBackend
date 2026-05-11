"""
File RAG — "Chat with Documents"
=================================

Per-conversation Retrieval-Augmented Generation over user-uploaded files.

Pipeline:
    1. After upload + text extraction (api/routes/upload.py background task),
       call ``index_file_chunks(file_id, text)`` to chunk + embed + persist
       to the ``file_chunks`` table.
    2. On every chat turn (api/routes/chat.py), call
       ``retrieve_relevant_chunks(conversation_id, user_query)`` to fetch the
       top-k semantically similar chunks across all files linked to the
       conversation, formatted as a ready-to-inject system prompt block.

Gracefully degrades when:
    - VOYAGE_API_KEY is unset → falls back to keyword-LIKE search
    - file_chunks / RPC missing  → returns empty string (chat still works)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from core.rag_chunker import (
    chunk_text,
    generate_embeddings_batch,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Indexing
# ────────────────────────────────────────────────────────────────────────────
def index_file_chunks(
    db,
    file_id: str,
    text: str,
    chunk_size: int = 1200,
    overlap: int = 150,
    embedding_model: str = "voyage-2",
) -> Dict[str, Any]:
    """
    Chunk + (best-effort) embed the extracted text of an uploaded file
    and bulk-insert into ``file_chunks``.

    Idempotent: deletes any prior chunks for ``file_id`` before re-inserting,
    so calling this on re-upload / re-extract is safe.
    """
    if not text or not text.strip():
        return {"chunks_created": 0, "embeddings_generated": 0}

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap, max_chunks=0)
    if not chunks:
        return {"chunks_created": 0, "embeddings_generated": 0}

    # Wipe stale rows so reruns don't double-index
    try:
        db.table("file_chunks").delete().eq("file_id", file_id).execute()
    except Exception as e:
        logger.debug(f"file_chunks pre-delete (non-fatal) for {file_id}: {e}")

    # Best-effort batch embeddings (None entries OK — we'll still text-search)
    embeddings = generate_embeddings_batch(chunks, model=embedding_model)
    embeddings_ok = sum(1 for e in embeddings if e is not None)

    rows: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        row: Dict[str, Any] = {
            "file_id": file_id,
            "chunk_index": idx,
            "content": chunk,
        }
        if idx < len(embeddings) and embeddings[idx] is not None:
            row["embedding"] = embeddings[idx]
        rows.append(row)

    inserted = 0
    try:
        # Bulk insert in one round trip
        db.table("file_chunks").insert(rows).execute()
        inserted = len(rows)
    except Exception as e:
        logger.warning(
            f"Bulk insert into file_chunks failed for {file_id} ({e}); "
            f"falling back to per-row inserts"
        )
        for row in rows:
            try:
                db.table("file_chunks").insert(row).execute()
                inserted += 1
            except Exception as inner:
                logger.error(f"Single chunk insert failed for {file_id}: {inner}")

    logger.info(
        f"Indexed file {file_id}: {inserted} chunks, {embeddings_ok} embeddings"
    )
    return {"chunks_created": inserted, "embeddings_generated": embeddings_ok}


# ────────────────────────────────────────────────────────────────────────────
# Retrieval
# ────────────────────────────────────────────────────────────────────────────
_MAX_CHARS_PER_CHUNK = 1800
_MAX_TOTAL_CHARS     = 14000   # ~3.5k tokens of retrieved context


def _embed_query(query: str, model: str = "voyage-2") -> Optional[List[float]]:
    """Embed a single query string. Returns None if Voyage is unavailable."""
    if not query.strip():
        return None
    embeddings = generate_embeddings_batch([query], model=model)
    return embeddings[0] if embeddings and embeddings[0] is not None else None


def _vector_search(db, conversation_id: str, query_vec: List[float],
                   top_k: int, threshold: float) -> List[Dict[str, Any]]:
    """Call the match_conversation_file_chunks RPC."""
    try:
        result = db.rpc(
            "match_conversation_file_chunks",
            {
                "p_conversation_id": conversation_id,
                "query_embedding":   query_vec,
                "match_threshold":   threshold,
                "match_count":       top_k,
            },
        ).execute()
        return result.data or []
    except Exception as e:
        logger.warning(f"match_conversation_file_chunks RPC failed: {e}")
        return []


def _keyword_fallback(db, conversation_id: str, query: str,
                      top_k: int) -> List[Dict[str, Any]]:
    """
    Crude BM25-less fallback when no embedding is available.
    Uses ILIKE on the longest keywords in the query.
    """
    # Extract candidate keywords (alpha tokens of length >= 4, dedup'd)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", query)
    if not tokens:
        return []
    seen, keywords = set(), []
    for t in tokens:
        lt = t.lower()
        if lt not in seen:
            seen.add(lt)
            keywords.append(t)
    keywords = keywords[:5]

    try:
        cf = db.table("conversation_files").select("file_id").eq(
            "conversation_id", conversation_id
        ).execute()
        file_ids = [r["file_id"] for r in (cf.data or []) if r.get("file_id")]
        if not file_ids:
            return []

        out: List[Dict[str, Any]] = []
        seen_chunk_ids: set = set()
        for kw in keywords:
            res = db.table("file_chunks").select(
                "id, file_id, chunk_index, content"
            ).in_("file_id", file_ids).ilike("content", f"%{kw}%").limit(top_k).execute()

            # Look up filenames in one shot
            ids_in_batch = list({r["file_id"] for r in (res.data or [])})
            fname_map: Dict[str, str] = {}
            if ids_in_batch:
                fu = db.table("file_uploads").select(
                    "id, original_filename"
                ).in_("id", ids_in_batch).execute()
                fname_map = {r["id"]: r.get("original_filename", "")
                             for r in (fu.data or [])}

            for r in res.data or []:
                if r["id"] in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(r["id"])
                out.append({
                    "chunk_id":    r["id"],
                    "file_id":     r["file_id"],
                    "filename":    fname_map.get(r["file_id"], ""),
                    "chunk_index": r["chunk_index"],
                    "content":     r["content"],
                    "similarity":  None,  # text mode → no score
                })
                if len(out) >= top_k:
                    break
            if len(out) >= top_k:
                break

        return out
    except Exception as e:
        logger.warning(f"Keyword fallback failed: {e}")
        return []


def retrieve_relevant_chunks(
    db,
    conversation_id: str,
    query: str,
    top_k: int = 8,
    threshold: float = 0.35,
) -> List[Dict[str, Any]]:
    """
    Return up to ``top_k`` most relevant chunks from files linked to this
    conversation, ranked by cosine similarity to the query.
    """
    if not query or not query.strip():
        return []

    query_vec = _embed_query(query)
    if query_vec:
        results = _vector_search(db, conversation_id, query_vec, top_k, threshold)
        if results:
            return results
        # Vector search returned nothing — try keyword fallback as a safety net
        logger.debug("Vector search returned 0 hits; trying keyword fallback")

    return _keyword_fallback(db, conversation_id, query, top_k)


def format_chunks_for_prompt(chunks: List[Dict[str, Any]]) -> str:
    """
    Render retrieved chunks into a system-prompt block that Claude/GPT can
    cite. Truncates per-chunk and total to stay under a token budget.
    """
    if not chunks:
        return ""

    lines: List[str] = []
    total = 0
    for c in chunks:
        body = (c.get("content") or "").strip()
        if not body:
            continue
        if len(body) > _MAX_CHARS_PER_CHUNK:
            body = body[:_MAX_CHARS_PER_CHUNK] + " …[truncated]"
        sim = c.get("similarity")
        sim_txt = f" (similarity {sim:.2f})" if isinstance(sim, (int, float)) else ""
        header = (
            f'From "{c.get("filename") or "uploaded file"}", '
            f'chunk {c.get("chunk_index", "?")}{sim_txt}:'
        )
        block = f"{header}\n{body}"
        if total + len(block) > _MAX_TOTAL_CHARS:
            break
        lines.append(block)
        total += len(block)

    if not lines:
        return ""

    body = "\n\n".join(lines)
    return (
        "\n\n<retrieved_document_context>\n"
        "The following passages were retrieved from documents the user has "
        "attached to this conversation. Use them to answer the question and "
        "cite the source filename when you do. Do not fabricate quotations.\n\n"
        f"{body}\n"
        "</retrieved_document_context>"
    )


def fetch_retrieved_doc_context(
    db,
    conversation_id: Optional[str],
    user_query: str,
    top_k: int = 8,
) -> str:
    """High-level helper: retrieve + format. Safe to call in any chat path."""
    if not conversation_id or not user_query:
        return ""
    try:
        chunks = retrieve_relevant_chunks(db, conversation_id, user_query, top_k=top_k)
        return format_chunks_for_prompt(chunks)
    except Exception as e:
        logger.warning(f"fetch_retrieved_doc_context failed (non-fatal): {e}")
        return ""
