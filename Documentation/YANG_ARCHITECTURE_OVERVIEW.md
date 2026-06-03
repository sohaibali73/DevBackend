# YANG Backend — High-Level Architecture Overview

> Audience: the platform author, for hand-drawing architecture diagrams.
> Scope: synthesized from verified subsystem code-reader maps. Verified numbers are flagged where they differ from prior marketing claims.

---

## 1. What YANG Is

YANG is the proprietary agentic AI backend powering **Analyst by Potomac**, an AI-powered AmiBroker AFL (AmiBroker Formula Language) development and financial-research platform built in-house at Potomac Fund Management. It is a **FastAPI + Uvicorn (Python 3.11)** REST/streaming backend deployed on **Railway**, fronting **47 domain-specific route modules** behind Supabase-JWT authentication. At its core sits a **multi-provider LLM abstraction** (Anthropic Claude as primary, with OpenAI, OpenRouter, and Vercel AI Gateway behind a single registry) wrapped by an **agentic orchestration layer ("YANG")** that supports parallel sub-agent dispatch, parallel tool execution, rolling conversation focus tracking, checkpoints, auto-compaction, and an autonomous goal runner (`yang_autopilot`). Around that core are firm-specific subsystems: a **tools-and-skills registry** (80 built-in tools + dynamic desktop/workflow tools + loadable expert skills), a **financial data integration layer** (SEC EDGAR, Yahoo Finance, a 75,015-security Norgate universe), a dedicated **AFL generation → 19-phase validation → backtest-analysis pipeline**, and a **Content Studio / humanize / generative-UI streaming** stack that produces versioned, branded `.pptx`/`.docx`/`.site` artifacts and streams them to the frontend over the Vercel AI SDK protocol.

---

## 2. The Stack at a Glance

| Layer | Technology | Role |
|---|---|---|
| Deployment / Infra | Railway (container + volumes), Nixpacks (Python 3.11, poppler_utils, tesseract5), Uvicorn (2 workers, `0.0.0.0:8080`) | Hosting, build, process management, persistent volume (`/data`, `$STORAGE_ROOT`) |
| Web / API | FastAPI, middleware stack (rate limit 120/min per IP, CORS, public-sites host routing, Smart GZip, perf timing), 47 routers | HTTP/SSE entry, routing, request lifecycle |
| Auth | Supabase GoTrue, PyJWT (HS256 local verify), Redis cache (300s), Fernet (AES-128-CBC) | JWT verification, per-user API-key decryption |
| LLM Providers | Anthropic SDK (primary), OpenAI SDK, OpenRouter (300+ models), Vercel AI Gateway (100+ models) | Model execution behind a provider-agnostic registry |
| LLM Core | `core/llm/*` (BaseLLMProvider, registry, router), `core/prompt_cache.py`, `core/streaming.py`, `core/context_manager.py` | Provider routing, prompt caching, unified streaming, context budgeting |
| Agent Core (YANG) | `core/yang/*`, `core/yang_autopilot.py`, `core/agent_team*.py`, `core/consensus_engine.py`, `core/task_manager.py`; asyncio | Sub-agent dispatch, parallel tools, focus chain, checkpoints, auto-compaction, goal runner, multi-agent teams, consensus |
| Tools / Skills | `core/tools.py` (80 defs), `core/tools_v2/*`, `core/desktop_tools.py`, `core/yang_cu_tools.py`, `core/yang_workflow_tools.py`, `core/skills/*` | Unified tool registry + skill workflows (multi-turn LLM loops) |
| Data Integrations | `core/edgar_client.py`, `api/routes/yfinance.py`, `core/norgate_index.py`, `core/researcher*.py`, Voyage AI embeddings, Tavily, Finnhub, FRED, NewsAPI, FinBERT | Fundamentals, prices, ticker universe, web research, RAG |
| Document Generation | `core/tools_v2/document_tools.py`, pptxgenjs (Node subprocess), python-pptx/docx, openpyxl/pandas, PyMuPDF/pypdf/Pillow | PPTX/DOCX/XLSX/site artifacts |
| Storage / DB | Supabase PostgreSQL (asyncpg pool, port 6543) + pgvector, Supabase Storage, Redis, 3-tier file store (memory → Railway volume → Supabase bucket) | Persistent state, caching, artifact persistence |
| Frontend Protocol | Vercel AI SDK Data Stream Protocol (legacy) + v5 SSE + v7 Beta UI Message Stream (`core/ui_message_*`, `core/vercel_ai.py`) | Streaming text + generative-UI events to Next.js `useChat` |

---

## 3. System Architecture (the big picture)

Top-to-bottom master diagram. Each layer lists **boxes** and **arrows**.

### Layer 1 — Client
- **Boxes:** Next.js frontend (`useChat`), Studio Editor UI, Desktop client (advertises fs/shell/computer/outlook capabilities + CU/browser tools).
- **Arrows:** Client → API with `JWT Bearer` token. Desktop client ⇄ backend bidirectionally (advertises capabilities; receives client-executed tool calls; returns results).

### Layer 2 — API / Gateway (`main.py`)
- **Boxes (middleware, in order):** Rate Limit (120/min per IP, in-memory) → CORS (open) → Public-Sites Host routing → Smart GZip (skips streaming paths) → Perf-timing. Then **47 route modules**. Then the **dependency-injection chain**: `get_current_user_id` (JWT verify) → `get_current_user` (profile auto-create) → `get_user_api_keys` (decrypt) → `verify_admin`.
- **Arrows:** Request flows down the middleware chain → router → DI chain → core logic. GZip is **bypassed** for streaming paths: `/chat/agent`, `/chat/sse`, `/ai/`, `/agent/`, `/researcher/stream`, `/skills/execute/stream`, `/consensus/stream`.
- **Startup (lifespan):** asyncpg pool (8s) → Redis (4s) → httpx client (2s) → Node worker pool (15s) → task manager — each timeout-wrapped with independent error handling (no boot cascade).

### Layer 3 — Agent Orchestration (YANG)
- **Boxes:** Config gate (`YangConfig`, loaded per-user DB + per-request overrides) → Dispatch & Execution (`spawn_subagents`, `execute_tool_calls_parallel`, background-edit task queue) → Memory & State (`focus_chain`, `checkpoints`, `auto_compact`, goal steps) → Multi-agent Coordination (`agent_team`, `agent_team_v2`, `consensus_engine`) → Goal runner (`yang_autopilot.tick_goal`).
- **Arrows:** Chat route checks feature gates → if `subagents`, fan out via `asyncio.gather` (≤5, semaphore) → if `parallel_tools`, partition into read-only Phase 1 (parallel) + side-effect Phase 2 (sequential) → update focus chain → optional completion verification (Haiku) → optional background auto-compaction. Solid arrows = hot path; dashed = `asyncio.create_task` background jobs; parallel lines = `asyncio.gather`.

### Layer 4 — LLM Provider Router (`core/llm/`)
- **Boxes:** `get_provider_for_model(model_str, api_keys)` → `LLMProviderRegistry` (`_model_map` exact, `_prefix_map` prefix, default fallback) → 4 provider impls (Anthropic / OpenAI / OpenRouter / Vercel) extending `BaseLLMProvider`. Support: `normalize_tools` / `normalize_messages`, prompt-cache helpers, `stream_claude_response` tool-use loop, `context_manager`.
- **Arrows:** model string → registry lookup → provider instance → `stream_chat`/`chat` → normalize → SDK call → unified `StreamChunk`/`LLMResponse`. Tool-use loop: stream → accumulate → execute tools → append results → continue until `stop_reason != 'tool_use'`.

### Layer 5 — Tools / Skills (`core/tools.py` + `core/skills/`)
- **Boxes:** `handle_tool_call()` entry → dispatch via `_STATIC_DISPATCH` (fast, ~40 stateless tools) OR injected-dep `if/elif` (6 tools needing `api_key`/`supabase_client`) OR skill-dispatch (`_invoke_skill`, `run_<slug>`) OR `tools_v2` document/site tools. Skill side: `loader` (two roots) → `router` (validation, AFL blocking) → `executor` (multi-turn LLM loop + sandbox). Tool sources: 80 built-in, 30 desktop, 40 Yang (CU 19 + workflow 21), 26 skills-as-tools.
- **Arrows:** Provider tool-use loop → `handle_tool_call` → dispatch → handler returns JSON → back into loop. Skill executor recursively re-enters tool dispatch.

### Layer 6 — Data & Document Subsystems
- **Boxes:** Financial data (`edgar_client`, `yfinance` routes, `norgate_index`, `researcher_engine`, embeddings/RAG pipeline). Document gen (`tools_v2/document_tools` via pptxgenjs subprocess + python-pptx). Content Studio (`studio/*`), humanize (`humanize/*`), styles (`styles/*`).
- **Arrows:** Tools/skills call data clients → external APIs. Document tools write artifacts → `chat_hook.materialize_tool_result` → Studio artifact versions. AFL path: `afl.py` → `ClaudeAFLEngine` → `afl_validator` (19 phases) → result.

### Layer 7 — Storage / DB / Streaming-out
- **Boxes:** Supabase PostgreSQL (asyncpg, port 6543) + pgvector, Supabase Storage buckets, Redis (cache + LRU/TTL fallback), 3-tier file store (memory 4h TTL → Railway volume `/data/generated` → Supabase bucket), UI-stream encoders (`ui_message_stream`, `ui_message_sse`, `ui_message_translator`, `ui_message_adapter`).
- **Arrows:** Core logic ⇄ Postgres/Redis. Generated files written 3-tier (background to Supabase). All streamed output encoded → Vercel AI SDK protocol → Layer 1 client.

---

## 4. Subsystem Deep-Dives

### 4.1 API Layer & Infrastructure
- **Purpose:** FastAPI entry, JWT auth, routing to 47 modules, orchestrating Postgres/Redis/LLM/file storage.
- **Boxes:** `main.py` (app + lifespan + middleware), `config.py`, `api/dependencies.py` (DI chain), `db/async_db.py`, `db/supabase_client.py`, `core/cache.py`, `core/encryption.py`, `core/http_client.py`, `core/file_store.py`, `core/storage.py`.
- **Data flow:** Client (JWT) → 5 middleware → router → DI chain (verify → profile → decrypt keys → admin) → core logic → JSON/SSE response. Fast auth: local HS256 decode with 300s Redis cache, Supabase fallback when unconfigured. Service-role RLS bypass + a **fresh auth client per call** prevents session bleed under concurrency.

### 4.2 Multi-Provider LLM Core
- **Purpose:** Provider-agnostic routing, streaming, prompt caching, context management.
- **Boxes:** `BaseLLMProvider` (abstract) → 4 impls; `LLMProviderRegistry`; `stream_claude_response` (tool loop); `normalize_tools`/`normalize_messages`; `prompt_cache` (`as_cached_system`, `mark_tools_cached` → `cache_control: ephemeral`); `context_manager` (`estimate_tokens`, `truncate_contexts_batch`).
- **Data flow:** model string → registry (exact then prefix) → provider → normalize → SDK → unified `StreamChunk`/`LLMResponse`. Context path merges conversation/system/KB/training/research sources, token-budgets each, returns optimized message list.

### 4.3 YANG Agentic Core
- **Purpose:** Parallel sub-agents, parallel tools, focus tracking, checkpoints, auto-compaction, autonomous goals, multi-agent teams, consensus.
- **Boxes (4 swim lanes):** (1) Chat-route feature gates + `settings.py` (`YangConfig`, frozen). (2) Dispatch: `subagents.py` (≤5 via `asyncio.gather` + semaphore; researcher/analyst/kb_searcher roles; Sonnet primary, Haiku fallback), `parallel_tools.py` (Phase 1 read-only parallel ≤5 + Phase 2 sequential, order-preserving, heartbeats), `background_edit.py` (defers pptx/docx/xlsx to tasks; 200-entry/5-min store). (3) State: `focus_chain.py` (regex extraction + optional Haiku polish every N turns, injected as un-cached `<focus_chain>` block), `checkpoints.py` (high-water-mark `last_message_id`, soft-delete), `auto_compact.py` (Haiku summarizes oldest 60% past threshold). (4) Coordination: `agent_team.py` (sequential leader→researcher→analyst→critic→synthesizer), `agent_team_v2.py` (sequential/parallel/hybrid 4-phase), `consensus_engine.py` (N models parallel, Jaccard similarity matrix, tier-weighted agreement). Plus `plan_guard.py` (READ_ONLY_TOOLS allowlist for Plan Mode), `completion_verifier.py` (secondary Haiku, one retry), `yolo.py` (no-confirm, caps iterations at 10), `task_manager.py` (in-memory queue, 20/user, 600s timeout, 3600s TTL), `yang_autopilot.py` (goal runner; `tick_goal`; `goal_steps`; desktop futures; Voyage memory; cron `scheduled_jobs`; SSE fan-out via `asyncio.Queue`).
- **Data flow:** `ChatAgentRequest` + overrides → `load_yang_config` merge → gate checks → dispatch (subagents/parallel-tools) → focus update → verify → background compact. Goals run separately on a ticker; emit SSE `status/step/artifact` to subscribers.

### 4.4 Tools & Skills System
- **Purpose:** Unify built-in + dynamic + desktop + skills into one provider-agnostic registry; skills run higher-level multi-turn workflows.
- **Boxes:** `core/tools.py` (7,367 lines; **80** `TOOL_DEFINITIONS`; `handle_tool_call`), `tools_v2/registry.py` (provider normalization), `tools_v2/document_tools.py` (9 doc tools), `tools_v2/site_tools.py` (2 site tools), `desktop_tools.py` (**30**: fs 11 / shell 2 / computer 11 / outlook 5), `yang_cu_tools.py` (**19** CU tools), `yang_workflow_tools.py` (**21** workflow tools), `skills/loader.py` (two roots + DB decoration), `skills/router.py` (AFL blocking), `skills/executor.py` (LLM loop + sandbox + timeout/partial recovery), `skill_storage.py`, `uploads.py`, `skill_gateway.py`.
- **Data flow:** tool-use loop → `handle_tool_call` → `_STATIC_DISPATCH` (fast) | injected-dep `if/elif` | skill-dispatch `_invoke_skill` | `tools_v2` → JSON. Skills discovered from `core/skills/` (lightweight, 23) + `ClaudeSkills/` (bundle, 3) with mtime cache. **AFL slugs (afl-developer/afl/amibroker) are blocked** in router/gateway and forced through `ClaudeAFLEngine` + `AFLValidator`.

### 4.5 Financial Data Integration Layer
- **Purpose:** Unify SEC EDGAR + Yahoo Finance + Norgate to power research, analysis, RAG.
- **Boxes:** `edgar_client.py` (+ `routes/edgar.py`), `routes/yfinance.py`, `norgate_index.py` (+ `ALL NORGATE TICKERS.txt`), `performance_engine.py`, RAG pipeline (`file_rag.py`, `embeddings.py` Voyage + Redis 30-day cache, `rag_chunker.py` sentence-aware 1500-char), `routes/knowledge_base.py`, `routes/research.py`, `researcher.py`, `researcher_engine.py`.
- **Data flow:** EDGAR — ticker→CIK resolution (24h cache, 10 req/s) → submissions → financials/filings/XBRL. yfinance — `yf.Ticker(symbol)` → DataFrame → JSON. Norgate — lazy singleton parses ticker file once → in-memory indices → O(1) exact / ranked (exact>prefix>word). RAG — upload → chunk → Voyage embed (cached) → Supabase `file_chunks`; query → embed → vector search → top-k injection.
- **Verified numbers:** **75,015 securities** across **9 databases** (source file **300,111 lines / ~12 MB**) — the "~75,000 Norgate securities" claim is **confirmed (exact 75,015)**.

### 4.6 AFL Generation, Validation & Backtesting Engine
- **Purpose:** NL prompt → AFL code → multi-phase validation → backtest-result analysis.
- **Boxes:** `afl_validator.py` (**19 validation phases**; ERROR_CODES errors 1–54, 90–94, 701–706 + WARNING_CODES 501–503 = **68 documented codes**), `claude_engine.py` (`ClaudeAFLEngine`, `BacktestSettings` dataclass, streaming/non-streaming), `routes/afl.py` (`/afl/generate|optimize|debug|explain|validate`; 3-phase conversation workflow), `routes/backtest.py` (upload, AI insights, metrics, comparison), `prompts/base.py`, skills `backtest-expert` + `backtesting-frameworks`.
- **Data flow:** `POST /afl/generate` → `ClaudeAFLEngine.generate_afl()` (Claude Opus 4-6 + base prompt) → AFL string → `afl_validator.validate()` (19 phases; cascading-error detection cross-references within 5 lines) → `ValidationResult` → frontend + Supabase (`afl_codes`/`afl_history`). Backtest: upload → Claude Opus 4-6 analysis → metrics + recommendations → `backtest_results`.
- **Verified numbers:** the **"19-phase AFL validator" claim is CONFIRMED** (19 phases enumerated in `afl_validator.py`).

### 4.7 Content Studio, Humanize & Generative UI
- **Purpose:** Versioned `.pptx`/`.docx`/`.site` artifacts with visual editing; humanize text rewriting; generative-UI streaming.
- **Boxes:** Studio — `projects.py` (versioned `$STORAGE_ROOT/projects/{id}/v{n}.{ext}`), `sites.py` + `site_sandbox.py` (ESM importmap + Babel + Tailwind wrap), `edits.py`, `chat_hook.py` (auto-capture tool outputs as artifact versions). Styles — `cloner.py` (voice card), `injector.py`, `embeddings.py` (all-MiniLM-L6-v2, 384-dim, pgvector fallback). Humanize — `pipeline.py` (fingerprint scrub → parallel `unified_rewrite` chunks → fact_guard + retry), `passes.py`, `detectors.py` (Binoculars/GLTR/RoBERTa + stylometric ensemble). UI streaming — `ui_message_stream.py` (v7 Beta), `ui_message_sse.py` (v5 SSE), `ui_message_translator.py`, `ui_message_adapter.py`, `vercel_ai.py`; `artifacts.py`, `artifact_parser.py`; `Documentation/BACKEND_GENUI_PROTOCOL.md`.
- **Data flow:** `POST /chat/agent` → stream Claude → tool results encoded as SSE data events → `chat_hook.materialize_tool_result` silently registers pptx/docx into `studio_projects` → bytes back via `StreamingResponse`. Humanize: `POST /studio/humanize` → `pipeline.run` (scrub → parallel chunk rewrite via ThreadPoolExecutor → fact_guard → detect) → `trace.json` + `studio_humanization_runs` row. Sites auto-sandboxed at `build_zip_from_files()`.

---

## 5. Key Request Flows (sequence-diagram guidance)

### Flow A — Chat turn that calls a tool and streams back
**Lanes:** Client (Next.js) · API/Middleware (`main.py`) · DI chain · YANG agent core · LLM router/provider · Tool dispatch (`handle_tool_call`) · Supabase/Redis.
1. Client → `POST /chat/agent` with JWT + messages + model.
2. Middleware: rate-limit → CORS → host routing → **GZip bypass** (streaming path) → perf timing.
3. DI: `get_current_user_id` (local HS256, Redis 300s cache) → `get_current_user` → `get_user_api_keys` (Fernet decrypt) → admin check.
4. YANG: `load_yang_config` (DB + overrides) → feature-gate checks → (optional) `spawn_subagents` / focus-chain prep.
5. LLM router: `get_provider_for_model` → registry → provider `stream_chat` → normalize tools/messages → SDK stream begins (text deltas streamed out).
6. Provider yields `tool_use` → `stream_claude_response` calls `handle_tool_call` → dispatch (static/injected/skill). If `parallel_tools`, Phase 1 read-only batch via `asyncio.gather` + heartbeats, Phase 2 sequential.
7. Tool returns JSON → appended as `tool_result` → loop continues until `stop_reason != tool_use`.
8. `update_focus_deterministic`; optional Haiku completion verification; optional background auto-compaction (`asyncio.create_task`).
9. SSE encoder streams text-delta + `data-*` GenUI events → Client; messages persisted to Supabase.

### Flow B — AFL generation and validation
**Lanes:** Client · `routes/afl.py` · `ClaudeAFLEngine` · Anthropic (Opus 4-6) · `afl_validator.py` · Supabase.
1. Client → `POST /afl/generate`.
2. `afl.py` runs 3-phase conversation workflow (INITIAL ask questions → AWAITING_ANSWERS → GENERATING) — mandatory questions (strategy type, trade timing). **Skill router blocks AFL slugs; path is forced through `ClaudeAFLEngine`.**
3. `ClaudeAFLEngine.generate_afl()` → Anthropic Opus 4-6 with `prompts/base.py` system prompt (optional extended thinking) → AFL string.
4. `afl_validator.validate()` runs **19 phases**; Phase 13 cascading detection cross-references primary/secondary errors (≤5-line proximity).
5. `ValidationResult` (error/warning/info/suggestion counts; issues sorted by line) → returned to client + saved to `afl_codes`/`afl_history`.
6. (Backtest variant) `POST /backtest/upload` → Opus 4-6 analysis → metrics + recommendations → `backtest_results`.

### Flow C — Potomac-branded document generation
**Lanes:** Client · API/YANG · Tool dispatch · `tools_v2/document_tools.py` · Node subprocess (pptxgenjs) · `chat_hook.py` · Studio (`projects.py`) · Storage (volume + Supabase).
1. Chat turn triggers `generate_pptx` (or docx/xlsx) tool call.
2. If `background_edit` enabled, YANG defers to `asyncio.create_task`, returns `task_id` immediately; frontend polls.
3. `handle_tool_call` → `tools_v2/document_tools.py` → pptxgenjs Node subprocess (PPTX) / python-docx / openpyxl.
4. Output bytes → `register_artifact_from_bytes` writes `$STORAGE_ROOT/projects/{id}/v{n}.{ext}` + inserts `studio_artifacts` row.
5. `chat_hook.materialize_tool_result` auto-registers the file as a new Studio artifact version if the conversation is a Studio project.
6. 3-tier file store: memory (4h TTL) → Railway volume → Supabase bucket (background).
7. `data-file_download` GenUI event streamed to client; artifact retrievable from Studio.

> **Branding note / unsupported claim:** the maps describe document *generation* (pptxgenjs/python-pptx, templates `generate_pptx_template`) and a `COLOR_PALETTE` constant in `core/prompts/base.py`, but **no map explicitly documents a "Potomac brand kit / theme" system**. Treat "Potomac-branded" as a product intent layered on `generate_pptx_template` + palette constants, not a verified dedicated subsystem.

---

## 6. Diagramming Guidelines

**Diagram types per view:**
- **Section 3 (master architecture):** C4-style **Container diagram** — one box per subsystem/layer, arrows for runtime calls. Keep to 7 horizontal layers on one page.
- **Section 5 (request flows):** **Sequence diagrams** (UML), one per flow, lanes = participants listed above.
- **Financial data:** a dedicated **data-source map** (radial: core clients in center, external APIs on the right, persistence at bottom — per subsystem 4.5 `diagram_notes`).
- **Tools/skills:** a **catalog / matrix** — rows = tool sources (80 built-in, 30 desktop, 19 CU, 21 workflow, 26 skills), columns = dispatch path (static / injected / skill / tools_v2).
- **AFL validator:** a **vertical pipeline** of 19 numbered checkpoints feeding Phase 13 (cascading), output = color-coded `ValidationResult`.

**Color / grouping conventions:**
- Infra/storage = **gray**; API/middleware = **slate**; LLM core = **purple**; YANG agent core = **teal**; tools/skills = **orange**; financial data = **green**; AFL pipeline = severity colors (ERROR red / WARNING orange / INFO blue / SUGGESTION green); Content Studio = **yellow**; humanize = **blue**; GenUI events = **green**.
- **Solid arrows** = synchronous hot path; **dashed** = `asyncio.create_task` background; **parallel double-lines** = `asyncio.gather` fan-out (annotate semaphore caps, e.g. "≤5 subagents", "Phase 1 ≤5 tools").

**One page vs. break out:**
- One page: the 7-layer container diagram (Section 3) and each sequence diagram.
- Break out: YANG agent core (4 swim lanes), the tools/skills catalog, the financial data-source map, and the 19-phase AFL pipeline — each is too dense to share a page with the master.

**Suggested 5–6 diagram set:**
1. Master container diagram (Section 3, 7 layers).
2. YANG agent-core swim-lane diagram (4 lanes; highlight 3 parallel mechanisms: subagents, parallel-tools, agent-team phases).
3. LLM provider-router diagram (registry exact/prefix → 4 providers → unified contracts + tool-use loop).
4. Tools/skills catalog matrix + dispatch decision point (`run_*`/`generate_*`? → `_invoke_skill`; AFL slug → blocked → mandatory engine).
5. AFL 19-phase validation pipeline (vertical, severity-colored).
6. Financial data-source map (EDGAR / yfinance / Norgate + RAG, with Supabase + Redis persistence).
   *(Optional 7th: a Content Studio + humanize + GenUI streaming stack diagram.)*

---

## 7. Why YANG Is Not Any Other Platform

An honest, stack-anchored argument. Each differentiator points to a named module.

**vs. general assistants (ChatGPT, Gemini):**
- **Firm-native tool/skill integration.** YANG is not a chat box around a model; it is a tool/skill *registry* (`core/tools.py`, 80 defs + 70 dynamic + 26 loadable skills) wired into Potomac's own data and workflows. General assistants expose generic tools; YANG ships domain meta-tools like `run_backtest_analysis` and a skill executor (`skills/executor.py`) running multi-turn loops with firm-specific system prompts.
- **Multi-provider routing.** `core/llm/registry.py` routes any model string (Anthropic primary; OpenAI/OpenRouter 300+/Vercel 100+ as fallbacks) behind one contract. ChatGPT/Gemini are single-vendor by construction.
- **Agentic sub-agent dispatch.** `core/yang/subagents.py` fans out role-specialized sub-agents under a semaphore via `asyncio.gather`, with checkpoints, auto-compaction, and an autonomous goal runner (`yang_autopilot.py`). *Caveat:* the marketing phrase "parallel sub-agent dispatch" is **verified but bounded** — the cap is **≤5 subagents**, not unlimited.

**vs. financial AI platforms (BloombergGPT, FactSet Mercury, Kensho):**
- **The AFL pipeline is the moat.** No mainstream financial-AI platform generates and *validates* AmiBroker AFL. YANG has a dedicated `ClaudeAFLEngine` plus a **19-phase validator** (`afl_validator.py`) emulating 68 AmiBroker error/warning codes with cascading-error detection. This is the most platform-specific asset and is **code-verified**.
- **The Norgate universe.** `core/norgate_index.py` indexes **75,015 securities across 9 databases** in-memory for O(1) lookup — a quant-grade symbol universe, not a vendor terminal feed.
- **Open data composition.** YANG composes EDGAR + yfinance + Tavily + Finnhub + FRED + Voyage RAG (`researcher_engine.py`) rather than locking to one proprietary feed. *Caveat:* this is breadth over the depth/licensing of Bloomberg/FactSet's proprietary datasets — a structural difference, not a claim of superior data.

**vs. quant platforms (QuantConnect Mia):**
- **AmiBroker-native, not Python-research-native.** QuantConnect targets its own LEAN/Python engine; YANG targets **AmiBroker AFL** end-to-end (generation → 19-phase validation → `backtest_results` analysis). Different target language, different validator, different user.
- **Generative-UI + branded document output.** YANG streams artifacts (versioned `.pptx`/`.docx`/`.site`) via the Vercel AI SDK protocol (`core/ui_message_*`), auto-captured into a versioned Content Studio (`studio/projects.py`) and wrapped in client sandboxes (`site_sandbox.py`). This is a content-production capability quant platforms don't have.
- **Humanize + voice-cloning pipeline.** `core/humanize/pipeline.py` + `core/styles/cloner.py` (detector ensemble, voice cards) is an editorial layer with no analog in quant tooling.

**Claims to flag as NOT fully supported by the code maps:**
- **"60+ tools":** *Undercount.* The verified built-in count is **80** (`TOOL_DEFINITIONS`), plus ~70 dynamic and 26 skills-as-tools — total far exceeds 60.
- **"Potomac-branded documents":** generation + template + palette exist, but **no dedicated brand-kit subsystem** is documented (see Flow C note).
- **Sub-agent parallelism is real but capped at ≤5**; do not draw it as unbounded fan-out.
