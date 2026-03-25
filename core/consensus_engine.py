"""
consensus_engine.py
====================
Multi-model consensus validation engine.

Runs the same prompt through N models in parallel, scores agreement
between responses using lightweight NLP (no extra deps required), and
synthesises a validated answer with a confidence score.

Algorithm:
  1. Fire all selected models in parallel (asyncio.gather)
  2. Sentence-tokenise each response
  3. Build a pairwise Jaccard-similarity agreement matrix
  4. consensus_score  = mean of off-diagonal similarity values (0-100)
  5. best_response    = response with highest mean similarity to others
  6. Highlight claims agreed by ≥ majority_threshold of models
  7. Return structured ConsensusResult
"""

from __future__ import annotations
import asyncio
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ─── simple text helpers ──────────────────────────────────────────────────────

_STOP_WORDS = {
    "a","an","the","is","are","was","were","be","been","being",
    "have","has","had","do","does","did","will","would","could",
    "should","may","might","shall","can","need","dare","ought",
    "used","to","of","in","on","at","by","for","with","about",
    "against","between","through","during","before","after",
    "above","below","from","up","down","out","off","over","under",
    "and","but","or","nor","so","yet","for","because","since",
    "while","although","though","if","unless","until","when",
    "where","who","which","that","this","these","those","it","its",
    "i","you","he","she","we","they","me","him","her","us","them",
    "my","your","his","our","their","what","how","all","both",
    "each","few","more","most","other","some","such","no","not",
    "only","own","same","than","too","very","s","just","into",
}

def _tokenise(text: str) -> list[str]:
    """Split text into sentences."""
    text = text.strip()
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if len(p.strip()) > 20]

def _keywords(sentence: str) -> frozenset[str]:
    """Extract meaningful keywords from a sentence."""
    words = re.findall(r'\b[a-z]{3,}\b', sentence.lower())
    return frozenset(w for w in words if w not in _STOP_WORDS)

def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity between two keyword sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)

def _sentence_similarity(s1: str, s2: str) -> float:
    return _jaccard(_keywords(s1), _keywords(s2))

def _response_similarity(r1: str, r2: str) -> float:
    sents1 = _tokenise(r1) or [r1]
    sents2 = _tokenise(r2) or [r2]
    scores: list[float] = []
    for s1 in sents1:
        kw1 = _keywords(s1)
        best = max((_jaccard(kw1, _keywords(s2)) for s2 in sents2), default=0.0)
        scores.append(best)
    return sum(scores) / len(scores) if scores else 0.0

def _symmetric_similarity(r1: str, r2: str) -> float:
    return (_response_similarity(r1, r2) + _response_similarity(r2, r1)) / 2

def _extract_consensus_claims(responses: list[str], threshold: float = 0.5) -> list[str]:
    if len(responses) < 2:
        return _tokenise(responses[0]) if responses else []
    primary_sents = _tokenise(responses[0])
    others = responses[1:]
    if not others:
        return primary_sents
    consensus: list[str] = []
    for sent in primary_sents:
        kw = _keywords(sent)
        agree_count = sum(
            1 for other in others
            if max((_jaccard(kw, _keywords(os)) for os in (_tokenise(other) or [other])), default=0.0) >= 0.35
        )
        if agree_count / len(others) >= threshold:
            consensus.append(sent)
    return consensus if consensus else primary_sents[:3]

# ─── tier weighting ──────────────────────────────────────────────────────────

def _model_tier_weight(model_id: str) -> float:
    lower = model_id.lower()
    if any(k in lower for k in ("o1","o3","r1","reasoning","think","opus","405b")):
        return 1.5
    if any(k in lower for k in ("sonnet","gpt-4o","large","pro","70b")):
        return 1.2
    if any(k in lower for k in ("haiku","mini","flash","8b","small","micro")):
        return 0.8
    return 1.0

# ─── main engine ─────────────────────────────────────────────────────────────

async def _call_model(
    registry,
    model_id: str,
    provider: str,
    messages: list[dict],
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """
    Call a single model and return its response text + metadata.

    Uses the registry's pre-initialized provider (with server-side API key).
    StreamChunk is a dataclass — access via .type / .content / .usage attributes.
    """
    try:
        provider_obj = registry.get_provider(provider)
        if not provider_obj:
            # Try resolving by model string (handles prefix matching)
            try:
                provider_obj = registry.get_provider_for_model(model_id)
            except Exception:
                pass

        if not provider_obj:
            return {
                "model_id": model_id, "provider": provider,
                "text": None, "tokens": 0,
                "error": f"Provider '{provider}' not found in registry. "
                         f"Available: {registry.list_providers()}",
            }

        full_text = ""
        usage: dict = {"input_tokens": 0, "output_tokens": 0}

        async for chunk in provider_obj.stream_chat(
            messages=messages,
            model=model_id,
            max_tokens=max_tokens,
            system=(
                "You are a precise, factual AI assistant. "
                "Answer the question thoroughly and accurately."
            ),
        ):
            # StreamChunk is a dataclass — use attribute access, NOT dict.get()
            chunk_type = getattr(chunk, "type", None) or chunk.get("type", "") if isinstance(chunk, dict) else chunk.type
            if chunk_type == "text":
                content = getattr(chunk, "content", "") if not isinstance(chunk, dict) else chunk.get("content", chunk.get("text", ""))
                full_text += content
            elif chunk_type == "finish":
                raw_usage = getattr(chunk, "usage", {}) if not isinstance(chunk, dict) else chunk.get("usage", {})
                if raw_usage:
                    usage = raw_usage

        text_out = full_text.strip() or None
        return {
            "model_id": model_id,
            "provider": provider,
            "text": text_out,
            "error": None if text_out else "Empty response",
            "tokens": usage.get("output_tokens", 0) if isinstance(usage, dict) else 0,
        }

    except Exception as e:
        logger.warning(f"Consensus: model {model_id} ({provider}) failed: {e}", exc_info=True)
        return {
            "model_id": model_id, "provider": provider,
            "text": None, "error": str(e), "tokens": 0,
        }


async def run_consensus(
    registry,
    model_configs: list[dict],   # [{"model_id": "...", "provider": "..."}]
    messages: list[dict],
    max_tokens: int = 1024,
    majority_threshold: float = 0.5,
) -> dict[str, Any]:
    """
    Run the same messages through multiple models in parallel.
    The registry must already be initialized with valid API keys.
    """
    if not model_configs:
        return {"error": "No models specified"}

    # 1. Call all models in parallel
    tasks = [
        _call_model(registry, cfg["model_id"], cfg["provider"], messages, max_tokens)
        for cfg in model_configs
    ]
    raw_results: list[dict] = await asyncio.gather(*tasks)

    # 2. Separate successful vs failed
    succeeded = [r for r in raw_results if r.get("text")]
    failed    = [r for r in raw_results if not r.get("text")]

    logger.info(
        f"Consensus: {len(succeeded)} succeeded, {len(failed)} failed "
        f"out of {len(raw_results)} models"
    )

    if not succeeded:
        errors = [f"{r['model_id']}: {r.get('error','unknown')}" for r in raw_results]
        return {
            "consensus_score": 0,
            "confidence_label": "divergent",
            "best_response": f"All models failed to respond. Errors: {'; '.join(errors)}",
            "best_model": "",
            "synthesised_claims": [],
            "model_results": raw_results,
            "agreement_matrix": [],
            "models_agreed": 0,
            "models_total": len(raw_results),
            "divergence_warning": True,
            "error": "All models failed",
        }

    texts = [r["text"] for r in succeeded]
    model_ids = [r["model_id"] for r in succeeded]
    n = len(texts)

    # 3. Single model — no comparison possible
    if n == 1:
        return {
            "consensus_score": 100.0,
            "confidence_label": "high",
            "best_response": texts[0],
            "best_model": model_ids[0],
            "synthesised_claims": _tokenise(texts[0])[:5],
            "model_results": [{**succeeded[0], "agreement_score": 100.0, "is_best": True}]
                             + [{**r, "agreement_score": 0.0, "is_best": False} for r in failed],
            "agreement_matrix": [[1.0]],
            "models_agreed": 1,
            "models_total": len(raw_results),
            "divergence_warning": False,
        }

    # 4. Build pairwise similarity matrix
    matrix: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 1.0
            elif j > i:
                sim = _symmetric_similarity(texts[i], texts[j])
                matrix[i][j] = sim
                matrix[j][i] = sim

    # 5. Per-model agreement score (weighted mean similarity to others)
    model_agreement: list[float] = []
    for i in range(n):
        weight_sum   = 0.0
        weighted_sim = 0.0
        for j in range(n):
            if i == j:
                continue
            w = _model_tier_weight(model_ids[j])
            weighted_sim += matrix[i][j] * w
            weight_sum   += w
        score = (weighted_sim / weight_sum) if weight_sum > 0 else 0.0
        model_agreement.append(score)

    # 6. Overall consensus score
    total_w   = 0.0
    weighted  = 0.0
    for i, score in enumerate(model_agreement):
        w = _model_tier_weight(model_ids[i])
        weighted += score * w
        total_w  += w
    raw_consensus = (weighted / total_w) if total_w > 0 else 0.0
    consensus_score = round(raw_consensus * 100, 1)

    # 7. Best response = model with highest agreement score
    best_idx = model_agreement.index(max(model_agreement))
    best_response = texts[best_idx]
    best_model    = model_ids[best_idx]

    ordered_texts = [texts[best_idx]] + [t for k, t in enumerate(texts) if k != best_idx]
    synthesised_claims = _extract_consensus_claims(ordered_texts, majority_threshold)

    # 8. Confidence label
    if consensus_score >= 75:
        confidence_label = "high"
    elif consensus_score >= 50:
        confidence_label = "medium"
    elif consensus_score >= 30:
        confidence_label = "low"
    else:
        confidence_label = "divergent"

    divergence_warning = consensus_score < 50

    # 9. Build enriched model_results
    enriched: list[dict] = []
    agg_idx = 0
    for r in raw_results:
        if r.get("text"):
            enriched.append({
                **r,
                "agreement_score": round(model_agreement[agg_idx] * 100, 1),
                "is_best": agg_idx == best_idx,
            })
            agg_idx += 1
        else:
            enriched.append({**r, "agreement_score": 0.0, "is_best": False})

    models_agreed = sum(1 for s in model_agreement if s >= 0.5)

    return {
        "consensus_score":    consensus_score,
        "confidence_label":   confidence_label,
        "best_response":      best_response,
        "best_model":         best_model,
        "synthesised_claims": synthesised_claims,
        "model_results":      enriched,
        "agreement_matrix":   [[round(v, 3) for v in row] for row in matrix],
        "models_agreed":      models_agreed,
        "models_total":       len(raw_results),
        "divergence_warning": divergence_warning,
    }
