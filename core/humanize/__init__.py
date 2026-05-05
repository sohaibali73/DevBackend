"""
Advanced humanizer — turns AI-generated text into human-passing copy
while preserving facts and (optionally) cloning a target writing voice.

Pipeline (see core/humanize/pipeline.py):
    1. Stylometric analyzer
    2. AI-fingerprint scrubber (rule-based, deterministic)
    3. Burstiness pass (LLM)
    4. Perplexity injection (LLM)
    5. Style transfer (LLM, optional voice clone)
    6. LinkedIn SEO pass (optional)
    7. Detector self-check loop (Binoculars + GLTR + optional Roberta)
    8. Fact-preservation guard
    9. Style fidelity score (cosine vs. style centroid)

Public surface:
    run(text, ...)   →  {output, scores, passes_summary, ...}
    score(text)      →  {ai_detection, perplexity, ...}
"""
