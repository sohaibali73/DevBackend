# AFL Skill Architecture Map
> Current state — all file locations and how they connect.

---

## HIGH-LEVEL FLOW

```
Frontend Request
      │
      ├─── POST /afl/generate          → api/routes/afl.py
      ├─── POST /chat                  → api/routes/chat.py
      └─── POST /skills/{slug}/execute → api/routes/skills_execute.py
                                              │
                                              ▼
                                    core/claude_engine.py
                                    (ClaudeAFLEngine)
                                              │
                                    core/prompts/__init__.py
                                              │
                                    core/prompts/base.py
                                    (get_base_prompt / get_chat_prompt)
                                              │
                                    core/afl_validator.py
                                    (post-generation validation)
                                              │
                                         Supabase DB
```

---

## 1. API ENTRY POINTS

### Direct AFL Generation
```
api/routes/afl.py
├── POST /afl/generate            ← Main strategy generation (streaming + non-streaming)
├── POST /afl/generate/workflow   ← Conversation-based generation with mandatory questions
├── POST /afl/optimize            ← Optimize existing AFL code
├── POST /afl/debug               ← Debug and fix AFL errors
├── POST /afl/explain             ← Explain AFL code in plain English
├── POST /afl/validate            ← Syntax validation (no API key needed)
├── POST /afl/format              ← Pretty-print / format AFL code
├── POST /afl/upload              ← Upload files for generation context
├── GET  /afl/history             ← User's generation history
├── POST /afl/history             ← Save a history entry
├── DELETE /afl/history/{id}      ← Delete history entry
├── GET  /afl/codes               ← List saved strategies
├── GET  /afl/codes/{id}          ← Get a specific strategy
├── DELETE /afl/codes/{id}        ← Delete a strategy
├── POST /afl/feedback            ← Thumbs up/down on a generation
├── GET  /afl/generations/{id}    ← Alias: fetch from afl_history OR afl_codes
├── DELETE /afl/generations/{id}  ← Alias: delete from afl_history OR afl_codes
├── GET/POST/PUT/DELETE /afl/presets ← Backtest settings presets
```

### Chat (uses AFL engine internally)
```
api/routes/chat.py
└── POST /chat  ← General chat, routes to ClaudeAFLEngine
                   Imports: get_base_prompt, get_chat_prompt from core.prompts
                   Still has _AFL_RULES block + invoke_skill/amibroker references
                   ⚠️  Contains stale invoke_skill references for "amibroker-afl-developer"
```

### Skill Execution (legacy Claude beta path)
```
api/routes/skills_execute.py
└── POST /skills/{slug}/execute
        │
        ├── calls: core/skill_gateway.py (SkillGateway)
        └── calls: core/skills/loader.py (get_skill, list_skills)
```

---

## 2. GENERATION ENGINE

```
core/claude_engine.py
├── class ClaudeAFLEngine          ← Main engine class
├── class StrategyType             ← STANDALONE | COMPOSITE
├── class BacktestSettings         ← Equity, position size, commission, delays
│     └── .to_afl()               ← Generates AFL SetOption/SetTradeDelays block
├── class ClaudeModel              ← Available Claude models
│
├── .generate_afl()               ← Core generation (streaming + non-streaming)
├── .optimize_code()              ← Optimization via Claude
├── .debug_code()                 ← Debugging via Claude
├── .explain_code()               ← Explanation via Claude
├── .validate_code()              ← Local syntax validation (no API call)
│
├── PROMPT IMPORT (with fallback chain):
│     1. tries: from core.prompts.afl import ...   ← ⚠️  FILE DOES NOT EXIST
│     2. tries: from routes.afl import ...         ← ⚠️  WRONG PATH
│     3. tries: from afl import ...               ← ⚠️  WRONG PATH
│     4. fallback: inline minimal prompts          ← what actually runs
│     ✅ REAL SOURCE: core/prompts/base.py         ← but reached via __init__.py
│        (imported by chat.py and afl.py routes, NOT by claude_engine.py directly)
│
└── AFL_VALIDATOR_AVAILABLE check:
      └── from core.afl_validator import AFLValidator, validate_afl_code, fix_afl_code
```

---

## 3. PROMPTS

```
core/prompts/
├── __init__.py              ← Re-exports everything; defines get_generate_prompt(),
│                               get_clarification_prompt(), get_afl_base_prompt(), etc.
│                               Imports from base.py and condensed_prompts.py
│
├── base.py                  ← ★ PRIMARY SOURCE ★
│   ├── FUNCTION_REFERENCE   ← AFL function signature rules (RSI(14) not RSI(Close,14))
│   ├── RESERVED_KEYWORDS    ← Variable naming rules
│   ├── PARAM_OPTIMIZE_PATTERN ← Param/Optimize template
│   ├── TIMEFRAME_RULES      ← TimeFrameExpand() rules
│   ├── get_base_prompt()    ← Full AFL developer system prompt
│   └── get_chat_prompt()    ← Chat/agent mode prompt (file routing, trading advice,
│                               GenUI card rules, artifact guidelines)
│
├── condensed_prompts.py     ← Token-efficient versions
│   ├── get_condensed_clarification_prompt()
│   ├── get_condensed_reverse_engineer_prompt()
│   ├── get_condensed_afl_generation_prompt()
│   ├── get_condensed_research_synthesis_prompt()
│   └── get_condensed_schematic_generation_prompt()
│
└── afl.py                   ← ⚠️  DOES NOT EXIST (claude_engine.py tries to import from here)
```

**Who imports what:**

| File | Imports from base.py |
|---|---|
| `core/prompts/__init__.py` | `get_base_prompt`, `get_chat_prompt`, `FUNCTION_REFERENCE`, `RESERVED_KEYWORDS` |
| `api/routes/chat.py` | `get_base_prompt`, `get_chat_prompt` (via `core.prompts`) |
| `api/routes/backtest.py` | `get_backtest_analysis_prompt` (via `core.prompts.__init__`) |
| `core/claude_engine.py` | ❌ Tries `core.prompts.afl` — fails silently, uses inline fallback |

---

## 4. AFL VALIDATOR

```
core/afl_validator.py
├── class AFLValidator             ← Comprehensive syntax + semantic checker
│     ├── validate()              ← Returns ValidationResult
│     ├── _check_function_signatures()
│     ├── _check_reserved_words()
│     ├── _check_colors()
│     └── _check_timeframe_rules()
│
├── validate_afl_code(code)        ← Convenience function → dict
├── validate_afl_file(filepath)    ← File-based convenience function
│
├── Covers: Errors 1–54, 90–94, 701–706, Warnings 501–503
└── Used by: core/claude_engine.py (post-generation validation)
```

---

## 5. SKILL SYSTEMS (Two parallel systems exist)

### System A — Old Claude Beta Skills (api/routes/skills.py)
> Uses Anthropic's Claude beta headers. Still registered but may not be active.

```
api/routes/skills.py
├── SKILLS_BETAS = ["code-execution-2025-08-25", "skills-2025-10-02"]
├── class SkillCategory (AFL, DOCUMENT, PRESENTATION, etc.)
├── class SkillDefinition (skill_id, name, slug, system_prompt, ...)
│
└── Registered AFL Skill:
    ├── skill_id: "skill_01GG6E88EuXr9H9tqLp51sH5"
    ├── name: "AmiBroker AFL Developer"
    ├── slug: "amibroker-afl-developer"
    ├── category: SkillCategory.AFL
    └── system_prompt: inline AFL rules (FUNCTION SIGNATURES, COLORS, etc.)

api/routes/skills_execute.py
└── POST /skills/{slug}/execute
      └── core/skill_gateway.py (SkillGateway)
```

### System B — Server-Side Skills V2 (core/skills_v2/)
> Model-agnostic. Runs as sub-agent conversation with same provider.

```
core/skills_v2/
├── base.py           ← SkillDefinition dataclass (slug, system_prompt, tools, timeout)
├── registry.py       ← SkillRegistry (register, get, list_enabled, get_tool_definitions)
├── executor.py       ← SkillExecutor (runs multi-turn tool loop as sub-agent)
└── builtins/
    ├── afl_developer.py    ← AFL_DEVELOPER_SKILL definition
    │    slug: "amibroker-afl-developer"
    │    max_tokens: 81920, timeout: 1200
    │    required_tools: ["execute_code"]
    ├── docx_generator.py
    ├── pptx_generator.py
    └── quant_analyst.py
```

### System C — Legacy File-Based Skills (core/skills/)
> Loaded from skill.json + prompt.md pairs. Older architecture.

```
core/skills/
├── loader.py                        ← get_skill(), list_skills()
├── executor.py                      ← SkillExecutor (uses BaseLLMProvider + SandboxManager)
├── router.py                        ← Skill routing logic
├── __init__.py
│
└── afl-developer/
    ├── skill.json                   ← slug: "afl-developer"
    │                                   aliases: ["amibroker-afl-developer", "afl", ...]
    │                                   max_tokens: 163840, timeout: 18000
    │                                   tools: ["execute_python"]
    └── prompt.md                    ← Skill-specific system prompt
```

---

## 6. DATABASE TABLES

```
Supabase
├── afl_codes              ← Saved generated strategies (user_id, code, description, strategy_type)
├── afl_history            ← Generation history (user_id, strategy_description, generated_code)
├── afl_uploaded_files     ← Uploaded context files (user_id, filename, content)
├── afl_settings_presets   ← Saved backtest presets (initial_equity, commission, etc.)
└── afl_feedback           ← Thumbs up/down on generations (generation_id, rating)
```

---

## 7. SUPPORTING FILES

```
core/afl_validator.py      ← Post-generation syntax validation
core/AFLCHECKER.PY         ← (separate standalone AFL checker script)
core/context_manager.py    ← build_optimized_context() — attaches KB + training context
                              only for AFL tasks: ["generate", "debug", "optimize", "afl", ...]
core/document_classifier.py ← Detects .afl files / AFL content for KB categorisation
core/document_parser.py     ← Parses .afl files as plain text
api/routes/reverse_engineer.py ← Reverse engineer chart → AFL code skeleton
api/routes/backtest.py      ← Backtest analysis (imports get_backtest_analysis_prompt)
api/routes/train.py         ← Feedback loop for improving generations
```

---

## 8. KNOWN ISSUES / STALE REFERENCES

| Issue | Location | Detail |
|---|---|---|
| `core.prompts.afl` doesn't exist | `core/claude_engine.py` line ~15 | Engine silently falls back to inline minimal prompts — NOT using the full base.py prompts |
| `invoke_skill` references in _AFL_RULES | `api/routes/chat.py` | Still mentions `amibroker-afl-developer` as an invoke_skill target |
| Two SkillDefinition classes | `api/routes/skills.py` + `core/skills_v2/base.py` | Same name, different schemas — potential confusion |
| `afl-developer` vs `amibroker-afl-developer` slug | `core/skills/afl-developer/skill.json` | Primary slug is `afl-developer`, aliases include `amibroker-afl-developer` |
| `core/prompts/afl.py` missing | Referenced by `claude_engine.py` | Creating this file and re-exporting from `base.py` would fix the fallback chain |
