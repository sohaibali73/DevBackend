"""
core/yang — YANG Advanced Agentic Features
==========================================
Feature modules:
  settings.py          — per-user config + per-request override merging
  subagents.py         — parallel focused subagent runner
  parallel_tools.py    — parallel tool dispatch with ordering preservation
  plan_guard.py        — strict plan mode tool-list filtering
  auto_compact.py      — background conversation history compression
  focus_chain.py       — rolling task-focus tracker
  checkpoints.py       — conversation rollback points
  completion_verifier.py — double-check completion via secondary LLM pass
  yolo.py              — yolo mode gate (no confirmations, auto-checkpoint)
"""
