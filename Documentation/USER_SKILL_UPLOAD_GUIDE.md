# User-Uploaded Skills — Frontend Integration Guide

This document is the contract between the backend (this repo) and the
Next.js frontend for letting authenticated users upload, manage, and use
their own skills inside chats.

---

## TL;DR

- One new endpoint family: **`/skills/upload`**, **`PATCH /skills/{slug}`**, **`DELETE /skills/{slug}`**, **`GET /skills/{slug}/download`**, **`POST /skills/{slug}/duplicate`**.
- The existing **`GET /skills`**, **`GET /skills/{slug}`**, and **`POST /skills/{slug}/execute`** endpoints already work for uploaded skills — no chat changes required.
- **Org-wide visibility**: every uploaded skill is visible to every authenticated user. Only the uploader (or an admin) can edit or delete.
- **Two on-disk formats are auto-detected** by the backend; the frontend never has to choose. The user just uploads a `.zip` (or fills the inline form, which the frontend turns into a 1-file zip).

---

## 1. Skill bundle format

A bundle is a `.zip` archive following one of two layouts. The backend auto-routes:

### Format A — Anthropic SKILL.md bundle (recommended)

```
my-skill.zip
├── SKILL.md            ← required, with YAML frontmatter
├── references/         ← optional reference docs
├── scripts/            ← optional .py / .js helpers
├── assets/             ← optional images, templates, etc.
└── examples/           ← optional sample inputs/outputs
```

`SKILL.md` frontmatter must include at minimum `name` and `description`:

```markdown
---
name: my-skill
description: >
  One-paragraph description that doubles as the trigger hint for the agent.
category: research
tags: [research, valuation]
---

# My Skill

Body of the system prompt goes here. Bundles with `scripts/` or `assets/`
are auto-routed to `ClaudeSkills/<slug>/` (sandbox-mounted).
```

### Format B — Lightweight skill (for simple system-prompt-only skills)

```
my-skill.zip
├── skill.json
└── prompt.md
```

`skill.json`:

```json
{
  "slug": "my-skill",
  "name": "My Skill",
  "description": "What this skill does and when to trigger it.",
  "category": "research",
  "tags": ["research"],
  "tools": [],
  "max_tokens": 8192,
  "timeout": 120,
  "enabled": true,
  "aliases": []
}
```

`prompt.md` is the system prompt body. Lightweight bundles are stored in
`core/skills/<slug>/`.

### Format C — Inline mode (no zip — frontend synthesizes one)

If the user fills a form (name + description + system prompt) instead of
uploading, the frontend has two options:

1. **Build a 1-file zip** containing only `SKILL.md` (synthesized) and POST it
   normally. Simplest and works without server changes.
2. **POST with `metadata.mode="inline"`** and put `name`, `description`,
   `system_prompt`, etc. in the metadata JSON. The backend will synthesize
   the `SKILL.md` server-side. The `file` field still has to exist (any
   tiny placeholder zip is fine; backend ignores it for inline mode).

Either is fine. Option 1 keeps client and server symmetric; option 2 saves
one round of zip-construction logic.

---

## 2. Endpoints

All endpoints require a Supabase JWT in `Authorization: Bearer <token>`.

### 2.1 List skills

```
GET /skills?category=&include_builtins=true&owned=me
```

- `?owned=me` returns only the current user's uploaded skills.
- Response merges hardcoded portal skills + filesystem-discovered skills:

```json
{
  "skills": [
    {
      "slug": "my-skill",
      "name": "My Skill",
      "description": "...",
      "category": "research",
      "tags": ["research"],
      "max_tokens": 8192,
      "enabled": true,
      "supports_streaming": true,
      "is_builtin": false,
      "source": "upload",          // 'system' | 'upload' | 'inline' | (legacy 'portal')
      "storage_kind": "lightweight", // 'portal' | 'lightweight' | 'bundle'
      "created_by": "<uuid>",      // null for system / portal skills
      "created_at": "2026-05-07T18:00:00Z"
    }
  ],
  "count": 1
}
```

### 2.2 Get one skill

```
GET /skills/{slug}
```

Returns the same shape as a list item (with `system_prompt` and `tools`
populated for non-portal skills).

### 2.3 Upload a new skill

```
POST /skills/upload
Content-Type: multipart/form-data

file:      <bundle.zip>            (≤ 25 MB)
metadata:  '{"slug":"my-skill",    (optional JSON string; overrides bundle)
             "name":"...",
             "description":"...",
             "category":"research",
             "tags":["research"],
             "system_prompt":"...",
             "mode":"upload"}'      // 'upload' | 'inline'
```

Success → `200`:

```json
{
  "skill": { /* full skill dict — same shape as GET /skills */ },
  "warnings": ["Skipped disallowed file: foo.exe"],
  "archived": true,
  "storage_kind": "bundle",
  "storage_path": "ClaudeSkills/my-skill"
}
```

Error → `400` / `403` / `500` with:

```json
{ "detail": { "code": "SLUG_TAKEN", "error": "Skill slug 'my-skill' is already in use (fs)." } }
```

### Error codes (for friendly UI mapping)

| Code | Meaning |
|---|---|
| `INVALID_METADATA` | `metadata` field was not valid JSON |
| `INVALID_ZIP` | The uploaded file isn't a valid zip |
| `EMPTY_UPLOAD` | Empty file or empty zip |
| `BUNDLE_TOO_LARGE` | > 25 MB compressed or > 50 MB extracted |
| `TOO_MANY_FILES` | > 500 entries |
| `UNSAFE_PATH` | Path traversal / absolute path / symlink in zip |
| `MISSING_SKILL_MD` | Neither `SKILL.md` nor `skill.json` at root |
| `MISSING_NAME` | Name is required |
| `MISSING_DESCRIPTION` | Description is required |
| `MISSING_PROMPT` | (inline mode) System prompt is required |
| `BAD_SLUG` | Slug fails `^[a-z][a-z0-9-]{2,63}$` |
| `SLUG_TAKEN` | Slug already exists (portal / fs / db). Tell the user to pick another. |
| `INVALID_SKILL_JSON` | `skill.json` was not valid JSON |
| `MATERIALIZE_FAILED` | Disk write failed (5xx) |
| `DB_INSERT_FAILED` | Postgres insert failed (5xx) |
| `FORBIDDEN` | Not the owner / not admin |
| `NOT_FOUND` | Slug not registered |

### 2.4 Edit metadata / system prompt

```
PATCH /skills/{slug}
Content-Type: application/json

{
  "name": "New name",
  "description": "...",
  "category": "research",
  "tags": ["research"],
  "enabled": false,
  "system_prompt": "..."   // applies to lightweight skills only
}
```

All fields optional — send only what changed. Returns `{ "skill": {...} }`.

### 2.5 Delete

```
DELETE /skills/{slug}
```

Returns `204` on success. Forbidden for `source='system'` unless the
caller is admin.

### 2.6 Download bundle

```
GET /skills/{slug}/download
```

Returns the skill folder repacked as a `.zip` (`Content-Disposition: attachment`).
Useful for "Fork to local", "Inspect", or "Re-upload elsewhere".

### 2.7 Duplicate (fork)

```
POST /skills/{slug}/duplicate
Content-Type: application/json

{ "new_slug": "my-skill-v2", "new_name": "My Skill v2" }
```

`new_slug` defaults to `<slug>-copy`. The duplicate is owned by the
current user (so they can edit it freely without admin perms).

### 2.8 Use it in chats — already works

The chat input already sends `skill_slug` in the request body, which
flows into `/chat/agent`. The moment a skill is registered (which happens
synchronously inside `POST /skills/upload`), it is selectable in the
skill picker and executable in chats. **No chat-side code changes needed.**

> **Frontend caveat:** the existing `ChatSkillSelector.tsx` caches the
> skill list once per component lifetime (`fetched=true`). After a
> successful upload/delete, bump a version counter / invalidate the
> cache so the new skill appears without a full page reload.

---

## 3. Recommended frontend implementation

### Next.js proxy routes

Mirror the existing `app/api/skills/...` proxy pattern:

```
app/api/skills/upload/route.ts        → forwards multipart to BACKEND/skills/upload
app/api/skills/[slug]/route.ts        → adds DELETE + PATCH (keep GET)
app/api/skills/[slug]/download/route.ts → streams zip
app/api/skills/[slug]/duplicate/route.ts → POST passthrough
```

All proxies should forward the `Authorization: Bearer <token>` header and
pass `multipart/form-data` through unchanged.

### Component sketch

`CreateSkillModal.tsx` with two tabs:

1. **Upload bundle** — drag-drop `.zip`. Use `jszip` + `js-yaml`
   client-side to parse `SKILL.md` and show:
   - Detected `name` / `description` / `category` / `tags`
   - File tree
   - "This will be installed as `bundle` because it contains `scripts/`."
   - Editable overrides (slug, category, tags) before submit.

2. **Author inline** — form fields:
   - Name (auto-derives slug, slug is editable)
   - Description (long text)
   - Category (dropdown)
   - Tags (chip input)
   - System prompt (large textarea / monaco)
   - On submit, build a synthesized SKILL.md zip OR pass `mode:'inline'` JSON.

### Refresh & wiring

After a successful upload/delete, do:

```ts
// 1. Invalidate any cached skill lists
queryClient.invalidateQueries({ queryKey: ["skills"] });

// 2. Bump a global "skillsVersion" so ChatSkillSelector re-fetches
useSkillStore.getState().bumpVersion();
```

### Permissions UI

For each skill card:

```ts
const canModify =
  skill.source !== "system" &&
  skill.source !== "portal" &&
  (skill.created_by === currentUserId || currentUserIsAdmin);
```

Show an overflow menu with **Edit / Duplicate / Download / Delete** only
when `canModify` is true. Always show **Download** and **Duplicate** for
any skill (they're both safe).

### Badges

```
source = 'system'   → "Built-in"   (gray)
source = 'portal'   → "Anthropic"  (blue)   // hardcoded SKILL_REGISTRY entries
source = 'upload'   → "Custom"     (green)
source = 'inline'   → "Inline"     (green, lighter)
```

---

## 4. Validation rules (enforced server-side)

| Rule | Limit |
|---|---|
| Compressed size | ≤ 25 MB |
| Total uncompressed | ≤ 50 MB |
| Files per zip | ≤ 500 |
| Allowed extensions | `.md .txt .json .yaml .yml .py .js .ts .tsx .jsx .mjs .csv .tsv .png .jpg .jpeg .gif .svg .webp .ico .pdf .html .htm .css .xml` |
| Slug | `^[a-z][a-z0-9-]{2,63}$` |
| Path safety | No `..`, no absolute paths, no symlinks |

Disallowed files are skipped silently and surfaced via `warnings[]` in
the upload response.

---

## 5. Persistence

- **On disk** (source of truth): `core/skills/<slug>/` (lightweight) or `ClaudeSkills/<slug>/` (bundle).
- **Database** (`user_skills` table): mirror with `source`, `created_by`, `enabled`, etc. — drives UI metadata.
- **Supabase Storage** (`skills-bundles` bucket): raw zip archived under `<slug>.zip`. On boot, the backend re-extracts any DB row whose folder is missing (rehydration after Railway redeploys).

The frontend doesn't touch Storage directly — backend handles it.

---

## 6. Smoke test (curl)

```bash
# Build a bundle
mkdir -p hello-skill && cd hello-skill
cat > SKILL.md <<'EOF'
---
name: hello-skill
description: Demo skill that says hello.
category: general
tags: [demo]
---
You are a friendly greeter. Always start replies with "Hello!".
EOF
zip -r ../hello-skill.zip .
cd ..

# Upload
curl -X POST https://developer-potomaac.up.railway.app/skills/upload \
  -H "Authorization: Bearer $JWT" \
  -F "file=@hello-skill.zip" \
  -F 'metadata={"category":"general","tags":["demo"]}'

# List (should include hello-skill)
curl -H "Authorization: Bearer $JWT" \
  https://developer-potomaac.up.railway.app/skills?owned=me

# Use in a chat
curl -X POST https://developer-potomaac.up.railway.app/skills/hello-skill/execute \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"message":"who are you?"}'

# Delete
curl -X DELETE https://developer-potomaac.up.railway.app/skills/hello-skill \
  -H "Authorization: Bearer $JWT"
```
