"""
Individual humanizer passes.

Each pass is a function `(text, ctx) → text` plus a name. They are pure-ish
(side-effect: may call out to an LLM via core.humanize.llm.claude_rewrite).

Passes:
    fingerprint_scrub      — rule-based phrase substitution + punctuation tweaks
    burstiness_pass        — LLM rewrites for sentence-length variance
    perplexity_injection   — LLM rewrites with unexpected word choices
    style_transfer         — LLM rewrites in user's cloned voice
    linkedin_seo           — LinkedIn-style hook + cadence + hashtags + CTA
    fact_guard             — diff entities/numbers; revert any that mutated
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
from typing import Any, Dict, List, Optional

from core.humanize.llm import claude_rewrite
from core.styles import stats as stx

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Fingerprints (rule-based)
# -----------------------------------------------------------------------------

_FP_PATH = os.path.join(os.path.dirname(__file__), "fingerprints.json")
_FP_CACHE: Optional[Dict[str, Any]] = None


def _load_fingerprints() -> Dict[str, Any]:
    global _FP_CACHE
    if _FP_CACHE is not None:
        return _FP_CACHE
    try:
        with open(_FP_PATH, "r", encoding="utf-8") as f:
            _FP_CACHE = json.load(f)
    except Exception as e:
        logger.warning("Could not load fingerprints.json: %s", e)
        _FP_CACHE = {"phrases": [], "punctuation_rules": {}}
    return _FP_CACHE


def fingerprint_scrub(text: str, ctx: Dict[str, Any]) -> str:
    """
    Deterministic per-occurrence replacement of known AI-tell phrases,
    case-preserving, with a stable PRNG seeded by run_id (so re-runs are
    reproducible but distinct runs differ).
    """
    fp = _load_fingerprints()
    seed = ctx.get("seed") or 0
    rng = random.Random(seed)

    out = text
    for entry in fp.get("phrases", []):
        find = entry.get("find") or ""
        repls = entry.get("replace_with") or []
        if not find or not repls:
            continue
        # Case-insensitive find with case preservation on first letter
        pattern = re.compile(re.escape(find), re.IGNORECASE)

        def _sub(m):
            choice = repls[rng.randrange(len(repls))]
            original = m.group(0)
            if not choice:
                return ""
            if original and original[0].isupper() and choice:
                return choice[0].upper() + choice[1:]
            return choice

        out = pattern.sub(_sub, out)

    # Subtle punctuation de-uniformization
    rules = fp.get("punctuation_rules", {})
    if rules.get("em_dash_strip_uniformity"):
        # If every paragraph contains an em-dash, randomly drop ~30%.
        paragraphs = out.split("\n\n")
        for i, p in enumerate(paragraphs):
            if "—" in p and rng.random() < 0.30:
                paragraphs[i] = p.replace("—", ",", 1)
        out = "\n\n".join(paragraphs)
    chance = float(rules.get("ellipsis_unicode_to_ascii_chance", 0))
    if chance and "…" in out:
        # Randomly turn some Unicode ellipses into ASCII ones
        def _ell(m):
            return "..." if rng.random() < chance else "…"
        out = re.sub(r"…", _ell, out)

    return out


# -----------------------------------------------------------------------------
# LLM passes
# -----------------------------------------------------------------------------

_BURSTINESS_PROMPT = """Rewrite the following text to vary sentence length deliberately.

Rules:
  • Mix very short sentences (3–6 words) with longer multi-clause sentences.
  • Target sentence-length stdev ≥ 8 words.
  • Use occasional fragments. Like this. They feel human.
  • Do NOT change meaning. Do NOT add or remove facts. Do NOT change names, numbers, or quotes.
  • Keep the same overall structure (paragraphs, bullets if present).
  • Return ONLY the rewritten text. No preamble, no notes, no quotes.

TEXT:
{TEXT}
"""


def burstiness_pass(text: str, ctx: Dict[str, Any]) -> str:
    api_key = ctx.get("api_key") or ""
    if not api_key:
        return text
    out = claude_rewrite(
        api_key=api_key,
        user_prompt=_BURSTINESS_PROMPT.replace("{TEXT}", text),
        temperature=0.85,
        max_tokens=min(4000, max(800, int(len(text) / 2))),
    )
    return out or text


_PERPLEXITY_PROMPT = """Rewrite this text to feel more human and less predictable.

Rules:
  • Replace generic word choices with more specific or unexpected (but still
    correct) alternatives. Example: "important" → "load-bearing" / "the part
    that actually matters" — only when it fits.
  • Use idiomatic phrasing where natural.
  • Allow occasional sentence-initial conjunctions ("And", "But", "So") —
    sparingly.
  • Use contractions where natural ("don't", "we're", "it's").
  • Keep facts, names, numbers, and quotes EXACTLY the same.
  • Do not add filler or padding. Tighten where possible.
  • Return ONLY the rewritten text.

TEXT:
{TEXT}
"""


def perplexity_injection(text: str, ctx: Dict[str, Any]) -> str:
    api_key = ctx.get("api_key") or ""
    if not api_key:
        return text
    out = claude_rewrite(
        api_key=api_key,
        user_prompt=_PERPLEXITY_PROMPT.replace("{TEXT}", text),
        temperature=0.95,
        max_tokens=min(4000, max(800, int(len(text) / 2))),
    )
    return out or text


def style_transfer(text: str, ctx: Dict[str, Any]) -> str:
    """If a voice-clone system_prompt is provided, rewrite in that voice."""
    api_key = ctx.get("api_key") or ""
    voice_prompt = ctx.get("voice_system_prompt") or ""
    if not api_key or not voice_prompt:
        return text

    user = (
        "Rewrite the following text in the voice described in the system message.\n"
        "Do NOT change facts, names, numbers, or quotes. Do NOT add new claims.\n"
        "Keep length within ±20% of the original. Return ONLY the rewritten text.\n\n"
        f"TEXT:\n{text}"
    )
    out = claude_rewrite(
        api_key=api_key,
        user_prompt=user,
        system_prompt=voice_prompt,
        temperature=0.8,
        max_tokens=min(4000, max(800, int(len(text) / 2))),
    )
    return out or text


_LINKEDIN_PROMPT = """Reshape this text as a high-performing LinkedIn post.

Rules:
  • The first line must be a hook of ≤ 210 characters that delivers the punchline
    — it MUST land before LinkedIn truncates.
  • Short paragraphs: 1–2 sentences each. White space matters.
  • Use plain language. No buzzwords. No "thrilled to announce".
  • Where it helps comprehension, use a short bulleted list with — or • markers.
  • End with one CTA-style line: a sharp question or a soft ask.
  • Add 3–5 relevant hashtags on a single line at the end. Lowercase or PascalCase.
  • Use AT MOST one emoji, only if it adds meaning. Often zero.
  • Keep all facts/numbers/quotes intact. Do not invent stats.
  • Return ONLY the post text.

TEXT:
{TEXT}
"""


def linkedin_seo(text: str, ctx: Dict[str, Any]) -> str:
    api_key = ctx.get("api_key") or ""
    if not api_key or ctx.get("seo_target") != "linkedin":
        return text
    out = claude_rewrite(
        api_key=api_key,
        user_prompt=_LINKEDIN_PROMPT.replace("{TEXT}", text),
        temperature=0.8,
        max_tokens=min(2000, max(800, int(len(text) / 2))),
    )
    return out or text


# -----------------------------------------------------------------------------
# Fact guard — extract entities & numbers, revert mutations
# -----------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\b\d[\d,\.]*\s?%?\b")
_QUOTE_RE  = re.compile(r"[\"\u201c]([^\"\u201c\u201d\n]{4,200})[\"\u201d]")
_PROPER_RE = re.compile(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,}){0,3})\b")


def _extract_facts(text: str) -> Dict[str, List[str]]:
    return {
        "numbers": list({m.group(0) for m in _NUMBER_RE.finditer(text)}),
        "quotes":  list({m.group(0) for m in _QUOTE_RE.finditer(text)}),
        "names":   list({m.group(0) for m in _PROPER_RE.finditer(text)}),
    }


def fact_guard(text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare facts in current text vs. the original (ctx['original_text']).
    Returns {"text": text, "lost": {"numbers":[...], "quotes":[...], "names":[...]}}
    The pipeline can decide to retry / annotate based on what was lost.
    """
    original = ctx.get("original_text") or ""
    if not original:
        return {"text": text, "lost": {"numbers": [], "quotes": [], "names": []}}
    orig = _extract_facts(original)
    cur  = _extract_facts(text)
    lost = {
        "numbers": [n for n in orig["numbers"] if n not in cur["numbers"]],
        "quotes":  [q for q in orig["quotes"]  if q not in cur["quotes"]],
        "names":   [n for n in orig["names"]   if n not in cur["names"]],
    }
    # Cheap restore: append a [Note: <original fact>] for any lost numbers/quotes
    # only if the model fully dropped them. This is a safety net, not a rewrite.
    appendix: List[str] = []
    if lost["numbers"]:
        appendix.append("Numbers preserved: " + ", ".join(lost["numbers"][:10]))
    if lost["quotes"]:
        appendix.append("Quotes preserved: " + " ".join(lost["quotes"][:5]))
    if lost["names"]:
        appendix.append("Names preserved: " + ", ".join(lost["names"][:10]))

    if appendix and ctx.get("preserve_facts", True):
        # Don't mangle the output text by default; the pipeline annotates
        # the audit log instead. We only append when the user explicitly
        # asks for visible fact-preservation.
        if ctx.get("annotate_lost_facts"):
            text = text.rstrip() + "\n\n" + "\n".join(appendix)

    return {"text": text, "lost": lost}
