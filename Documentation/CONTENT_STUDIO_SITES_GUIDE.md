# Content Studio — Sites (Lovable-style website builder)

A new **`site`** project kind alongside `pptx` / `docx` / `chat`. Users
describe a website in chat → the AI emits a multi-file HTML/CSS/JS bundle →
the bundle is captured as a versioned **site artifact** under the active
Studio project → the user previews it live in an iframe → publishes it to a
public subdomain (or `/s/{slug}/` path slug) anyone can visit.

---

## 1. Architecture (mental model)

```
chat ──▶ generate_site / revise_site (Claude tool)
            │
            ▼
   core.tools_v2.site_tools.handle_*       ──▶ zip bundle
            │
            ▼
   core.file_store.store_file              ──▶ /data/generated/<file_id>_site.zip
            │
            ▼
   chat_hook.materialize_tool_result       ──▶ studio_artifacts(kind='site')
            │
            ▼
   core.studio.sites.extract_site_bundle   ──▶ /data/projects/{pid}/v{n}_files/
                                                       │
                  ┌────────────────────────────────────┤
                  ▼                                    ▼
   AUTH preview iframe                       publish_site
   GET /studio/sites/{pid}/preview/{n}/...   POST /studio/sites/{pid}/publish
                                                       │
                                                       ▼
                                         published_sites table + alias
                                         /data/published/{subdomain}/
                                                       │
              ┌────────────────────────────────────────┤
              ▼                                        ▼
   PUBLIC path-based                       PUBLIC host-based
   GET /s/{subdomain}/...                  GET /  (Host: {sub}.sites.<DOMAIN>)
```

**Storage layout (Railway volume):**

```
$STORAGE_ROOT/projects/{project_id}/
    v1.zip                    ← raw bundle, stored as artifact
    v1_files/                 ← extracted on demand (preview / publish target)
        index.html
        styles/main.css
        scripts/app.js
$STORAGE_ROOT/published/
    {subdomain}/              ← copy of currently-published site_root
```

Bytes live on the volume; metadata lives in Supabase
(`studio_projects`, `studio_artifacts`, `published_sites`).

---

## 2. New pieces

### Database — `db/migrations/030_studio_sites.sql`
- Adds `'site'` to `studio_projects.kind` and `studio_artifacts.kind`
- New table `published_sites` (subdomain unique, RLS, CSP-friendly)
- Anon `SELECT` on `published_sites` so the public router can resolve
  subdomains without service_role

> **Run this migration in your Supabase SQL editor before deploying.**

### Backend modules
| File | Purpose |
|---|---|
| `core/studio/sites.py` | zip build/extract, validation, publish/unpublish, static-file serving with SPA fallback |
| `core/tools_v2/site_tools.py` | `handle_generate_site` + `handle_revise_site` |
| `core/tools.py` | tool definitions + dispatch entries |
| `core/studio/projects.py` | extended to support `kind='site'` (zip artifact + auto-extract) |
| `core/studio/chat_hook.py` | captures `generate_site` / `revise_site` outputs as artifact versions |
| `api/routes/studio_sites.py` | auth-gated preview, file map, publish/unpublish, availability check |
| `api/routes/public_sites.py` | anonymous `/s/{slug}/...` path serving + Host-header subdomain resolver |
| `main.py` | mounts both routers + Host-header middleware |

---

## 3. AI tools

### `generate_site`
```jsonc
{
  "title": "Linda's Photography Portfolio",
  "description": "Minimalist dark portfolio with a contact form",
  "files": {
    "index.html":      "<!doctype html>...",
    "styles/main.css": "body{background:#111;color:#fff;...}",
    "scripts/app.js":  "console.log('hi');"
  }
}
```
- Must include `index.html`
- Static-only (`.py`, `.php`, `.rb`, `.sh`, `.exe`, etc. are stripped)
- ≤ 50 MB / 200 files / 10 MB per file

### `revise_site`
```jsonc
{
  "summary": "Switch to a light theme",
  "ops": [
    { "op": "write",  "path": "styles/main.css", "content": "body{background:#fff;color:#111}" },
    { "op": "delete", "path": "deprecated.html" },
    { "op": "rename", "from": "old.css", "to": "new.css" }
  ]
}
```
If `artifact_id` is omitted, the latest site artifact in the active
conversation's project is used.

---

## 4. API surface

### Auth-gated (Bearer token)
| Method | Path | Purpose |
|---|---|---|
| GET  | `/studio/projects?kind=site` | list site projects |
| POST | `/studio/projects` `{kind:"site"}` | create site project |
| GET  | `/studio/projects/{id}/artifacts` | list versions |
| GET  | `/studio/sites/{pid}/preview/{version}/{path:path}` | live preview iframe target (SPA fallback included) |
| GET  | `/studio/sites/{pid}/files/{artifact_id}` | `{path: content}` map for in-app code editor |
| GET  | `/studio/sites/check/{subdomain}` | format + availability check |
| POST | `/studio/sites/{pid}/publish` `{artifact_id, subdomain}` | publish (or re-point) a subdomain |
| POST | `/studio/sites/{pid}/unpublish` `{publication_id}` | deactivate |
| GET  | `/studio/sites/{pid}/publications` | list publications for project |
| GET  | `/studio/sites/publications` | list ALL of user's publications |

### Public (anonymous)
| Method | Path | Purpose |
|---|---|---|
| GET | `/s/{subdomain}/` | serves `index.html` of the published bundle |
| GET | `/s/{subdomain}/{path:path}` | serves any file (SPA fallback to index.html) |
| GET | `/...` with `Host: {sub}.<base>` | wildcard subdomain hosting (see §6) |

---

## 5. Frontend integration sketch

```ts
// 1. Create a site project
await api.post('/studio/projects', { kind: 'site', title: 'My Portfolio' })

// 2. User chats with the bound conversation_id — the AI calls generate_site
//    automatically. New site artifacts show up in /studio/projects/{id}/artifacts.

// 3. Preview the latest version in an iframe
<iframe
  src={`${API}/studio/sites/${projectId}/preview/${version}/`}
  sandbox="allow-scripts allow-same-origin allow-forms"
/>

// 4. Publish
await api.post(`/studio/sites/${projectId}/publish`, {
  artifact_id, subdomain: 'lindas-portfolio'
})
// → returns { urls: { path_url, subdomain_url } }

// 5. Open the public URL in a new tab.
```

---

## 6. Public hosting modes

**Mode A — Path-based (works today, zero DNS work)**
Publish goes live at:
```
https://<your-railway-host>/s/lindas-portfolio/
```

**Mode B — True wildcard subdomains**
1. In your DNS provider, add a wildcard CNAME:
   `*.sites.<yourdomain>` → your Railway custom domain
2. In Railway, add a wildcard custom domain (paid plan) for
   `*.sites.<yourdomain>`
3. Set the env var:
   ```
   PUBLIC_SITES_BASE_DOMAINS=sites.yourdomain.com
   ```
4. Restart. The Host-header middleware in `main.py` will route
   `Host: lindas-portfolio.sites.yourdomain.com` straight to the
   published bundle.

Multiple base domains supported (comma-separated). Code paths are
identical — only routing changes.

---

## 7. Security

- **Subdomain regex**: `^[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])?$`
- **Reserved subdomains**: 50+ (api, www, admin, studio, app, …) — see
  `RESERVED_SUBDOMAINS` in `core/studio/sites.py`
- **Server-side script blocklist** (extension-based) on extract: `.py`,
  `.php`, `.rb`, `.sh`, `.exe`, `.dll`, `.bat`, `.ps1`, `.jar`, `.war`,
  `.class`
- **Path traversal**: all zip member paths and request paths run through
  `_safe_relpath` + `realpath` containment check
- **CSP** on every public response — disables third-party iframes from
  embedding sites and locks down origins:
  ```
  default-src 'self' data: blob: https:;
  script-src  'self' 'unsafe-inline' 'unsafe-eval' https:;
  frame-ancestors 'self';
  ```
- **Bundle limits**: 50 MB total, 10 MB/file, 200 files
- **RLS**: only the owner (or service role) can mutate `published_sites`;
  anon role has SELECT on active rows only

---

## 8. Phased rollout (already wired)

1. ✅ Generation + private preview (`/studio/sites/{pid}/preview/...`)
2. ✅ Path-based publishing (`/s/{slug}/...`)
3. ⏳ Wildcard subdomains — flip on once DNS + Railway domain are configured
4. 🔜 Custom domains per published site (CNAME verification flow)
5. 🔜 Visual edit mode (click-to-edit text in iframe → emits `revise_site` ops)

---

## 9. Operational knobs (env vars)

| Var | Purpose | Default |
|---|---|---|
| `STORAGE_ROOT` | Railway volume root | `/data` |
| `PUBLIC_SITES_BASE_DOMAINS` | Comma-list of base domains for wildcard subdomain serving | _(unset → path-only)_ |

---

## 10. To deploy

1. Run `db/migrations/030_studio_sites.sql` in your Supabase SQL editor.
2. Deploy the backend (Railway picks up the new files automatically).
3. (Optional) Set `PUBLIC_SITES_BASE_DOMAINS` and configure wildcard DNS.
4. Test: in chat (project bound to a `kind='site'` project), say
   *"Build a one-page landing site for my coffee shop."*
   → Expect a new site artifact, an iframe preview, and a working
   `/s/<chosen-slug>/` URL after publish.
