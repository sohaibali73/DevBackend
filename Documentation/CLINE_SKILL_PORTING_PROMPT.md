# Cline Agent Prompt: Port Skills from Skill Port Folder

Copy and paste the entire text below as your task to Cline:

---

## TASK: Port All Skills from Skill Port to core/skills/

You are porting skills from `C:\Users\SohaibAli\Desktop\Skill Port` into the backend skill system at `C:\Users\SohaibAli\Videos\Development\DevBackend\core\skills\`.

Read the full porting guide first: `C:\Users\SohaibAli\Videos\Development\DevBackend\Documentation\SKILL_PORTING_GUIDE.md`

---

## SYSTEM ARCHITECTURE (read this carefully before starting)

The backend uses a model-agnostic skill system. Skills are NOT Claude-only. They run through any LLM provider. This means:

1. **NEVER** include references to Anthropic, Claude, the Anthropic Files API, beta headers, skill containers, or `skill_id` in any prompt.md
2. Skills execute by sending the `prompt.md` content as the system prompt to whatever LLM is configured
3. Tools available to skills are a fixed list (see below) — they are NOT bash scripts or Claude code execution containers

The skill system auto-discovers any folder inside `core/skills/` that has both `skill.json` and `prompt.md`.

---

## VALID TOOLS (only these can go in the `tools` array in skill.json)

```
execute_python          — Python code execution in our sandbox
execute_react           — React/JSX component rendering
search_knowledge_base   — Search uploaded user documents
get_stock_data          — Real-time stock prices/history
technical_analysis      — RSI, MACD, Bollinger Bands, etc.
get_stock_chart         — OHLCV candlestick data
web_search              — Live web search
generate_docx           — Create Potomac-branded Word documents
generate_pptx           — Create Potomac-branded PowerPoint
generate_xlsx           — Create Potomac-branded Excel workbooks
edgar_get_financials    — SEC EDGAR financial data
edgar_get_filings       — SEC EDGAR filings
edgar_search_fulltext   — Search SEC EDGAR full text
```

---

## SKILLS TO PORT

Port ALL of the following folders from `C:\Users\SohaibAli\Desktop\Skill Port`:

```
agent-browser
algorithmic-art
article-extractor (1)          ← note the "(1)" in name, slug should be: article-extractor
backtest-expert                ← already exists in core/skills — check if it already has skill.json + prompt.md, if not, port it
backtesting-frameworks         ← already exists in core/skills — check and port if needed
canvas-design
csv-data-summarizer-claude-skill-mai...   ← full folder name, slug: csv-data-summarizer
doc-coauthoring
internal-comms
lead-research-assistant
pdf                            ← already exists in core/skills — check and port if needed
people-search
potomac-researcher
skill-creator
theme-factory
webapp-testing
web-artifacts-builder
web-search
```

**BEFORE PORTING EACH SKILL**: Check if the folder already exists in `core/skills/`. If it exists AND already has both `skill.json` and `prompt.md` with meaningful content, skip it. If it exists but is empty, port it.

---

## PROCESS FOR EACH SKILL (follow this EXACTLY, one skill at a time)

### Step 1: Read the Source

Read ALL files in `C:\Users\SohaibAli\Desktop\Skill Port\{skill-name}\` recursively:
- Find the `SKILL.md` file (may be in a subfolder)
- Find any `references/` folder and read all .md files in it
- Find any `scripts/` folder — note what the scripts do (but do NOT copy them verbatim)
- Note the YAML frontmatter: `name` and `description` fields

### Step 2: Determine the Slug

The slug is the kebab-case folder name. Rules:
- All lowercase
- Hyphens only (no underscores, no spaces)
- Must match the folder name exactly in `core/skills/`
- Special cases:
  - `article-extractor (1)` → slug: `article-extractor`
  - `csv-data-summarizer-claude-skill-mai...` → slug: `csv-data-summarizer`

### Step 3: Determine the Category

Use this mapping:
- Trading strategies, backtesting, finance → `finance`
- Web search, lead generation, research, article extraction, people search → `research`
- Document creation, writing, reports → `document`
- Code generation, debugging → `code`
- Data analysis, CSV, spreadsheets → `data`
- UI design, presentations, visual → `design`
- Everything else → `general`

### Step 4: Determine the Tools

Match the skill's purpose to tools:
- If it needs to analyze data or run calculations → `execute_python`
- If it searches the web → `web_search`
- If it creates Word docs → `generate_docx`
- If it creates presentations → `generate_pptx`
- If it creates spreadsheets → `generate_xlsx`
- If it does financial market analysis → `get_stock_data`, `technical_analysis`
- If it accesses SEC data → `edgar_get_financials`, `edgar_get_filings`
- If it searches user's uploaded documents → `search_knowledge_base`
- If it only generates text analysis/advice → `[]` (empty array)

**IMPORTANT**: Do NOT add tools that the skill doesn't actually need. A backtesting advisor doesn't need `generate_docx`. A web search skill doesn't need `get_stock_data`.

### Step 5: Determine max_tokens

- Simple text generation / advice: `8192`
- Detailed analysis / research reports: `16384`
- Very complex multi-part outputs (docs, spreadsheets): `32768`

### Step 6: Create the Folder and Files

Create `C:\Users\SohaibAli\Videos\Development\DevBackend\core\skills\{slug}\` folder.

**Create `skill.json`:**

```json
{
  "slug": "{slug}",
  "name": "{Human Readable Name From SKILL.md frontmatter}",
  "description": "{description from SKILL.md frontmatter, expanded if needed to 1-2 sentences}",
  "category": "{category}",
  "tools": ["{tool1}", "{tool2}"],
  "output_type": "{text|file|code|data|image}",
  "max_tokens": {8192|16384|32768},
  "timeout": 120,
  "enabled": true,
  "aliases": ["{any-old-slugs-or-alternate-names}"]
}
```

output_type guide:
- `text` — analysis, advice, research, summaries
- `file` — when skill generates downloadable files
- `code` — when skill generates code
- `data` — when skill generates structured data

**Create `prompt.md`:**

Extract the body content from `SKILL.md` (everything AFTER the `---` YAML frontmatter closing line).

Then **clean it**:

REMOVE these patterns entirely:
- Any line containing: "Anthropic", "Claude", "skill_id", "container", "Files API", "beta header", "betas=", "tool_result", "bash script"
- Any sentence like "This skill runs in Claude's code execution environment"
- Any reference to shell commands like `pip install` in a container context
- Any reference to Anthropic-specific APIs

REPLACE these patterns:
- "Claude's code execution" → "the execute_python tool"
- "the code execution container" → "the Python sandbox"
- "bash" or "shell script" execution → "execute the following as Python code"
- "write to /tmp/" → (describe the logic instead, no file paths)

ADD this header if the prompt doesn't already have a role statement:
```
You are an expert [skill name] assistant. [One sentence describing your main purpose.]
```

If the skill has a `references/` folder: **APPEND** the content of each reference file at the bottom of `prompt.md` under a `## Reference Materials` section.

### Step 7: Verify

After creating the files, verify the skill loaded by checking that the files exist and are valid JSON/markdown. You can do a quick sanity check by reading the files back.

---

## EXAMPLE: How to port `web-search`

**Source**: `Skill Port/web-search/SKILL.md` has frontmatter `name: web-search` and the body describes using DuckDuckGo.

**Output `skill.json`**:
```json
{
  "slug": "web-search",
  "name": "Web Search",
  "description": "Search the web for current information, news, articles, and real-time data using DuckDuckGo. Use when the user needs up-to-date information that may not be in training data.",
  "category": "research",
  "tools": ["web_search"],
  "output_type": "text",
  "max_tokens": 8192,
  "timeout": 60,
  "enabled": true,
  "aliases": ["search", "duckduckgo-search"]
}
```

**Output `prompt.md`**: Take the SKILL.md body. Remove any bash/shell execution references. Replace "run the search.py script" with "use the web_search tool". Keep all the guidance about search strategies, best practices, and output formatting.

---

## EXAMPLE: How to port `backtest-expert`

**Source**: `Skill Port/backtest-expert/backtest-expert/SKILL.md` — 206 lines of systematic backtesting methodology. Has `references/failed_tests.md` and `references/methodology.md`.

**Output `skill.json`**:
```json
{
  "slug": "backtest-expert",
  "name": "Backtest Expert",
  "description": "Expert guidance for systematic backtesting of trading strategies. Applies 'beating ideas to death' methodology — stress testing parameters, modeling realistic slippage, preventing look-ahead bias, and interpreting results with professional skepticism. Use when developing, testing, or validating quantitative trading strategies.",
  "category": "finance",
  "tools": ["execute_python", "get_stock_data"],
  "output_type": "text",
  "max_tokens": 16384,
  "timeout": 180,
  "enabled": true,
  "aliases": ["backtester", "strategy-validator", "backtest_expert"]
}
```

**Output `prompt.md`**: Full SKILL.md body + append methodology.md and failed_tests.md content at the bottom under `## Reference Materials`.

---

## IMPORTANT RULES

1. **Port one skill at a time** — complete each skill fully (both files) before moving to the next
2. **Do not skip skills** — port every folder in the list
3. **Do not invent content** — the prompt.md content should come FROM the source SKILL.md, not be invented
4. **Preserve the expertise** — the source SKILL.md files contain real expert knowledge. Keep it all, just clean the Claude-specific stuff
5. **If a source skill has Python scripts** (`scripts/` folder) — DO NOT copy the scripts verbatim. Instead, describe in the prompt what the skill should do, and rely on the `execute_python` tool to run Python dynamically. The scripts are reference implementations, not deployable files.
6. **If you cannot determine the correct category or tools** — default to `category: "general"` and `tools: []`
7. **The `aliases` field** — add any obvious alternate names someone might use to invoke the skill (e.g., for `article-extractor` add `["article-extraction", "extract-article"]`)

---

## SKILLS THAT ALREADY EXIST IN core/skills/

These folders already exist in `core/skills/` — check each one:
- `afl-developer` — likely already ported, check and skip if complete
- `artifacts-builder` — check and skip if complete
- `backtest-expert` — check and skip if complete, otherwise port
- `backtesting-frameworks` — check and skip if complete, otherwise port
- `datapack-builder` — check
- `dcf-modeler` — check
- `doc-interpreter` — check
- `document-writer` — ALREADY COMPLETE (has skill.json + prompt.md), SKIP
- `financial-researcher` — check
- `initiating-coverage` — check
- `market-bubble-detector` — check
- `pdf-processor` — check (this is the `pdf` skill)
- `presentation-designer` — check
- `quant-analyst` — check
- `spreadsheet-builder` — check

For each of these: if the folder has `skill.json` AND `prompt.md` with real content → SKIP. If either file is missing or empty → PORT IT.

---

## ORDER OF OPERATIONS

Port in this order (start with simplest, end with complex):
1. web-search
2. article-extractor
3. people-search
4. lead-research-assistant
5. potomac-researcher
6. csv-data-summarizer
7. doc-coauthoring
8. internal-comms
9. skill-creator
10. backtest-expert (if not already complete)
11. backtesting-frameworks (if not already complete)
12. agent-browser
13. webapp-testing
14. canvas-design
15. theme-factory
16. web-artifacts-builder
17. algorithmic-art

After completing all of the above, check and fill in any of the existing `core/skills/` folders that are empty (missing skill.json or prompt.md).

---

## DONE SIGNAL

When all skills are ported, output a summary table:

```
| Skill Slug | Status | Category | Tools |
|---|---|---|---|
| web-search | ✅ Ported | research | web_search |
| backtest-expert | ✅ Already existed | finance | execute_python, get_stock_data |
| ... | ... | ... | ... |
```

This confirms everything is complete.
