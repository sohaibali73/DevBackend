"""
Pure-Python stylometric statistics for voice-cloning + humanizer scoring.

No external NLP deps — uses regex tokenization. All functions are O(n) and
safe to call thousands of times.
"""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from typing import Any, Dict, List, Tuple

# -----------------------------------------------------------------------------
# Tokenization
# -----------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'\(])")
_WORD_RE        = re.compile(r"\b[\w']+\b", re.UNICODE)


def split_sentences(text: str) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = _SENTENCE_SPLIT.split(text)
    return [s.strip() for s in parts if s.strip()]


def tokenize_words(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


# -----------------------------------------------------------------------------
# Per-text stats
# -----------------------------------------------------------------------------

# Common AI "tells" — overused phrases & constructions
_AI_FINGERPRINT_PHRASES = [
    "delve into", "in conclusion", "it's important to note", "it is important to note",
    "tapestry of", "navigate the", "navigating the", "leverage", "leveraging",
    "in today's", "in the realm of", "ever-evolving", "fast-paced",
    "robust", "seamless", "seamlessly", "synergy", "synergies",
    "harness", "harnessing", "embark on", "embark upon",
    "at the end of the day", "moving forward", "going forward",
    "comprehensive", "overall", "furthermore", "moreover", "additionally",
    "however, it is", "it should be noted",
    "a testament to", "a stark reminder",
    "this article", "in this article",
    "let's dive in", "let's explore", "let us explore",
    "unleash", "unlock the power",
    "cutting-edge", "state-of-the-art", "groundbreaking",
    "in summary", "to summarize",
    "plays a crucial role", "plays a vital role",
    "by leveraging", "by harnessing",
]


def stats(text: str) -> Dict[str, Any]:
    """
    Compute a compact stylometric profile for `text`.
    Used both during voice-cloning ingest and in the humanizer scoring loop.
    """
    sentences = split_sentences(text)
    words = tokenize_words(text)

    if not sentences or not words:
        return {
            "char_count":         len(text or ""),
            "word_count":         len(words),
            "sentence_count":     len(sentences),
            "sentence_len_avg":   0.0,
            "sentence_len_stdev": 0.0,
            "burstiness":         0.0,
            "ttr":                0.0,
            "hapax_ratio":        0.0,
            "avg_word_len":       0.0,
            "punctuation":        {},
            "ai_fingerprints":    {},
            "function_word_ratio": 0.0,
            "contractions_per_100w": 0.0,
            "exclamations":         0,
            "questions":            0,
            "starts_with_conjunction_pct": 0.0,
            "flesch_reading_ease": 0.0,
        }

    sent_lens = [len(tokenize_words(s)) for s in sentences]
    sent_avg = statistics.fmean(sent_lens)
    sent_std = statistics.pstdev(sent_lens) if len(sent_lens) > 1 else 0.0

    word_counter = Counter(words)
    unique = len(word_counter)
    hapax = sum(1 for c in word_counter.values() if c == 1)

    avg_wl = statistics.fmean(len(w) for w in words)

    # Punctuation
    punct = {
        "comma":      text.count(","),
        "semicolon":  text.count(";"),
        "colon":      text.count(":"),
        "em_dash":    text.count("—") + text.count("--"),
        "ellipsis":   text.count("…") + text.count("..."),
        "exclam":     text.count("!"),
        "question":   text.count("?"),
        "open_paren": text.count("("),
    }

    # AI fingerprint phrase counts
    low = text.lower()
    fingerprints = {p: low.count(p) for p in _AI_FINGERPRINT_PHRASES if p in low}

    # Function word ratio (rough proxy)
    function_words = {
        "the","of","and","to","a","in","that","is","it","for","on","with","as","be",
        "by","this","an","at","but","from","or","not","are","was","were","which","you",
        "your","i","we","they","he","she","his","her","its","their","our",
    }
    fw = sum(1 for w in words if w in function_words)
    fw_ratio = fw / max(1, len(words))

    # Contractions per 100 words
    contractions = sum(1 for w in words if "'" in w)
    contractions_100 = contractions / max(1, len(words)) * 100.0

    # Sentence-initial conjunctions
    conj = {"and","but","so","or","yet","because","however","still","also","then"}
    starters = [s.split(maxsplit=1)[0].lower() for s in sentences if s]
    sw_pct = sum(1 for s in starters if s in conj) / max(1, len(starters)) * 100.0

    # Flesch reading ease
    syllables = sum(_estimate_syllables(w) for w in words)
    fre = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syllables / max(1, len(words)))

    return {
        "char_count":         len(text or ""),
        "word_count":         len(words),
        "sentence_count":     len(sentences),
        "sentence_len_avg":   round(sent_avg, 2),
        "sentence_len_stdev": round(sent_std, 2),
        "burstiness":         round(sent_std / sent_avg, 3) if sent_avg else 0.0,
        "ttr":                round(unique / len(words), 3),
        "hapax_ratio":        round(hapax / len(words), 3),
        "avg_word_len":       round(avg_wl, 2),
        "punctuation":        punct,
        "ai_fingerprints":    fingerprints,
        "function_word_ratio": round(fw_ratio, 3),
        "contractions_per_100w": round(contractions_100, 2),
        "exclamations":       punct["exclam"],
        "questions":          punct["question"],
        "starts_with_conjunction_pct": round(sw_pct, 2),
        "flesch_reading_ease": round(fre, 2),
    }


def _estimate_syllables(word: str) -> int:
    """Crude syllable estimator — vowel groups."""
    word = word.lower()
    if not word:
        return 0
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


# -----------------------------------------------------------------------------
# Aggregate over many samples
# -----------------------------------------------------------------------------

def aggregate(stats_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not stats_list:
        return {}

    def avg(key: str) -> float:
        vals = [s.get(key, 0) or 0 for s in stats_list]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    # Aggregate punctuation density per 1000 chars
    total_chars = max(1, sum(s.get("char_count", 0) for s in stats_list))
    punct_keys = ["comma","semicolon","colon","em_dash","ellipsis","exclam","question","open_paren"]
    punct_density = {
        k: round(sum(s.get("punctuation",{}).get(k,0) for s in stats_list) / total_chars * 1000.0, 3)
        for k in punct_keys
    }

    # AI fingerprint occurrences
    fp = Counter()
    for s in stats_list:
        for k, v in (s.get("ai_fingerprints") or {}).items():
            fp[k] += v

    return {
        "samples":            len(stats_list),
        "sentence_len_avg":   avg("sentence_len_avg"),
        "sentence_len_stdev": avg("sentence_len_stdev"),
        "burstiness":         avg("burstiness"),
        "ttr":                avg("ttr"),
        "hapax_ratio":        avg("hapax_ratio"),
        "avg_word_len":       avg("avg_word_len"),
        "function_word_ratio": avg("function_word_ratio"),
        "contractions_per_100w": avg("contractions_per_100w"),
        "starts_with_conjunction_pct": avg("starts_with_conjunction_pct"),
        "flesch_reading_ease": avg("flesch_reading_ease"),
        "punctuation_per_1000c": punct_density,
        "ai_fingerprint_total": dict(fp.most_common(20)),
    }


# -----------------------------------------------------------------------------
# AI detection score (lightweight, fast — runs without ML models)
# -----------------------------------------------------------------------------

def ai_detection_score(text: str) -> Dict[str, Any]:
    """
    Lightweight 0..1 AI-likelihood score using statistical proxies for
    burstiness, perplexity surrogate, and AI-fingerprint phrase density.

    1.0 = very AI-like, 0.0 = very human-like.

    This is the *fast* baseline always available. The heavy ensemble
    (Binoculars + GLTR + Roberta) lives in core.humanize.detectors.
    """
    s = stats(text)
    # Burstiness: humans average ~0.5–0.9; LLMs often ~0.2–0.4
    burstiness = s.get("burstiness", 0.0) or 0.0
    burst_score = max(0.0, min(1.0, (0.55 - burstiness) / 0.45))  # higher → AI

    # AI-fingerprint phrase density
    fp_total = sum((s.get("ai_fingerprints") or {}).values())
    words = max(1, s.get("word_count", 1))
    fp_density = fp_total / words * 1000.0
    fp_score = max(0.0, min(1.0, fp_density / 6.0))  # 6+ per 1k words → 1.0

    # Sentence length variance — too uniform = AI
    stdev = s.get("sentence_len_stdev", 0.0) or 0.0
    var_score = max(0.0, min(1.0, (8.0 - stdev) / 8.0))

    # Function-word ratio is bizarrely uniform in AI text
    fwr = s.get("function_word_ratio", 0.0) or 0.0
    fwr_score = max(0.0, min(1.0, abs(fwr - 0.42) > 0.06 and 0.0 or (0.06 - abs(fwr - 0.42)) / 0.06))

    # Contractions: AI tends to under-use them
    contr = s.get("contractions_per_100w", 0.0) or 0.0
    contr_score = max(0.0, min(1.0, (1.5 - contr) / 1.5))

    score = (
        0.30 * burst_score
        + 0.25 * fp_score
        + 0.20 * var_score
        + 0.10 * fwr_score
        + 0.15 * contr_score
    )

    return {
        "score":      round(score, 3),
        "components": {
            "burstiness":            round(burst_score, 3),
            "fingerprint_density":   round(fp_score, 3),
            "sentence_var":          round(var_score, 3),
            "function_word_ratio":   round(fwr_score, 3),
            "contractions":          round(contr_score, 3),
        },
        "raw_stats":  s,
    }
