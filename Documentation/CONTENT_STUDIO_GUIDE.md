# Content Studio — Backend Guide

## Overview

Content Studio is a project-centric layer on top of the existing chat engine.
A **Project** wraps a `conversations` row with metadata (kind, style profile,
humanize settings) and an ordered list of **versioned artifacts** (`.pptx` /
`.docx`) that live on the Railway volume.

There are **NO new chat or generation endpoints**. All generation flows
through the existing `POST /chat/agent`. When a chat is bound to a Studio
project, generated `.pptx`/`.docx` files are automatically captured as
artifact versions by an internal hook.

```
$STORAGE_ROOT/projects/{project_id}/v{n}.pptx
$STORAGE_ROOT/projects/{project_id}/v{n}.docx
$STORAGE_ROOT/projects/{project_id}/edit_state/v{n}.json
$STORAGE_ROOT/styles/{style_id}/samples/{sample_id}.txt
$STORAGE_ROOT/styles/{style_id}/voice_card.json
$STORAGE_ROOT/humanize/{run_id}.json
$STORAGE_ROOT/models/hf_cache/             # Binoculars / GLTR / Roberta
```

---

## SQL Migrations (paste into Supabase SQL Editor in order)

1. `db/migrations/027_studio_projects.sql`
2. `db/migrations/028_studio_writing_styles.sql`
3. `db/migrations/029_studio_humanization_runs.sql`

All migrations are idempotent.

---

## Endpoint Reference

All routes require the standard `Authorization: Bearer <jwt>` header.

### Projects (`/studio/projects`)

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/studio/projects` | `{kind:'pptx'|'docx'|'chat', title?, description?, style_profile_id?, humanize_settings?, conversation_id?, tags?}` | `{project}` |
| GET | `/studio/projects?kind=pptx&include_archived=false&limit=100&offset=0` | – | `{projects, count}` |
| GET | `/studio/projects/{id}` | – | `{project, artifacts}` |
| PATCH | `/studio/projects/{id}` | partial: `{title?, description?, style_profile_id?, humanize_settings?, tags?, is_archived?, current_artifact_id?, thumbnail_path?, touch_opened?}` | `{project}` |
| DELETE | `/studio/projects/{id}?purge_files=true` | – | `{deleted:true,id}` |
| GET | `/studio/projects/{id}/artifacts` | – | `{artifacts}` |
| GET | `/studio/projects/{id}/artifacts/{aid}` | – | `{artifact}` |
| GET | `/studio/projects/{id}/artifacts/{aid}/download` | – | binary `.pptx`/`.docx` stream |
| POST | `/studio/projects/{id}/artifacts/{aid}/edit` | `{ops:[op,...], save_edit_state?:true}` | `{artifact}` (new version) |
| POST | `/studio/projects/{id}/artifacts/upload` | multipart `file` | `{artifact}` |

### Visual editor `ops` shapes

**PPTX:**
```json
{"type":"text",          "slide": 1, "shape_index": 2, "value": "New title"}
{"type":"text_replace",  "slide": 3, "find": "Q1", "replace": "Q2", "all": false}
{"type":"add_slide_note","slide": 1, "value": "Speaker note"}
{"type":"reorder_slides","order": [3,1,2,4]}
{"type":"delete_slide",  "slide": 2}
{"type":"duplicate_slide","slide": 1}
```

**DOCX:**
```json
{"type":"text_replace",     "find":"FY24", "replace":"FY25", "all": true}
{"type":"replace_paragraph","index": 4, "value": "New paragraph text"}
{"type":"append_paragraph", "value":"…", "style":"Normal"}
{"type":"append_heading",   "value":"…", "level": 1}
```

Unknown op types are skipped (not errored) so the frontend can ship new ops
without backend updates.

### Writing-Style (Voice Cloning) (`/studio/styles`)

The frontend wizard:
1. Create style → `POST /studio/styles {name}`
2. Add samples → `POST /studio/styles/{id}/samples` (text) or `/samples/upload` (file)
3. Analyze → `POST /studio/styles/{id}/analyze` (Claude-based; falls back to stats-only if no key)
4. Vibe-check → `POST /studio/styles/{id}/preview {prompt}`
5. Attach to project → `PATCH /studio/projects/{pid} {style_profile_id}`

Once a style is `status:'ready'` and attached to a project, the chat hook
auto-injects the voice into `/chat/agent` for that conversation. No frontend
work needed beyond setting `style_profile_id` on the project.

| Method | Path | Notes |
|---|---|---|
| POST | `/studio/styles` | `{name, description?, icon?, color?}` |
| GET | `/studio/styles` | list (returns sample_count, fidelity_score) |
| GET | `/studio/styles/{id}` | full style + samples |
| PATCH | `/studio/styles/{id}` | rename, etc. |
| DELETE | `/studio/styles/{id}` | |
| POST | `/studio/styles/{id}/samples` | `{text, title?, source_url?, source_file_id?}` |
| POST | `/studio/styles/{id}/samples/upload` | multipart `file` (txt/md/docx/pdf) |
| GET | `/studio/styles/{id}/samples` | |
| DELETE | `/studio/styles/{id}/samples/{sid}` | |
| POST | `/studio/styles/{id}/analyze?self_test=true` | builds voice_card + system_prompt + fidelity score |
| POST | `/studio/styles/{id}/preview` | `{prompt, max_tokens?}` → `{output}` |
| GET | `/studio/styles/{id}/system_prompt` | inspect built prompt |

### Humanizer (`/studio/humanize`)

```http
POST /studio/humanize
{
  "text": "...",
  "intensity": "light" | "standard" | "max",
  "seo_target": "linkedin" | null,
  "style_profile_id": "uuid?",
  "project_id": "uuid?",
  "preserve_facts": true
}
```

Returns:
```json
{
  "run_id": "uuid",
  "output": "...",
  "input": "...",
  "scores": {
    "ai_detection": 0.18,
    "components": {"stats":0.21, "binoculars":0.16, "gltr":0.19, "roberta":0.14},
    "binoculars_ratio": 1.32,
    "gltr": {"top1_pct":0.31,"top10_pct":0.62,"top100_pct":0.84,"ai_score":0.41},
    "roberta_p_ai": 0.14,
    "style_fidelity": 0.78,
    "stats_in":  {...},
    "stats_out": {...},
    "ai_detection_in": 0.71
  },
  "passes_summary": [...],
  "lost_facts": {"numbers":[],"quotes":[],"names":[]},
  "detector_retries": 1,
  "duration_ms": 14820
}
```

Other endpoints:
- `POST /studio/humanize/score {text}` — score only, no rewrite
- `GET /studio/humanize/runs?project_id=...` — list past runs
- `GET /studio/humanize/runs/{run_id}` — full trace (loads from volume)

The chat agent can also call this internally as the `humanize_text` tool.

---

## Voice Cloning — what's actually in the voice_card

Two halves:

```jsonc
voice_card.quantitative {
  sentence_len_avg, sentence_len_stdev, burstiness,
  ttr, hapax_ratio, avg_word_len,
  function_word_ratio, contractions_per_100w,
  starts_with_conjunction_pct, flesch_reading_ease,
  punctuation_per_1000c: {comma, em_dash, ellipsis, ...},
  ai_fingerprint_total: {phrase: count}
}

voice_card.qualitative {
  voice: {register, formality, warmth, authority, humor, certainty, perspective},
  lexicon: {signature_phrases, avoided_words, jargon_density, favored_verbs},
  structure: {opening_patterns, closing_patterns, paragraph_shape, transitions},
  rhetoric: {devices, argumentation, storytelling},
  idiolect: {discourse_markers, punctuation_quirks, unusual_constructions},
  do_rules: [...],
  dont_rules: [...],
  summary: "..."
}
```

The cached `system_prompt` is built from these by `core/styles/injector.py`.
Few-shot exemplars (8–12 most distinctive passages) are appended.

---

## Humanizer Pipeline (advanced)

1. **Stats** of the input
2. **Fingerprint scrub** — deterministic phrase substitution (curated list in `core/humanize/fingerprints.json` — edit freely)
3. **Burstiness pass** — LLM rewrite forcing sentence-length variance σ≥8
4. **Perplexity injection** — LLM rewrite for unexpected word choices, idioms, contractions
5. **Detector loop** — if `ai_detection > 0.35`, retry passes 3+4 (1× for `standard`, 2× for `max`)
6. **Style transfer** — only if a voice clone is attached
7. **LinkedIn SEO pass** — only if `seo_target='linkedin'` (hook in first 210 chars, short paras, hashtags, soft CTA)
8. **Fact guard** — diffs numbers / proper nouns / quotes between input and output
9. **Style fidelity** — cosine similarity of output embedding vs. style centroid

The detector ensemble lazy-loads on first call:
- **Binoculars** — GPT-2 + GPT-2-medium perplexity ratio
- **GLTR** — top-K token rank histogram from GPT-2
- **Roberta** — `roberta-base-openai-detector` from HF

If `torch`/`transformers` aren't installed, the pipeline degrades gracefully to
the always-on lightweight stylometric detector — endpoints never break.

---

## Chat ↔ Studio integration (already wired)

`api/routes/chat.py` was patched with two integration points:

1. **Voice injection** — when a conversation is bound to a project with a
   `style_profile_id`, the cloned voice's `system_prompt` is appended to the
   chat system prompt. Frontend doesn't need to do anything.
2. **Artifact capture** — when any of these tools succeed in a Studio
   conversation, the resulting bytes are copied into the project dir and a
   `studio_artifacts` row is inserted:

   - `create_pptx_with_skill`
   - `create_word_document`
   - `generate_pptx`
   - `generate_pptx_freestyle`
   - `generate_pptx_template`
   - `revise_pptx`
   - `generate_docx`

   The hook fires from both the sequential and the YANG `parallel_tools`
   paths. Capture failures are logged as warnings — they never break chat.

---

## Frontend integration cheat-sheet

```ts
// 1. Create a project
const { project } = await api.post('/studio/projects', {
  kind: 'pptx',
  title: 'Q1 Outlook',
  style_profile_id: '...',          // optional
  humanize_settings: { enabled: false, intensity: 'standard' },
});

// 2. Stream chat into it (existing endpoint, just pass conversation_id)
const stream = await api.streamPost('/chat/agent', {
  content: 'Build a 12-slide Q1 outlook...',
  conversation_id: project.conversation_id,
});

// 3. After stream ends, refresh project — new artifacts appear
const { artifacts } = await api.get(`/studio/projects/${project.id}`);
const latest = artifacts[artifacts.length - 1];

// 4. Render slides
//    Frontend renders the .pptx itself. Either:
//    a) Download the bytes and parse client-side
const bytes = await fetch(`/studio/projects/${project.id}/artifacts/${latest.id}/download`);
//    b) Or use existing /preview endpoints if the frontend already has them.

// 5. Visual editor saves
const { artifact: v2 } = await api.post(
  `/studio/projects/${project.id}/artifacts/${latest.id}/edit`,
  { ops: [{ type: 'text_replace', find: 'Q1', replace: 'Q2', all: true }] },
);

// 6. Humanize a chunk
const { output, scores } = await api.post('/studio/humanize', {
  text: '…AI-generated paragraph…',
  intensity: 'max',
  seo_target: 'linkedin',
  style_profile_id: project.style_profile_id,
});
```

---

## Files added (for reference)

```
db/migrations/027_studio_projects.sql
db/migrations/028_studio_writing_styles.sql
db/migrations/029_studio_humanization_runs.sql

core/studio/__init__.py
core/studio/projects.py
core/studio/chat_hook.py
core/studio/edits.py

core/styles/__init__.py
core/styles/stats.py
core/styles/embeddings.py
core/styles/cloner.py
core/styles/injector.py

core/humanize/__init__.py
core/humanize/llm.py
core/humanize/fingerprints.json
core/humanize/passes.py
core/humanize/detectors.py
core/humanize/pipeline.py

api/routes/studio_projects.py
api/routes/studio_styles.py
api/routes/studio_humanize.py
```

Modified:
- `main.py` — registers 3 new routers
- `api/routes/chat.py` — voice injection + artifact capture hook (sequential + parallel paths)
- `core/tools.py` — adds `humanize_text` tool definition + dispatch
- `requirements.txt` — adds `torch` + `transformers` for the heavy detector ensemble
