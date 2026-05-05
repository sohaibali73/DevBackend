"""
Build a system-prompt that injects a cloned voice into any LLM call.

The prompt has three parts:
    1. Persona declaration ("You are writing as <Name>.")
    2. Hard quantitative targets (sentence-len avg/σ, fingerprint avoidance, etc.)
    3. Few-shot exemplars (the most-characteristic passages)
    4. Explicit DO / DON'T rules from qualitative voice_card

This module is purely string-building — no I/O.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _fmt_quantitative(quant: Dict[str, Any]) -> str:
    if not quant:
        return ""
    lines = [
        "Quantitative voice fingerprint (match these targets within ±15%):",
        f"  - sentence_len_avg:        {quant.get('sentence_len_avg', 'n/a')} words",
        f"  - sentence_len_stdev:      {quant.get('sentence_len_stdev', 'n/a')} (mix short + long sentences)",
        f"  - burstiness:              {quant.get('burstiness', 'n/a')}",
        f"  - type_token_ratio:        {quant.get('ttr', 'n/a')}",
        f"  - hapax_ratio:             {quant.get('hapax_ratio', 'n/a')}",
        f"  - avg_word_len:            {quant.get('avg_word_len', 'n/a')}",
        f"  - function_word_ratio:     {quant.get('function_word_ratio', 'n/a')}",
        f"  - contractions_per_100w:   {quant.get('contractions_per_100w', 'n/a')}",
        f"  - sentence_initial_conjunctions_pct: {quant.get('starts_with_conjunction_pct', 'n/a')}",
        f"  - flesch_reading_ease:     {quant.get('flesch_reading_ease', 'n/a')}",
    ]
    pd = quant.get("punctuation_per_1000c") or {}
    if pd:
        lines.append(
            "  - punctuation_per_1000_chars: "
            + ", ".join(f"{k}={v}" for k, v in pd.items())
        )
    fp = quant.get("ai_fingerprint_total") or {}
    if fp:
        lines.append(
            "  - AI-tell phrases observed in this author: " + ", ".join(list(fp.keys())[:8])
        )
    return "\n".join(lines)


def _fmt_qualitative(qual: Dict[str, Any]) -> str:
    if not qual:
        return ""
    voice = qual.get("voice") or {}
    lex   = qual.get("lexicon") or {}
    stru  = qual.get("structure") or {}
    rhet  = qual.get("rhetoric") or {}
    idio  = qual.get("idiolect") or {}
    out   = []

    if voice:
        out.append(
            f"Voice: register={voice.get('register','?')}, formality={voice.get('formality','?')}/10, "
            f"warmth={voice.get('warmth','?')}/10, authority={voice.get('authority','?')}/10, "
            f"humor={voice.get('humor','?')}/10, certainty={voice.get('certainty','?')}/10, "
            f"perspective={voice.get('perspective','?')}."
        )
    if qual.get("summary"):
        out.append(f"Summary: {qual['summary']}")

    sigs = lex.get("signature_phrases") or []
    if sigs:
        out.append("Signature phrases (use sparingly, never paraphrase): " + ", ".join(f'"{p}"' for p in sigs[:20]))
    avoid = lex.get("avoided_words") or []
    if avoid:
        out.append("Words this author avoids: " + ", ".join(avoid[:30]))
    if lex.get("favored_verbs"):
        out.append("Favored verbs: " + ", ".join(lex["favored_verbs"][:20]))
    if lex.get("jargon_density"):
        out.append(f"Jargon density: {lex['jargon_density']}")

    if stru.get("opening_patterns"):
        out.append("Opening patterns: " + " | ".join(stru["opening_patterns"][:6]))
    if stru.get("closing_patterns"):
        out.append("Closing patterns: " + " | ".join(stru["closing_patterns"][:6]))
    if stru.get("paragraph_shape"):
        out.append(f"Paragraph shape: {stru['paragraph_shape']}")
    if stru.get("transitions"):
        out.append("Transitions: " + " | ".join(stru["transitions"][:6]))

    if rhet.get("devices"):
        out.append("Rhetorical devices: " + ", ".join(rhet["devices"][:10]))
    if rhet.get("argumentation"):
        out.append(f"Argumentation: {rhet['argumentation']}")
    if rhet.get("storytelling"):
        out.append(f"Storytelling: {rhet['storytelling']}")

    if idio.get("discourse_markers"):
        out.append("Discourse markers: " + ", ".join(idio["discourse_markers"][:10]))
    if idio.get("punctuation_quirks"):
        out.append("Punctuation quirks: " + ", ".join(idio["punctuation_quirks"][:10]))
    if idio.get("unusual_constructions"):
        out.append("Unusual constructions: " + ", ".join(idio["unusual_constructions"][:10]))

    return "\n".join(out)


def _fmt_rules(qual: Dict[str, Any]) -> str:
    do_rules = qual.get("do_rules") or []
    dont = qual.get("dont_rules") or []
    parts = []
    if do_rules:
        parts.append("DO:\n" + "\n".join(f"  • {r}" for r in do_rules[:15]))
    if dont:
        parts.append("DON'T:\n" + "\n".join(f"  • {r}" for r in dont[:15]))
    return "\n".join(parts)


def _fmt_exemplars(exemplars: List[Dict[str, Any]]) -> str:
    if not exemplars:
        return ""
    lines = ["Few-shot exemplars (match this rhythm, vocabulary, and shape exactly):"]
    for i, ex in enumerate(exemplars, 1):
        text = (ex.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"\n[Exemplar {i}]\n{text}")
    return "\n".join(lines)


def build_system_prompt(
    *,
    name: str,
    voice_card: Dict[str, Any],
    exemplars: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Build the full system-prompt addition that clones the voice 1:1.
    Designed to be appended to (or composed with) any base system prompt.
    """
    qual = (voice_card or {}).get("qualitative") or {}
    quant = (voice_card or {}).get("quantitative") or {}

    sections: List[str] = []
    sections.append(
        f"WRITING VOICE — You are writing AS {name}. "
        f"Match their voice 1:1. Do not introduce a generic AI voice. "
        f"If the user's request conflicts with this voice, keep the voice."
    )
    qf = _fmt_qualitative(qual)
    if qf:
        sections.append(qf)
    rf = _fmt_rules(qual)
    if rf:
        sections.append(rf)
    qq = _fmt_quantitative(quant)
    if qq:
        sections.append(qq)
    ef = _fmt_exemplars(exemplars or [])
    if ef:
        sections.append(ef)

    sections.append(
        "Hard rules:\n"
        "  • Never use these AI-tell phrases: 'delve into', 'in conclusion', "
        "'it's important to note', 'tapestry', 'navigate the', 'leverage' (as a verb), "
        "'ever-evolving', 'fast-paced', 'robust', 'seamless', 'synergy', 'harness', "
        "'embark on', 'in today's', 'cutting-edge', 'state-of-the-art', 'in summary', "
        "'plays a crucial role'.\n"
        "  • Vary sentence length deliberately. Short. Then a longer sentence that "
        "stretches an idea across multiple clauses without losing the thread. "
        "Then a fragment. Like that.\n"
        "  • Use contractions when the voice supports them. Do not over-formalize.\n"
        "  • Never explain your stylistic choices. Just write."
    )

    return "\n\n".join(sections).strip()


def fetch_style_prompt(style_id: str, user_id: str) -> Optional[str]:
    """
    Convenience: load a style row and return its cached system_prompt.
    Returns None if style not found or not yet ready.
    """
    if not style_id:
        return None
    try:
        from db.supabase_client import get_supabase
        db = get_supabase()
        res = (
            db.table("studio_writing_styles")
            .select("status, system_prompt")
            .eq("id", style_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        if row.get("status") != "ready":
            return None
        return row.get("system_prompt") or None
    except Exception:
        return None
