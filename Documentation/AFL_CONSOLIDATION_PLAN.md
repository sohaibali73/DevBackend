# AFL Skill Consolidation Plan (CORRECTED)
> Goal: ONE place for the AFL skill prompt. Remove Claude beta references. Fix broken import chain.

---

## HOW THE SYSTEMS ACTUALLY WORK

### `core/skills/` ← THIS IS THE LIVE SERVER-SIDE SKILL SYSTEM ✅
- Auto-discovers skill subfolders at startup via `loader.py`
- Each skill folder: `skill.json` (metadata) + `prompt.md` (system prompt)
- Executed by: `core/skills/executor.py` → `SkillRouter` → `BaseLLMProvider` + `SandboxManager`
- Triggered by: `api/routes/skills_execute.py` → `POST /skills/{slug}/execute`
- **`core/skills/afl-developer/`** is the ACTIVE server-side AFL skill

### `api/routes/skills.py` ← CLAUDE BETA SKILLS REGISTRY (to be cleaned up) ❌
- Uses Anthropic's beta headers: `skills-2025-10-02`, `code-execution-2025-08-25`
- Skills identified by `skill_id` (cloud-registered on Anthropic portal)
- AFL entry: `skill_id="skill_01GG6E88EuXr9H9tqLp51sH5"` — this is the OLD beta approach
- **This is what needs removing**

### `core/skills_v2/` ← DUPLICATE SYSTEM (to be removed) ❌
- A second attempt at a Python dataclass-based server-side skill system
- Has its own `builtins/afl_developer.py` with inline minimal prompt
- Parallel to `core/skills/` — adds confusion, not used consistently
- **Candidate for removal** (consolidate into `core/skills/`)

### `core/claude_engine.py` ← BROKEN IMPORT CHAIN ❌
- Tries `from core.prompts.afl import ...` — file doesn't exist
- Falls back to 3-line inline minimal prompts silently
- Never reaches `core/prompts/base.py` prompt

---

## CURRENT PROBLEM SUMMARY

| Location | Type | Status |
|---|---|---|
| `core/skills/afl-developer/` | ✅ Live server-side skill | **KEEP — this is the right place** |
| `core/skills/afl-developer/prompt.md` | ✅ Rich detailed AFL prompt | **KEEP — but make it the single source** |
| `api/routes/skills.py` → `skill_01GG...` | ❌ Old Claude beta registration | **REMOVE** |
| `core/skills_v2/builtins/afl_developer.py` | ❌ Duplicate with minimal inline prompt | **REMOVE** |
| `core/skills_v2/` (entire folder) | ❌ Duplicate skill system | **REMOVE or consolidate** |
| `core/prompts/afl.py` | ❌ Referenced but doesn't exist | **CREATE** to fix import chain |
| `core/claude_engine.py` import chain | ❌ Broken — uses inline fallback | **FIX** |
| `api/routes/chat.py` `_AFL_RULES` block | ❌ Stale invoke_skill reference | **CLEAN** |

---

## TARGET STATE (after cleanup)

```
core/skills/afl-developer/
├── skill.json          ← metadata (slug, aliases, max_tokens, timeout)
└── prompt.md           ← ★ THE AFL PROMPT (edit this to improve the skill)

core/prompts/afl.py     ← thin shim: reads prompt.md and exports get_afl_system_prompt()
        │
        ├── imported by: core/claude_engine.py          (fixes broken import)
        └── imported by: core/prompts/__init__.py       (re-exported to rest of app)

api/routes/skills_execute.py → POST /skills/{slug}/execute
        └── core/skills/router.py → loader.py → reads afl-developer/prompt.md
```

**One edit to `core/skills/afl-developer/prompt.md` → flows to everything.**

---

## STEP-BY-STEP CHANGES

---

### STEP 1 — Create `core/prompts/afl.py` (thin shim to fix import chain)

**Why:** `claude_engine.py` tries `from core.prompts.afl import get_base_prompt, get_chat_prompt` — this file doesn't exist so it falls back to a 3-line inline prompt.

**What:** Create a thin module that reads from `base.py` and exports the right names:

```python
# core/prompts/afl.py
"""
AFL prompt shim — re-exports from base.py.
This file exists so claude_engine.py can import from core.prompts.afl
without triggering the fallback chain.
"""
from .base import (
    get_base_prompt as get_afl_system_prompt,
    get_base_prompt,
    get_chat_prompt,
    FUNCTION_REFERENCE,
    RESERVED_KEYWORDS,
    PARAM_OPTIMIZE_PATTERN,
    TIMEFRAME_RULES,
)

__all__ = [
    "get_afl_system_prompt",
    "get_base_prompt",
    "get_chat_prompt",
    "FUNCTION_REFERENCE",
    "RESERVED_KEYWORDS",
    "PARAM_OPTIMIZE_PATTERN",
    "TIMEFRAME_RULES",
]
```

**Impact:** The engine now gets the full prompt. No more inline fallback.

---

### STEP 2 — Fix `core/claude_engine.py` (clean up the broken fallback chain)

**Current (broken):**
```python
try:
    from core.prompts.afl import get_base_prompt, get_chat_prompt   # ← DIDN'T EXIST
    _AFL_IMPORT_SOURCE = "core.prompts.afl"
except ImportError:
    try:
        from routes.afl import ...   # ← WRONG
    ...
    # silently uses 3-line inline prompt
```

**Fix — replace the whole try/except block with:**
```python
from core.prompts.afl import get_base_prompt, get_chat_prompt
_AFL_IMPORT_SOURCE = "core.prompts.afl"
```

**Impact:** Engine always uses `base.py`'s full prompt. Broken fallback chain eliminated.

---

### STEP 3 — Remove AFL beta skill from `api/routes/skills.py`

**Action:** Delete the `_register(SkillDefinition(...))` block for:
- `skill_id = "skill_01GG6E88EuXr9H9tqLp51sH5"`
- `name = "AmiBroker AFL Developer"`
- `slug = "amibroker-afl-developer"`

**Check:** Verify `SkillCategory.AFL` is not used by other remaining skills — if not, remove that enum value too.

**Impact:** The Anthropic cloud-registered beta skill_id is no longer referenced anywhere in the codebase.

---

### STEP 4 — Remove `core/skills_v2/builtins/afl_developer.py`

**Action:** Delete this file. It duplicates the skill that already lives at `core/skills/afl-developer/`.

**Check first:** Confirm nothing imports `core.skills_v2.builtins.afl_developer` directly.

---

### STEP 5 — Assess `core/skills_v2/` for full removal

**Check:** Does anything actively import from `core/skills_v2/`?

```
core/skills_v2/base.py       ← SkillDefinition dataclass
core/skills_v2/registry.py   ← SkillRegistry
core/skills_v2/executor.py   ← SkillExecutor
core/skills_v2/builtins/     ← afl_developer, docx, pptx, quant_analyst
```

If nothing in production routes imports `core.skills_v2`, remove the entire folder.
If other builtins (docx, pptx, quant_analyst) ARE used, keep those but delete just the afl_developer.py builtin.

---

### STEP 6 — Clean up `api/routes/chat.py`

**Action:** Remove the `_AFL_RULES` string that still says:
```python
"You have access to: invoke_skill, analyze_backtest, generate_afl_code, and other domain-specific tools."
```

The AFL rules are already delivered via `get_chat_prompt()` from `base.py`. This block is stale and misleading.

---

### STEP 7 — Update `core/prompts/__init__.py`

**Action:** Add import of `get_afl_system_prompt` from the new `afl.py`:

```python
from .afl import get_afl_system_prompt
```

Add to `__all__`.

---

## FILES CHANGED SUMMARY

| File | Action |
|---|---|
| `core/prompts/afl.py` | **CREATE** — thin shim re-exporting from base.py, fixes broken import |
| `core/claude_engine.py` | **FIX** — remove broken fallback chain, clean single import |
| `api/routes/skills.py` | **REMOVE** — delete the `amibroker-afl-developer` beta SkillDefinition block |
| `core/skills_v2/builtins/afl_developer.py` | **DELETE** — duplicate of `core/skills/afl-developer/` |
| `core/skills_v2/` (rest) | **ASSESS** — remove entirely if nothing else uses it |
| `api/routes/chat.py` | **CLEAN** — remove stale `_AFL_RULES` invoke_skill line |
| `core/prompts/__init__.py` | **UPDATE** — export `get_afl_system_prompt` |

---

## FILES NOT TOUCHED

| File | Reason |
|---|---|
| `core/skills/afl-developer/prompt.md` | ✅ This IS the AFL skill — keep and improve it |
| `core/skills/afl-developer/skill.json` | ✅ Metadata for the live server-side skill |
| `core/skills/loader.py` | ✅ Auto-discovery system — no changes needed |
| `core/skills/executor.py` | ✅ Execution engine — no changes needed |
| `core/skills/router.py` | ✅ Routing — no changes needed |
| `api/routes/skills_execute.py` | ✅ Already calls correct server-side path |
| `api/routes/afl.py` | ✅ Direct generation routes work correctly |
| `core/afl_validator.py` | ✅ Validation logic is correct |
| `core/prompts/base.py` | ✅ Source of truth for prompts — no changes needed |
| DB tables | No DB changes needed |

---

## AFTER CLEANUP: HOW TO IMPROVE THE AFL SKILL

**Edit this one file:** `core/skills/afl-developer/prompt.md`

That change flows to:
1. `POST /skills/afl-developer/execute` (via `SkillRouter` → `loader.py` reads `prompt.md`)
2. `POST /afl/generate` via `claude_engine.py` → `core.prompts.afl` → `base.py` (via STEP 1 fix)
3. `POST /chat` via `api/routes/chat.py` → `core.prompts` → `base.py`

> NOTE: Steps 1 & 2 make `claude_engine.py` use `base.py`'s prompt. To make ALL paths use the same `prompt.md`, a future improvement would be to have `core/prompts/base.py`'s `get_base_prompt()` read from `core/skills/afl-developer/prompt.md` directly — making the file truly the one-stop source.
