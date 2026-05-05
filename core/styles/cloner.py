"""
Voice cloner — turn raw writing samples into a 1:1 reproducible voice.

The cloner runs three steps:

  1. INGEST     — chunk samples, compute per-sample stats + embedding,
                  save raw text on the Railway volume.
  2. ANALYZE    — ask Claude (with full samples in context) to extract a
                  qualitative voice card: voice/tone/lexicon/structure/rhetoric.
                  We combine that with quantitative stats from `stats.py`.
  3. EXEMPLARS  — pick 8–12 most-characteristic passages (highest signature
                  fingerprint density / centroid distance) for few-shot.

The system_prompt is then built by `injector.py` from voice_card + exemplars.

This module is fail-safe: if the Anthropic key is missing or the LLM call
fails, we still produce a usable voice card from quantitative stats alone
and return status='ready' (with a warning in meta). The user can re-run
analyze when keys/quota are available.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from core.styles import embeddings as emb
from core.styles import stats as stx
from core.styles.injector import build_system_prompt

logger = logging.getLogger(__name__)


STORAGE_ROOT = os.getenv("STORAGE_ROOT", "/data")


# -----------------------------------------------------------------------------
# Volume helpers
# -----------------------------------------------------------------------------

def style_dir(style_id: str) -> str:
    p = os.path.join(STORAGE_ROOT, "styles", style_id)
    os.makedirs(os.path.join(p, "samples"), exist_ok=True)
    return p


def _save_sample_to_volume(style_id: str, sample_id: str, text: str) -> str:
    path = os.path.join(style_dir(style_id), "samples", f"{sample_id}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")
    return path


def _save_voice_card(style_id: str, voice_card: Dict[str, Any]) -> str:
    path = os.path.join(style_dir(style_id), "voice_card.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(voice_card, f, ensure_ascii=False, indent=2)
    return path


# -----------------------------------------------------------------------------
# DB helpers
# -----------------------------------------------------------------------------

def _db():
    from db.supabase_client import get_supabase
    return get_supabase()


# -----------------------------------------------------------------------------
# Sample ingest
# -----------------------------------------------------------------------------

def ingest_sample(
    *,
    user_id: str,
    style_id: str,
    text: str,
    title: str = "",
    source: str = "paste",
    source_url: Optional[str] = None,
    source_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert one sample row + save text to volume + compute stats/embedding."""
    if not (text or "").strip():
        raise ValueError("sample text is empty")

    db = _db()

    sample_stats = stx.stats(text)
    vec = emb.embed(text)

    row = {
        "style_id":      style_id,
        "user_id":       user_id,
        "title":         title or text[:60],
        "source":        source,
        "source_url":    source_url,
        "source_file_id": source_file_id,
        "text":          text,
        "word_count":    sample_stats.get("word_count", 0),
        "char_count":    sample_stats.get("char_count", 0),
        "stats":         sample_stats,
        "embedding":     vec,
    }

    res = db.table("studio_writing_style_samples").insert(row).execute()
    if not res.data:
        raise RuntimeError("failed to insert sample")

    sample = res.data[0]
    # Save raw text on volume now that we have an id
    try:
        path = _save_sample_to_volume(style_id, sample["id"], text)
        db.table("studio_writing_style_samples").update({"volume_path": path}).eq(
            "id", sample["id"]
        ).execute()
        sample["volume_path"] = path
    except Exception as e:
        logger.warning("could not save sample to volume: %s", e)

    return sample


def list_samples(style_id: str, user_id: str) -> List[Dict[str, Any]]:
    db = _db()
    res = (
        db.table("studio_writing_style_samples")
        .select("id, title, source, source_url, source_file_id, word_count, char_count, stats, created_at")
        .eq("style_id", style_id)
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .execute()
    )
    return res.data or []


def delete_sample(sample_id: str, user_id: str) -> bool:
    db = _db()
    # remove file on volume best-effort
    try:
        row = (
            db.table("studio_writing_style_samples")
            .select("style_id, volume_path")
            .eq("id", sample_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if row.data and row.data[0].get("volume_path"):
            p = row.data[0]["volume_path"]
            try:
                os.remove(p)
            except OSError:
                pass
    except Exception:
        pass
    db.table("studio_writing_style_samples").delete().eq("id", sample_id).eq(
        "user_id", user_id
    ).execute()
    return True


# -----------------------------------------------------------------------------
# Analyzer (Claude)
# -----------------------------------------------------------------------------

_ANALYZER_PROMPT = """You are a forensic linguistic analyst building a "voice card" for a 1:1 voice clone.

Read the writing samples below. Produce a JSON object — and ONLY a JSON object,
no prose, no code fences — with this exact shape:

{
  "voice": {
    "register":       "<one of: very_casual|casual|conversational|business_casual|formal|academic>",
    "formality":      <int 0..10>,
    "warmth":         <int 0..10>,
    "authority":      <int 0..10>,
    "humor":          <int 0..10>,
    "certainty":      <int 0..10>,
    "perspective":    "<one of: first_person|second_person|third_person|mixed>"
  },
  "lexicon": {
    "signature_phrases": ["<exact phrases the author uses repeatedly, max 30>"],
    "avoided_words":     ["<words the author never seems to use>"],
    "jargon_density":    "<low|medium|high>",
    "favored_verbs":     ["<verbs they reach for>"]
  },
  "structure": {
    "opening_patterns":   ["<how their pieces/paragraphs start>"],
    "closing_patterns":   ["<how their pieces/paragraphs end>"],
    "paragraph_shape":    "<short_punchy|medium|long_flowing|mixed>",
    "transitions":        ["<how they connect ideas>"]
  },
  "rhetoric": {
    "devices":            ["<rhetorical moves they use, e.g. anaphora, listing, asides>"],
    "argumentation":      "<descriptive sentence>",
    "storytelling":       "<descriptive sentence>"
  },
  "idiolect": {
    "discourse_markers":  ["<look,, honestly,, the thing is,, etc.>"],
    "punctuation_quirks": ["<em-dash usage, parentheticals, etc.>"],
    "unusual_constructions": ["<recognizable structural moves>"]
  },
  "do_rules":  ["<bullet rules an impersonator MUST follow to sound like this person>"],
  "dont_rules":["<bullet rules an impersonator must NOT do>"],
  "summary":   "<one short paragraph capturing the voice in plain English>"
}

Be specific. Quote actual phrases. Be ruthless about the "avoid" list.

==== SAMPLES ====
{SAMPLES}
==== END SAMPLES ====

Return ONLY the JSON object.
"""


def _build_samples_block(samples: List[Dict[str, Any]], max_chars: int = 60_000) -> str:
    """Concatenate samples into a single bounded block for the analyzer."""
    out: List[str] = []
    used = 0
    for i, s in enumerate(samples, start=1):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        title = s.get("title") or f"Sample {i}"
        block = f"\n--- Sample {i}: {title} ---\n{text}\n"
        if used + len(block) > max_chars:
            block = block[: max_chars - used]
            out.append(block)
            break
        out.append(block)
        used += len(block)
    return "".join(out)


def _call_claude_for_voice_card(
    samples_block: str,
    api_key: str,
    *,
    model: str = "claude-sonnet-4-20250514",
) -> Optional[Dict[str, Any]]:
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = _ANALYZER_PROMPT.replace("{SAMPLES}", samples_block)
        msg = client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        text = ""
        for block in msg.content:
            if getattr(block, "type", "") == "text":
                text += block.text
        text = text.strip()
        # Strip code-fence remnants if Claude was finicky
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        return json.loads(text)
    except Exception as e:
        logger.warning("voice-card analyzer LLM call failed: %s", e)
        return None


# -----------------------------------------------------------------------------
# Exemplar selection
# -----------------------------------------------------------------------------

def _select_exemplars(
    samples: List[Dict[str, Any]],
    *,
    target: int = 10,
    max_chars_each: int = 800,
) -> List[Dict[str, Any]]:
    """
    Pick the most "characteristic" passages by:
      1. Splitting each sample into 200–800-char chunks at sentence boundaries
      2. Scoring each chunk by:
         - distance from sample centroid (more distinctive)
         - length within band (prefer mid-length)
      3. Returning top-N chunks across all samples
    """
    if not samples:
        return []

    # Build chunks
    chunks: List[Dict[str, Any]] = []
    for s in samples:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        sents = stx.split_sentences(text)
        cur = ""
        for sent in sents:
            if not cur:
                cur = sent
            elif len(cur) + 1 + len(sent) <= max_chars_each:
                cur = cur + " " + sent
            else:
                chunks.append({"text": cur, "from_sample": s.get("id")})
                cur = sent
        if cur:
            chunks.append({"text": cur, "from_sample": s.get("id")})

    if not chunks:
        return []

    # Embed chunks + compute centroid
    vecs = emb.embed_many([c["text"] for c in chunks])
    cent = emb.centroid(vecs)

    # Score: distance from centroid (1 - cos) + length in [200, 600] band bonus
    for c, v in zip(chunks, vecs):
        dist = 1.0 - emb.cosine(v, cent)
        L = len(c["text"])
        len_score = 1.0 if 200 <= L <= 600 else max(0.0, 1.0 - abs(L - 400) / 400.0)
        c["score"] = round(0.7 * dist + 0.3 * len_score, 4)

    chunks.sort(key=lambda x: x["score"], reverse=True)
    picked = chunks[: max(8, min(target, 12))]
    return [{"text": c["text"], "score": c["score"]} for c in picked]


# -----------------------------------------------------------------------------
# Top-level analyze
# -----------------------------------------------------------------------------

def analyze_style(
    *,
    user_id: str,
    style_id: str,
    api_key: Optional[str] = None,
    self_test: bool = True,
) -> Dict[str, Any]:
    """
    Build the voice_card + system_prompt for a style. Updates DB row.
    Returns the updated style row.
    """
    db = _db()

    # 0. Load style + samples
    style = (
        db.table("studio_writing_styles")
        .select("*")
        .eq("id", style_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not style.data:
        raise ValueError("style not found")
    style_row = style.data[0]

    samples_full = (
        db.table("studio_writing_style_samples")
        .select("id, title, text, stats, embedding")
        .eq("style_id", style_id)
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .execute()
    )
    samples = samples_full.data or []
    if not samples:
        raise ValueError("no samples — add samples before analyzing")

    db.table("studio_writing_styles").update({"status": "analyzing"}).eq("id", style_id).execute()

    # 1. Aggregate stats
    agg = stx.aggregate([s.get("stats") or {} for s in samples])

    # 2. LLM voice card
    samples_block = _build_samples_block(samples)
    qual = _call_claude_for_voice_card(samples_block, api_key or "")

    # 3. Combine into final voice_card
    voice_card: Dict[str, Any] = {
        "quantitative":  agg,
        "qualitative":   qual or {
            "voice":     {"register": "conversational", "formality": 5, "warmth": 5,
                          "authority": 5, "humor": 3, "certainty": 6,
                          "perspective": "first_person"},
            "lexicon":   {},
            "structure": {},
            "rhetoric":  {},
            "idiolect":  {},
            "do_rules":  [],
            "dont_rules":[],
            "summary":   "(LLM analysis unavailable — quantitative profile only)",
        },
    }

    # 4. Exemplars
    exemplars = _select_exemplars(samples)

    # 5. System prompt
    sys_prompt = build_system_prompt(
        name=style_row.get("name") or "the author",
        voice_card=voice_card,
        exemplars=exemplars,
    )

    # 6. Centroid embedding
    sample_vecs = [s.get("embedding") for s in samples if s.get("embedding")]
    avg_vec = emb.centroid([list(v) for v in sample_vecs]) if sample_vecs else emb.embed(samples_block[:5000])

    # 7. Self-test fidelity (optional, requires api_key)
    fidelity = None
    if self_test and api_key:
        fidelity = _self_test_fidelity(api_key, sys_prompt, samples)

    # 8. Persist
    voice_path = _save_voice_card(style_id, voice_card)

    update = {
        "status":         "ready",
        "voice_card":     voice_card,
        "system_prompt":  sys_prompt,
        "exemplars":      exemplars,
        "embedding":      avg_vec,
        "fidelity_score": fidelity,
        "meta": {
            **(style_row.get("meta") or {}),
            "voice_card_path": voice_path,
            "llm_used":        bool(qual),
        },
    }
    res = (
        db.table("studio_writing_styles")
        .update(update)
        .eq("id", style_id)
        .eq("user_id", user_id)
        .execute()
    )
    return res.data[0] if res.data else {**style_row, **update}


# -----------------------------------------------------------------------------
# Self-test fidelity
# -----------------------------------------------------------------------------

_SELFTEST_PROMPTS = [
    "Write a short opening (3 sentences) about why discipline beats motivation.",
    "Write a short LinkedIn-style hook (2 sentences) about a market lesson you learned.",
    "Write a short paragraph (3–5 sentences) explaining what 'edge' means to you.",
]


def _self_test_fidelity(
    api_key: str, system_prompt: str, samples: List[Dict[str, Any]],
    *, model: str = "claude-sonnet-4-20250514",
) -> float:
    """
    Generate 3 short outputs in the cloned voice and average their cosine
    similarity vs. the centroid of the original samples. 0..1.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except Exception:
        return 0.0

    sample_vecs = [list(s.get("embedding") or []) for s in samples if s.get("embedding")]
    if not sample_vecs:
        return 0.0
    cent = emb.centroid(sample_vecs)

    sims: List[float] = []
    for prompt in _SELFTEST_PROMPTS:
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=400,
                temperature=0.7,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            text = ""
            for block in msg.content:
                if getattr(block, "type", "") == "text":
                    text += block.text
            if not text.strip():
                continue
            v = emb.embed(text)
            sims.append(emb.cosine(v, cent))
        except Exception as e:
            logger.warning("self-test fidelity prompt failed: %s", e)
    if not sims:
        return 0.0
    return round(sum(sims) / len(sims), 4)


# -----------------------------------------------------------------------------
# Style lookup (used by injector when chat starts)
# -----------------------------------------------------------------------------

def get_style(style_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    db = _db()
    res = (
        db.table("studio_writing_styles")
        .select("*")
        .eq("id", style_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None
