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
import math
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
    """
    Asymmetric coverage: for each sentence in r1, find best match in r2.
    Returns mean best-match similarity (0–1).
    """
    sents1 = _tokenise(r1) or [r1]
    sents2 = _tokenise(r2) or [r2]

    scores: list[float] = []
    for s1 in sents1:
        kw1 = _keywords(s1)
        best = max((_jaccard(kw1, _keywords(s2)) for s2 in sents2), default=0.0)
        scores.append(best)

    return sum(scores) / len(scores) if scores else 0.0

def _symmetric_similarity(r1: str, r2: str) -> float:
    """Mean of both directions."""
    return (_response_similarity(r1, r2) + _response_similarity(r2, r1)) / 2

def _extract_consensus_claims(responses: list[str], threshold: float = 0.5) -> list[str]:
    """
    Find sentences from the 'best' response that are echoed in at least
    `threshold` fraction of the other responses.
    """
    if len(responses) < 2:
        return _tokenise(responses[0]) if responses else []

    # Use response[0] as primary source (it will be the best-overlap one)
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
    """Higher-tier models get more weight in the consensus score."""
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
    api_key: str | None,
    max_tokens: int = 1024,
) -> dict[str, Any]:
    """Call a single model and return its response text + metadata."""
    try:
        provider_obj = registry.get_provider(provider)
        if not provider_obj:
            return {"model_id": model_id, "provider": provider, "text": None,
                    "error": f"Provider '{provider}' not found", "tokens": 0}

        if api_key:
            provider_obj.set_api_key(api_key)

        full_text = ""
        usage = {"input_tokens": 0, "output_tokens": 0}

        async for chunk in provider_obj.stream_chat(
            messages=messages,
            model=model_id,
            max_tokens=max_tokens,
            system="You are a precise, factual AI assistant. Answer the question thoroughly and accurately.",
        ):
            if chunk.get("type") == "text":
                full_text += chunk.get("text", "")
            elif chunk.get("type") == "usage":
                usage = chunk.get("usage", usage)

        return {
            "model_id": model_id,
            "provider": provider,
            "text": full_text.strip(),
            "error": None,
            "tokens": usage.get("output_tokens", 0),
        }
    except Exception as e:
        logger.warning(f"Consensus: model {model_id} failed: {e}")
        return {"model_id": model_id, "provider": provider, "text": None,
                "error": str(e), "tokens": 0}


async def run_consensus(
    registry,
    model_configs: list[dict],   # [{"model_id": "...", "provider": "...", "api_key": "..."}]
    messages: list[dict],
    max_tokens: int = 1024,
    majority_threshold: float = 0.5,
) -> dict[str, Any]:
    """
    Run the same messages through multiple models in parallel.
    Return a ConsensusResult dict.

    ConsensusResult schema:
    {
      "consensus_score":    float (0-100),
      "confidence_label":   "high" | "medium" | "low" | "divergent",
      "best_response":      str,
      "synthesised_claims": list[str],
      "model_results": [
        {
          "model_id":      str,
          "provider":      str,
          "text":          str | None,
          "error":         str | None,
          "agreement_score": float (0-100),
          "tokens":        int,
        }
      ],
      "agreement_matrix":  list[list[float]],  # N×N similarity grid
      "models_agreed":     int,
      "models_total":      int,
      "divergence_warning": bool,
    }
    """
    if not model_configs:
        return {"error": "No models specified"}

    # 1. Call all models in parallel
    tasks = [
        _call_model(
            registry,
            cfg["model_id"],
            cfg["provider"],
            messages,
            cfg.get("api_key"),
            max_tokens,
        )
        for cfg in model_configs
    ]
    raw_results: list[dict] = await asyncio.gather(*tasks)

    # 2. Separate successful vs failed
    succeeded = [r for r in raw_results if r["text"]]
    failed    = [r for r in raw_results if not r["text"]]

    if not succeeded:
        return {
            "consensus_score": 0,
            "confidence_label": "divergent",
            "best_response": "All models failed to respond.",
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

    # 3. Build pairwise similarity matrix
    matrix: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i][j] = 1.0
            elif j > i:
                sim = _symmetric_similarity(texts[i], texts[j])
                matrix[i][j] = sim
                matrix[j][i] = sim

    # 4. Per-model agreement score (weighted mean similarity to others)
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

    # 5. Overall consensus score (weighted by tier)
    total_w   = 0.0
    weighted  = 0.0
    for i, score in enumerate(model_agreement):
        w = _model_tier_weight(model_ids[i])
        weighted += score * w
        total_w  += w
    raw_consensus = (weighted / total_w) if total_w > 0 else 0.0
    consensus_score = round(raw_consensus * 100, 1)

    # 6. Best response = model with highest agreement score
    best_idx = model_agreement.index(max(model_agreement))
    best_response = texts[best_idx]
    best_model    = model_ids[best_idx]

    # Reorder: put best first for claim extraction
    ordered_texts = [texts[best_idx]] + [t for k, t in enumerate(texts) if k != best_idx]

    # 7. Synthesise consensus claims
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
        if r["text"]:
            enriched.append({
                **r,
                "agreement_score": round(model_agreement[agg_idx] * 100, 1),
                "is_best": agg_idx == best_idx,
            })
            agg_idx += 1
        else:
            enriched.append({**r, "agreement_score": 0.0, "is_best": False})

    # Models that agree above 50%
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
