# Full-Stack Next.js / React Apps in Content Studio — Architecture Plan

> **Status**: Planning — no code committed yet. Pick an option below and
> toggle to Act mode to implement.

---

## Current State (what works today)

Content Studio Sites can generate and host **static** websites:
- **Plain HTML/CSS/JS** — served directly from the Railway volume
- **React/JSX** — auto-wrapped through the Babel + ESM importmap sandbox
  (same engine as `execute_react`). Runs 100% in the browser. Supports
  useState, useEffect, Tailwind, lucide-react, recharts, framer-motion,
  react-router-dom, and 30+ CDN packages.

This is equivalent to what **Lovable** and **v0** do. It covers ~80% of
website use cases (landing pages, portfolios, dashboards, marketing sites).

What it **cannot** do:
- Server-side rendering (SSR / RSC)
- API routes (`/api/*`)
- Database access (Prisma, Drizzle)
- Server actions
- Middleware
- Dynamic `getServerSideProps`
- `npm install` of arbitrary packages not in the ESM importmap
- File-system routing (Next.js `app/` or `pages/` directory convention)

---

## Why Full-Stack Next.js?

Users want to say:
> "Build me a SaaS dashboard with auth, a Postgres-backed API, and
> server-side data fetching."

This requires a Node.js runtime, a build step, and persistent server
processes — not just browser-side React.

---

## Three Architecture Options

### Option B1: WebContainers (Browser-Side Node.js)

**How it works**: [WebContainers](https://webcontainers.io/) by StackBlitz
run a full Node.js runtime inside the browser using WASM + Service Workers.
The user's browser boots a virtual filesystem, runs `npm install`, starts
`next dev`, and serves the app from an iframe — all without touching the
server.

**This is exactly how Bolt.new and StackBlitz work.**

```
User prompt → AI writes files → frontend sends files to WebContainer
  → npm install (in browser, ~5s) → next dev (in browser)
  → iframe shows http://localhost:3000 from the Service Worker
```

| Pros | Cons |
|---|---|
| Zero server infra | Requires StackBlitz WebContainer API (free tier available) |
| Instant boot (~3s) | Only works in Chromium browsers (no Safari/Firefox yet) |
| Full Node.js + npm | Browser RAM limits (~512MB per container) |
| SSR, API routes, middleware all work | Large `node_modules` = slow first boot |
| No cost per site | Published sites still need a server (see Hybrid) |

**Frontend changes**:
- Add `@webcontainer/api` package
- Boot a WebContainer on project open
- Write AI-generated files into the virtual FS
- Run `npm install && npm run dev` inside the container
- Point iframe at the Service Worker URL
- On revision: write changed files → HMR picks them up instantly

**Backend changes**: Minimal. The AI's `generate_site` tool writes Next.js
files (pages, components, API routes, `package.json`, `next.config.js`).
The backend stores them as a zip artifact (same as today). The WebContainer
is purely a frontend concern.

**Publish path**: Export static via `next export` in the WebContainer →
upload the `out/` directory to the existing publish pipeline. OR deploy to
Vercel/Railway via API (see B2).

---

### Option B2: Docker-per-Site on Railway

**How it works**: Each published site gets its own Railway service created
via the [Railway API](https://docs.railway.app/reference/public-api). The
backend generates a `Dockerfile` + `package.json` + Next.js config, pushes
to a git repo (or uses Railway's direct deploy), and the site runs as an
independent container.

```
User prompt → AI writes files → backend builds zip → on Publish:
  → Create Railway service via API
  → Push files as a deployment
  → Railway builds + runs the container
  → Public URL: https://{subdomain}.up.railway.app
```

| Pros | Cons |
|---|---|
| True production SSR | $5-10/month per active site |
| Real database connections | 30-90s build time per version |
| Full Next.js feature set | Requires Railway Teams ($20/mo base) |
| Custom domains built-in | Cold starts if containers sleep |
| Works in all browsers | Complex teardown (orphaned containers) |

**Backend changes**:
- New module: `core/studio/site_deploy.py`
  - `create_railway_service(project_id, subdomain)` → Railway API
  - `deploy_to_railway(service_id, files_zip)` → trigger build
  - `teardown_railway_service(service_id)` → on unpublish
- Env vars: `RAILWAY_API_TOKEN`, `RAILWAY_PROJECT_ID`
- New DB column: `published_sites.railway_service_id`

**Frontend changes**: Publish modal shows a progress bar during build
(30-90s). Status polling via `GET /studio/sites/{pid}/deploy-status`.

---

### Option B3: Hybrid (Recommended)

**Preview** via WebContainers (instant, browser-side) +
**Publish** via Railway containers or Vercel deploy (production-grade).

```
┌─ Preview (in-browser) ──────────────────────────────┐
│                                                      │
│  WebContainer boots Next.js dev server               │
│  Full SSR, API routes, HMR                           │
│  Zero server cost, instant iteration                 │
│                                                      │
├─ Publish (server-side) ─────────────────────────────┤
│                                                      │
│  Option A: `next export` → static bundle             │
│    → existing /s/{subdomain}/ pipeline (free)        │
│                                                      │
│  Option B: Deploy to Railway container               │
│    → full SSR, API routes, DB ($5-10/mo)             │
│                                                      │
│  Option C: Deploy to Vercel via API                  │
│    → best Next.js hosting, free tier available       │
│                                                      │
└──────────────────────────────────────────────────────┘
```

| Pros | Cons |
|---|---|
| Best UX (instant preview, real builds for publish) | Two codepaths to maintain |
| Users only pay for published sites | WebContainer browser limits |
| Full Next.js during development | Publish adds 30-90s build step |
| Existing static pipeline works for simple sites | |

---

## What the AI Tool Needs to Change

### `generate_site` tool — add Next.js mode

The tool description already supports two modes (plain HTML, React). Add a
third:

```
MODE 3 — Next.js (full-stack):
  Write files following the Next.js App Router convention:
    app/layout.tsx       — root layout
    app/page.tsx         — home page
    app/api/hello/route.ts — API route
    components/*.tsx     — shared components
    package.json         — with next, react, react-dom deps
    next.config.js       — minimal config
    tailwind.config.js   — if using Tailwind
    .env.local           — environment variables (optional)

  The backend detects Next.js by the presence of `next.config.js` or
  `package.json` containing `"next"` in dependencies.
```

### Detection heuristic

```python
def is_nextjs_site(files: dict) -> bool:
    # Check for next.config.js/mjs/ts
    if any(f.startswith("next.config") for f in files):
        return True
    # Check package.json for next dependency
    pkg = files.get("package.json", "")
    if '"next"' in pkg:
        return True
    # Check for app/ or pages/ directory convention
    if any(f.startswith("app/") or f.startswith("pages/") for f in files):
        return True
    return False
```

### Storage

Same zip-based artifact system. Next.js files are just more files in the
bundle. The `_src/` preservation mechanism already handles this.

---

## Implementation Phases

### Phase 1: Enhanced React (no infra change) ✅ DONE
- React/JSX sandbox with Babel + ESM importmap
- Multi-file components, Tailwind, 30+ CDN packages
- Incremental editing via `revise_site`

### Phase 2: WebContainer Preview (frontend only)
1. Add `@webcontainer/api` to the frontend
2. When `kind === 'site'` and files contain `package.json`:
   - Boot WebContainer instead of using the static iframe
   - Write files into the virtual FS
   - Run `npm install && npm run dev`
   - Point iframe at the WebContainer URL
3. On `revise_site`: write only changed files → HMR
4. Fallback: if WebContainer unsupported (Safari), use static preview

### Phase 3: Publish Pipeline
- Static sites: existing `/s/{subdomain}/` (free, instant)
- Next.js sites with `next export`: build in WebContainer → upload static
- Next.js sites with SSR: deploy to Railway or Vercel via API

### Phase 4: Database Integration
- Provision a Supabase/Neon database per project
- Inject connection string as env var in the WebContainer
- Prisma/Drizzle schema generation via AI

---

## Cost Estimate

| Component | Cost |
|---|---|
| WebContainer preview | $0 (runs in browser) |
| Static site publish | $0 (served from Railway volume) |
| Next.js SSR container (Railway) | $5-10/site/month |
| Vercel deploy (free tier) | $0 for first 3, then $20/mo |
| Neon/Supabase database | $0 free tier, $25/mo for Pro |

---

## Decision Needed

Pick one and I'll build it:

- **B1**: WebContainers only (all browser-side, simplest, instant)
- **B2**: Railway containers only (server-side, production-grade, costs $)
- **B3**: Hybrid — WebContainers for preview + Railway/Vercel for publish

For B1 and B3, the backend changes are minimal — it's primarily a frontend
project. For B2, significant backend work (Railway API integration, build
pipeline, container lifecycle management).
