# Skill Porting Guide
## How to Add Skills to the Model-Agnostic Skill System

---

## Overview

Skills are stored in `core/skills/` — each in its own subdirectory. The system auto-discovers them at startup. Skills execute through the `SkillRouter` using **any LLM provider** (Anthropic, OpenAI, OpenRouter, etc.), not just Claude.

---

## Directory Structure

```
core/skills/
├── __init__.py           ← package exports (do not modify)
├── loader.py             ← auto-discovery engine (do not modify)
├── executor.py           ← tool loop engine (do not modify)
├── router.py             ← public API (do not modify)
│
├── backtest-expert/      ← one folder per skill
│   ├── skill.json        ← REQUIRED: metadata
│   └── prompt.md         ← REQUIRED: system prompt
│
├── document-writer/
│   ├── skill.json
│   └── prompt.md
│
└── (15+ more skills...)
```

---

## Required Files Per Skill

### 1. `skill.json` — Metadata

```json
{
  "slug": "backtest-expert",
  "name": "Backtest Expert",
  "description": "One-line description shown in skill listings and tool descriptions. What does this skill do? When should it be invoked?",
  "category": "finance",
  "tools": ["execute_python", "search_knowledge_base"],
  "output_type": "text",
  "max_tokens": 16384,
  "timeout": 120,
  "enabled": true,
  "aliases": ["backtester", "strategy-validator"]
}
```

#### Field Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `slug` | string | ✅ | Unique kebab-case identifier. Must match folder name. |
| `name` | string | ✅ | Human-readable display name |
| `description` | string | ✅ | One paragraph. Describes what the skill does and WHEN to invoke it. |
| `category` | string | ✅ | One of: `finance`, `research`, `document`, `code`, `data`, `design`, `general` |
| `tools` | array | ✅ | Tools this skill needs. See Tool Registry below. |
| `output_type` | string | ✅ | One of: `text`, `file`, `code`, `data`, `image` |
| `max_tokens` | int | ✅ | Max response tokens. Use 8192 for most, 16384 for long docs, 32768 for very complex. |
| `timeout` | int | optional | Seconds before timeout. Default: 120 |
| `enabled` | bool | ✅ | Set to `false` to disable without deleting |
| `aliases` | array | optional | Old slugs that should still route here (backward compat) |

#### Category Values
- `finance` — trading, investing, backtesting, valuation, research
- `research` — web search, data gathering, lead generation, article extraction
- `document` — Word docs, PDFs, reports, memos
- `code` — programming, debugging, code generation
- `data` — data analysis, CSV, spreadsheets, visualization
- `design` — UI/UX, presentations, visual artifacts
- `general` — catch-all for skills that don't fit above

#### Tool Registry (valid values for `tools` array)

```
execute_python          — Python code execution in sandbox
execute_react           — React/JSX component rendering
search_knowledge_base   — Search uploaded user documents
get_stock_data          — Real-time stock prices/history
technical_analysis      — RSI, MACD, Bollinger Bands, etc.
get_stock_chart         — OHLCV candlestick data
web_search              — Live web search (DuckDuckGo/Tavily)
generate_docx           — Create Potomac-branded Word documents
generate_pptx           — Create Potomac-branded PowerPoint
generate_xlsx           — Create Potomac-branded Excel workbooks
edgar_get_financials    — SEC EDGAR financial data
edgar_get_filings       — SEC EDGAR filings
```

Leave `tools` as `[]` if the skill only generates text/analysis without tool use.

---

### 2. `prompt.md` — System Prompt

This is the full system prompt the LLM receives when executing the skill. It should:

1. **State the role** — "You are an expert [X]..."
2. **Define the task** — What the skill does and how
3. **List constraints/rules** — Hard rules the LLM must follow
4. **Provide format guidance** — How to structure the output
5. **NOT reference Anthropic, Claude, or specific LLM providers** — The system is model-agnostic

#### Good prompt.md Template

```markdown
You are a [role description] expert. [One sentence on what you do.]

## When to Use
[Brief description of when this skill applies]

## Core Responsibilities
[Bulleted list of what this skill does]

## Instructions
[Step-by-step process]

## Output Format
[How the response should be structured]

## Constraints
- [Hard rule 1]
- [Hard rule 2]
- [Never do X]
```

#### Things to REMOVE from source prompts when porting:

| Remove | Replace With |
|---|---|
| "Use Claude's code execution" | "Use the execute_python tool" |
| "In this Claude skill container" | (remove entirely) |
| "Using Claude's Files API" | (remove entirely) |
| References to `skill_id`, `container`, beta APIs | (remove entirely) |
| "This skill runs in Anthropic's container" | (remove entirely) |
| References to bash/shell scripts in container | Replace with execute_python |

---

## Category → Tool Mapping Cheatsheet

When porting a skill, use this to decide which tools to include:

| Skill Type | Recommended Tools |
|---|---|
| Financial analysis | `execute_python`, `get_stock_data`, `technical_analysis` |
| Research / web | `web_search`, `search_knowledge_base` |
| Document generation | `generate_docx` or `generate_pptx` or `generate_xlsx` |
| Code generation | `execute_python` |
| Data analysis | `execute_python`, `get_stock_data` |
| Pure text/analysis | `[]` (no tools needed) |
| SEC/regulatory | `edgar_get_financials`, `edgar_get_filings` |

---

## Complete Example: Porting `backtest-expert`

### Source: `Skill Port/backtest-expert/SKILL.md`
```
---
name: backtest-expert
description: Expert guidance for systematic backtesting...
---
# Backtest Expert
[Full prompt content]
```

### Output: `core/skills/backtest-expert/skill.json`
```json
{
  "slug": "backtest-expert",
  "name": "Backtest Expert",
  "description": "Expert guidance for systematic backtesting of trading strategies. Covers 'beating ideas to death' methodology, parameter robustness testing, slippage modeling, bias prevention, and interpreting backtest results. Use when developing, testing, or validating quantitative trading strategies.",
  "category": "finance",
  "tools": ["execute_python", "get_stock_data"],
  "output_type": "text",
  "max_tokens": 16384,
  "timeout": 180,
  "enabled": true,
  "aliases": ["backtester", "strategy-validator", "backtest_expert"]
}
```

### Output: `core/skills/backtest-expert/prompt.md`
```markdown
You are an expert systematic backtesting advisor...
[Full content from SKILL.md body, cleaned of Anthropic references]
```

---

## Auto-Discovery

The loader auto-detects skills at startup. No registration needed. Just create the folder with the two files and the skill is available immediately after server restart.

```python
# Verify your skill loaded correctly
from core.skills import get_skill, list_skills

skill = get_skill("backtest-expert")
print(skill.name)  # "Backtest Expert"

all_skills = list_skills()
print(len(all_skills))  # Should increase by 1
```

---

## Invoking Skills

Skills are invoked through the `invoke_skill` tool or directly via `SkillRouter`:

```python
# Via SkillRouter (server-side)
from core.skills import SkillRouter
from core.llm.anthropic_provider import AnthropicProvider
from core.sandbox.manager import SandboxManager

router = SkillRouter(
    provider=AnthropicProvider(api_key="sk-ant-..."),
    sandbox_manager=SandboxManager()
)
result = await router.execute("backtest-expert", "Analyze this equity curve...")

# Via invoke_skill tool (Claude will call this automatically)
# Just mention the skill slug and Claude routes to it
```

---

## Skill Folder Naming Convention

- Use **kebab-case** only: `backtest-expert`, `lead-research-assistant`
- Folder name **must match** the `slug` field in `skill.json`
- No spaces, underscores, or uppercase letters in folder name

---

## Checklist Before Committing a New Skill

- [ ] Folder name matches `slug` in `skill.json`
- [ ] `skill.json` has all required fields
- [ ] `prompt.md` exists and has meaningful content
- [ ] No Anthropic/Claude-specific API references in `prompt.md`
- [ ] `tools` list only contains valid tool names
- [ ] `category` is one of the valid values
- [ ] `enabled: true`
- [ ] Tested: `from core.skills import get_skill; get_skill("your-slug")` returns the skill