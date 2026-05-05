"""
Voice cloning ("writing-style training").

Pipeline:
    1. Ingest samples → store on volume + DB
    2. Extract per-sample stats + embedding
    3. Run analyzer LLM → voice_card (deep linguistic profile)
    4. Build cached system_prompt + few-shot exemplars (injector)
    5. Self-test fidelity
"""
