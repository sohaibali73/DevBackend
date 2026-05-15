# YANG Autopilot — Artifacts, UI Contract, and Outlook (Backend Changes)

This document describes the backend changes implemented against the
frontend's spec. Everything is **additive** — old clients keep working.

---

## 1. Run the SQL migration

Open the Supabase SQL Editor and paste the contents of:

```
db/migrations/033_yang_artifacts.sql
```

It creates the `goal_artifacts` table (per-user RLS, dedupe-by-sha256 per
goal, `deleted_at` flag for 410-Gone after GC). No code change is needed
beyond what's already shipped.

---

## 2. Server-generated files → local workspace

### 2.1 New SSE event: `step.kind == "artifact"`

Emitted automatically after every server-side tool result whose payload
contains any of `{ path, file_id, charts[], artifacts[], workspace_files[] }`.
The step content is exactly the dict the spec asked for:

```json
{
  "name":       "Q4_Report.docx",
  "mime":       "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "bytes":      48213,
  "sha256":     "ab12…",
  "url":        "/goals/{goalId}/artifacts/{artifactId}",
  "producedBy": "generate_docx",
  "createdAt":  1736544000000,
  "id":         "<uuid>"
}
```

Because the step is persisted via `_save_step`, a late `GET /goals/{id}` will
return the artifact in `steps[]` too — no special replay code needed.

### 2.2 Endpoints

| Method      | Path                                            | Notes |
|-------------|-------------------------------------------------|-------|
| `GET`       | `/goals/{goalId}/artifacts`                      | List all (frontend "Files" tab). |
| `GET, HEAD` | `/goals/{goalId}/artifacts/{artifactId}`         | Download binary; HEAD short-circuits before streaming. |
| `POST`      | `/goals/{goalId}/_debug/emit_fake_artifact`      | Test fixture — register a 50-byte txt and emit the SSE step. Disabled by `YANG_DEBUG_FIXTURES=0`. |

Headers on download:

```
Content-Type:        <mime>
Content-Length:      <bytes>
Content-Disposition: attachment; filename="<name>"
ETag:                "sha256:<hex>"
Cache-Control:       private, max-age=3600
```

Error semantics:
* `401` — implicit via Bearer auth.
* `404` — goal/artifact not owned or doesn't exist.
* `410 Gone` — bytes were GC'd from disk (metadata row still present).

### 2.3 Retention

Bytes are kept on the Railway volume **24 hours after the goal reaches a
terminal status** (`done`, `failed`, `cancelled`). The GC loop runs hourly
(env: `YANG_ARTIFACT_RETENTION_HOURS`, `YANG_ARTIFACT_GC_INTERVAL_S`). After
GC, the row stays so the SSE step's `url` returns 410 (not 404), and the UI
can render "expired" copy.

### 2.4 Auto-wrap for existing tools

The agent loop now inspects every server-side tool result and routes
common shapes through `core.artifacts.register_from_candidates`:

* `{ "path": "...", "name"?: "..." }`
* `{ "file_id": "...", "filename"?: "..." }` (core.file_store)
* `{ "charts": [{ file_id, filename, type }] }` (execute_python)
* `{ "artifacts": [{ data: "/files/.../download", metadata }] }` (execute_python)
* `{ "workspace_files": [{ path }] }`

No per-tool change required.

---

## 3. UI contract additions

### 3.1 Plan event — `totalSteps`

The first `plan` step now persists structured content:

```json
{
  "plan":       "<full text>",        // back-compat
  "summary":    "<first bullet>",
  "steps":      ["bullet 1", "bullet 2", ...],
  "totalSteps": 6
}
```

### 3.2 `status` event — activity label

Before every tool execution the runner emits a status event:

```json
{
  "type":           "status",
  "status":         "running",
  "activity":       "Drafting Q4 report",
  "currentStepIdx": 3,
  "totalSteps":     6
}
```

`activity` is derived from `_humanize_activity(name, args)`. Falls back to a
capitalised version of the tool name. Frontend may treat `activity` as
optional (old web client without the runner update will simply not see this
field).

### 3.3 `GET /goals` items

Each item now includes:

* `updatedAt` (ms epoch) — derived from `updated_at`; sorted by it.
* `createdAt` (ms epoch) — derived from `created_at`.

The original ISO strings (`updated_at`, `created_at`) are preserved.

### 3.4 `POST /goals` body

The request body accepts an additional `options` object:

```json
{
  "title": "...",
  "description": "...",
  "prompt": "...",
  "capabilities": ["fs","shell","outlook"],
  "options": {
    "emailOnComplete":  { "enabled": true, "to": "user@example.com" },
    "saveArtifactsTo":  "default",
    "notify":           true
  }
}
```

`options` is persisted under `goals.metadata.options` and consulted by the
runner. When `emailOnComplete.enabled === true`, the system prompt is
augmented with a hard directive to call `outlook_send_email` at the end of
the goal.

### 3.5 SSE keepalive

`goal_stream()` emits a `: keepalive\n\n` SSE comment every 15s during idle
periods so edge proxies don't close long-running streams.

---

## 4. Outlook tools

Five tools are registered under the `outlook` capability — only advertised
to the model when the desktop client adds `"outlook"` to its capabilities
list. All five route via `core.desktop_pending` (same path as `fs_*` /
`computer_*`), so **the backend never sees Microsoft Graph tokens**:

* `outlook_status`        — `{ connected, email?, scopes? }`
* `outlook_send_email`    — exact schema per spec
* `outlook_create_draft`  — same shape as send
* `outlook_list_inbox`    — `{ folder?, top?, query? }`
* `outlook_reply`         — `{ messageId, body, isHtml? }`

When the goal advertises `outlook` OR `options.emailOnComplete.enabled` is
true, the system prompt receives an Outlook-specific block instructing the
agent to:

1. Call `outlook_status` first.
2. Compose a clean subject + plain-text body unless HTML is explicitly
   requested.
3. Attach generated artifacts by **workspace path**, never base64.
4. Confirm the email send + recipients in the final `done` step.
5. Never include secrets in the body.

---

## 5. FE pre-work answers

| Question | Answer |
|---|---|
| ✅/❌ on each item | ✅ all items, additive. |
| Final URL pattern for download | `GET\|HEAD /goals/{goalId}/artifacts/{artifactId}` (path params). List: `GET /goals/{goalId}/artifacts`. |
| Retention window | **24 h after terminal status**; afterwards `410 Gone`. |
| Test fixture | `POST /goals/{id}/_debug/emit_fake_artifact` (env-gated). |

---

## 6. Touch list

* `db/migrations/033_yang_artifacts.sql` — **paste into Supabase SQL editor**.
* `core/artifacts.py` — storage helpers + GC loop + auto-wrap.
* `core/yang_autopilot.py` — plan parsing, activity status, artifact extraction, system-prompt nudges, options handling, `updatedAt`.
* `core/desktop_tools.py` — outlook tool definitions.
* `api/routes/yang_autopilot.py` — list / download / HEAD / debug fixture, `GoalCreateRequest.options`.
* `main.py` — lifespan starts/stops the artifact GC loop.

---

## 7. Operational env vars

* `STORAGE_ROOT` — Railway volume root (defaults to `/data`). Artifacts live at `$STORAGE_ROOT/yang_artifacts/{goal_id}/...`.
* `YANG_ARTIFACT_RETENTION_HOURS` — default `24`.
* `YANG_ARTIFACT_GC_INTERVAL_S` — default `3600`.
* `YANG_DEBUG_FIXTURES` — set to `0`/`false`/`no` to disable the debug endpoint in production.
