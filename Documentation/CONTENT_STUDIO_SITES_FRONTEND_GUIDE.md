# Content Studio — Sites (Website Builder) — Frontend Guide

This is the complete frontend spec for the new **Sites** feature inside
Content Studio — a Lovable-style "describe a website in chat → see it live
→ publish to a public URL" experience. The backend is live and committed
(see `CONTENT_STUDIO_SITES_GUIDE.md` for the architecture). This document
is what to build on top of those endpoints.

USE THE SAME THEME AS THE REST OF THE APP. RE-USE THE EXISTING
`/studio` SHELL, CHAT COMPONENTS, AND PROJECT LIST PATTERNS — Sites is
the third project kind alongside PPTX and DOCX, not a new app.

---

## Table of Contents

1. [Mental Model](#1-mental-model)
2. [Information Architecture](#2-information-architecture)
3. [Pages & Routes](#3-pages--routes)
4. [State Management](#4-state-management)
5. [API Client (TypeScript)](#5-api-client-typescript)
6. [Page-by-Page Component Spec](#6-page-by-page-component-spec)
7. [The Live Preview Iframe](#7-the-live-preview-iframe)
8. [Publish Flow](#8-publish-flow)
9. [Code Editor (Optional Power-User View)](#9-code-editor-optional-power-user-view)
10. [Streaming + Real-Time Patterns](#10-streaming--real-time-patterns)
11. [Empty / Loading / Error States](#11-empty--loading--error-states)
12. [Accessibility & Keyboard Shortcuts](#12-accessibility--keyboard-shortcuts)
13. [Security Notes](#13-security-notes)
14. [QA Checklist](#14-qa-checklist)

---

## 1. Mental Model

```
SiteProject = Conversation + kind:'site' + Versioned Site Artifacts
   │
   ├─ kind = 'site'                     ← new value alongside 'pptx' / 'docx' / 'chat'
   ├─ conversation_id  ───────► everything goes through POST /chat/agent
   └─ artifacts[]      ───────► v1, v2, v3, ... each is a static-site bundle (zip)
                                  │
                                  └─ extracted on demand to v{n}_files/index.html
                                       └─ that's what the iframe loads
```

Same iron-rule as the rest of Content Studio: **all generation goes
through `/chat/agent`.** The user is in a Sites project → they chat → the
AI calls the new `generate_site` (or `revise_site`) tool → the chat hook
auto-captures the output as `studio_artifacts(kind='site')` v(n+1) → the
right pane re-renders the iframe pointing at the new version.

You do NOT call `generate_site` or `revise_site` directly. They are
Claude tools, not REST endpoints.

Lifecycle a user sees:

```
  Type: "Build me a portfolio site for my photography"
            │
            ▼
  Chat shows tool_use: generate_site
            │
            ▼
  Right pane swaps to live iframe of v1 (<2s)
            │
            ▼
  Type: "Make the hero text bigger and switch to dark mode"
            │
            ▼
  Tool: revise_site → v2 → iframe reloads
            │
            ▼
  Click "Publish" → pick subdomain → live at /s/<subdomain>/
```

---

## 2. Information Architecture

The existing Content Studio sidebar gets a third kind in the project list
— **Sites** — and a third filter chip on the Projects tab:

```
[ Sidebar ]
└─ Content Studio
    ├─ Projects (default tab)
    │   └─ filter chips:  All  |  PPTX  |  DOCX  |  Sites   ← NEW chip
    ├─ Styles
    └─ Humanize
```

Inside a single Site project the existing two-pane shell is reused, but
with a different right-pane:

```
┌─────────────────────────────────────────────────────────────────────┐
│  ProjectHeader: title · "Site" pill · publish chip · actions       │
├──────────────────────────────────┬──────────────────────────────────┤
│                                  │                                  │
│   Chat Pane (existing)            │   Live Preview Pane (NEW)        │
│                                  │                                  │
│   • re-uses chat UI               │   ┌─ Tabs: Preview │ Code │ Pubs │
│   • streams /chat/agent           │   │  ┌──────────────────────────┐│
│   • shows generate_site /         │   │  │                          ││
│     revise_site tool calls         │   │  │   <iframe>               ││
│     inline as activity items       │   │  │   live site v2 here      ││
│                                  │   │  │                          ││
│                                  │   │  └──────────────────────────┘│
│                                  │   │  Footer: ⟳ refresh ·          │
│                                  │   │  📱 mobile · 💻 desktop ·      │
│                                  │   │  v1 ▼ version selector ·      │
│                                  │   │  ⬇ download zip · 🚀 Publish   │
└──────────────────────────────────┴──────────────────────────────────┘
```

For `kind:'site'`, render the **right pane**: an iframe to the latest
version's preview URL. For `kind:'pptx' | 'docx'` render the existing
slide / page renderers. The chat pane is identical for all three kinds.

---

## 3. Pages & Routes

| Route | Component | Purpose |
|---|---|---|
| `/studio` | `StudioHome` | Existing — projects tab now includes site cards |
| `/studio/projects/new` | `NewProjectModal` | Modal — add `Site` to the kind picker |
| `/studio/projects/:projectId` | `ProjectWorkspace` | Existing shell. Branch on `kind === 'site'` to render `<SitePreviewPane />` |
| `/studio/projects/:projectId/sites/:version` | same workspace, version-pinned | Deep-link to a specific version (sets the version selector) |
| `/studio/sites/publications` | `PublicationsPage` | Standalone "all my live sites" list (across projects) |

No standalone "Sites" tab — keep it inside the existing Projects tab,
filterable by kind. This avoids a UX fork from PPTX/DOCX.

---

## 4. State Management

Add minimal new state to whatever pattern Content Studio already uses
(Zustand slice, React Query, Redux — match the rest of the app):

```ts
// types
type SiteArtifact = {
  id: string;
  project_id: string;
  kind: 'site';
  version: number;
  filename: string;        // e.g. "Portfolio.zip"
  size_bytes: number;
  file_count: number | null;
  meta: { source_tool?: 'generate_site' | 'revise_site' };
  created_at: string;
};

type Publication = {
  id: string;
  project_id: string;
  artifact_id: string;
  subdomain: string;
  custom_domain: string | null;
  is_active: boolean;
  published_at: string;
  request_count: number;
};

// per-project local state
type SiteProjectState = {
  artifacts: SiteArtifact[];
  selectedVersion: number;      // defaults to MAX(version)
  iframeKey: number;            // bump to force iframe reload
  publications: Publication[];
  publishing: boolean;
  device: 'desktop' | 'mobile' | 'tablet';
  rightPaneTab: 'preview' | 'code' | 'pubs';
};
```

Critical reactive rule:
> When a new artifact arrives via the chat stream (i.e. the chat hook
> wrote a new row), set `selectedVersion = newArtifact.version` and bump
> `iframeKey++` so React remounts the iframe and forces a clean reload.
> Do NOT mutate the iframe's `src` in place — Chrome can keep the old
> bundle cached.

---

## 5. API Client (TypeScript)

All endpoints live on the existing API host with the user's bearer
token. Extend the existing studio client:

```ts
// ─────────────────────────────────────────────────────────────────────
// Project list / create — REUSE existing endpoints, just allow 'site'
// ─────────────────────────────────────────────────────────────────────
api.post('/studio/projects', {
  kind: 'site',
  title: 'My Portfolio',
  conversation_id: undefined,   // backend creates one
});

api.get('/studio/projects?kind=site');

// ─────────────────────────────────────────────────────────────────────
// Site-specific
// ─────────────────────────────────────────────────────────────────────

// Build the iframe src for an authenticated preview.
// IMPORTANT: include the bearer token via cookie OR via a session-auth
// adapter — query-string tokens are fine for an embedded iframe but DO
// NOT log them.  See §7 for the recommended pattern.
function previewUrl(projectId: string, version: number, path = '') {
  return `${API_BASE}/studio/sites/${projectId}/preview/${version}/${path}`;
}

// Optional: load the {path: content} map for the in-app code editor.
api.get<{ artifact_id: string; files: Record<string,string>; file_count: number }>(
  `/studio/sites/${projectId}/files/${artifactId}`
);

// Subdomain availability + format check (debounced, on every keystroke).
api.get<{ available: boolean; reason?: string; subdomain: string }>(
  `/studio/sites/check/${subdomain}`
);

// Publish (or re-point) a subdomain.
api.post<{
  publication: Publication;
  urls: { path_url: string; subdomain_url: string };
}>(
  `/studio/sites/${projectId}/publish`,
  { artifact_id, subdomain }
);

// Unpublish.
api.post(`/studio/sites/${projectId}/unpublish`, { publication_id });

// List publications for a project (right-pane "Publications" tab).
api.get<{ publications: Publication[]; count: number }>(
  `/studio/sites/${projectId}/publications`
);

// All publications across projects (standalone Publications page).
api.get<{ publications: Publication[]; count: number }>(
  `/studio/sites/publications`
);

// Download the raw zip bundle (existing artifact endpoint, works for sites).
const downloadZipUrl = (projectId, artifactId) =>
  `${API_BASE}/studio/projects/${projectId}/artifacts/${artifactId}/download`;
```

---

## 6. Page-by-Page Component Spec

### 6.1 `<NewProjectModal />` — add Site kind

The existing modal already lets the user pick a kind. Add a third option:

```tsx
<KindPicker
  options={[
    { value: 'pptx', label: 'Presentation', icon: <SlidesIcon/> },
    { value: 'docx', label: 'Document',     icon: <DocIcon/> },
    { value: 'site', label: 'Website',      icon: <GlobeIcon/>,  // ← NEW
      hint: 'AI builds it as you chat. Publish to a public URL.' },
  ]}
/>
```

When `value === 'site'`, hide the "writing style" and "humanize" options
(they don't apply). Default the project title to `"New Website"`.

### 6.2 `<ProjectsGrid />` — show Sites among other projects

Each card is the same shape as PPTX/DOCX. For sites:
- Thumbnail: a low-res screenshot of the iframe (post-MVP — for v1 use
  a generic globe icon over a brand gradient).
- Subtitle: `"v{N} · {fileCount} files"` instead of slide/page count.
- Pill in the corner: `"Site"` (use the same chip component as PPTX/DOCX).
- Live badge: if there's at least one active publication, show a green
  dot + the subdomain (`my-portfolio.sites.…`).

Add a "Sites" filter chip to the existing `All / PPTX / DOCX` row.

### 6.3 `<ProjectWorkspace />` — branch on kind

Inside the existing two-pane shell:

```tsx
{project.kind === 'site' ? (
  <SitePreviewPane project={project} />
) : project.kind === 'pptx' ? (
  <PptxPreviewPane ... />
) : project.kind === 'docx' ? (
  <DocxPreviewPane ... />
) : null}
```

The chat pane on the left is unchanged. Re-bind it to
`project.conversation_id` so every new turn that emits `generate_site`
or `revise_site` lands as a new artifact under this project.

### 6.4 `<SitePreviewPane />` — the new component

```
┌──────────────────────────────────────────────────────────┐
│ Tabs: [ Preview ] [ Code ] [ Publications ]              │
│──────────────────────────────────────────────────────────│
│                                                          │
│   ╭──── DeviceFrame (desktop / tablet / mobile) ───╮     │
│   │                                                │     │
│   │           <iframe sandbox="…"                  │     │
│   │            src={previewUrl(...)} />            │     │
│   │                                                │     │
│   ╰────────────────────────────────────────────────╯     │
│                                                          │
│  ⟳  📱 💻 🖥   v[2 ▼]  Live: my-portfolio.sites.…  🚀     │
└──────────────────────────────────────────────────────────┘
```

Components inside this pane:

- `<DeviceFrame variant='desktop'|'tablet'|'mobile'>` — wraps the iframe
  in fixed widths (375 / 768 / 1280) for responsive checks. Use the
  existing brand styling.
- `<RefreshButton />` — bumps `iframeKey`.
- `<VersionSelector />` — dropdown of `artifacts.filter(a => a.kind==='site')`
  newest first, badge "Latest" on the max version.
- `<PublishChip />` — top-right summary; click opens the `<PublishModal />`.
- `<DownloadZipButton />` — direct link to `/studio/projects/{id}/artifacts/{aid}/download`.
- `<OpenInNewTabButton />` — opens the preview URL in a new browser tab.

### 6.5 `<PublishModal />`

Triggered from the publish chip, the right-pane footer button, or `⌘P`.

Form:
- `subdomain` text input — debounced check against
  `GET /studio/sites/check/{subdomain}` on every keystroke (300ms). Show:
  - 🟢 "available" + the resulting URLs (path + subdomain)
  - 🔴 backend `reason` if invalid/taken
- `version` selector — defaults to the version currently shown in the iframe.
- Submit → `POST /studio/sites/{pid}/publish` → on success, show the two
  URLs as click-to-copy chips and a "Open site ↗" button. Confetti is
  optional but encouraged.

Re-pointing an existing subdomain: if the user already has an active
publication on that subdomain, the modal pre-fills it and the submit
button changes to **"Update live site"**. Backend handles upsert atomically.

### 6.6 `<PublicationsPage />` (standalone)

Mounted at `/studio/sites/publications`. Reads `GET /studio/sites/publications`.

Table columns:
| Subdomain | Project | Version | Status | Requests | Published | Actions |
|---|---|---|---|---|---|---|
| my-portfolio | My Portfolio | v3 | Active | 1,204 | 2d ago | Open · Unpublish · Update… |

"Update…" opens the same `<PublishModal />` pre-filled, scoped to that
publication's project so the user can promote a newer version.

### 6.7 `<ProjectsGrid />` empty state for kind='site'

If `projects.filter(p => p.kind === 'site').length === 0`, show:

```
┌────────────────────────────────────────────┐
│  🌐  Build websites with AI                │
│  Describe what you want, see it live,      │
│  then publish to a public URL.             │
│                                            │
│  [ + New Website ]                         │
│  Examples:                                 │
│  • "Landing page for a coffee shop"        │
│  • "Photographer portfolio"                │
│  • "Personal résumé site"                  │
└────────────────────────────────────────────┘
```

Each example is a one-click button that creates a new project AND
preloads the chat input with the prompt.

---

## 7. The Live Preview Iframe

This is the piece that has to feel instant. Implementation rules:

### 7.1 Auth

The preview endpoint (`/studio/sites/{pid}/preview/{n}/...`) requires the
user's bearer token. An iframe can't easily attach `Authorization`
headers. Two acceptable patterns — pick whichever the rest of the app
already uses:

**Option A — Cookie session (preferred)** — if your app already sets a
session cookie alongside the bearer token, the iframe will pick it up
automatically. The backend's `get_current_user_id` accepts JWT, but if
your app uses cookie auth, route the iframe through a same-origin proxy
that forwards the cookie. Easiest if frontend + API are on the same root.

**Option B — Short-lived signed iframe URL** — add a new endpoint
`POST /studio/sites/{pid}/preview-token` that returns a 5-minute signed
URL. Use that as the `src`. (This requires a small backend addition; for
v1 use Option A or just include the token as a header via a service worker.)

For v1 of the frontend, simplest is: render the iframe via a fetch +
blob-URL fallback when running cross-origin:

```ts
// Generic fallback for any auth scheme
async function loadPreviewBlob(projectId: string, version: number) {
  const res = await fetch(previewUrl(projectId, version, ''), {
    headers: { Authorization: `Bearer ${getToken()}` },
    credentials: 'include',
  });
  const html = await res.text();
  return URL.createObjectURL(new Blob([html], { type: 'text/html' }));
}
```
…and use the blob URL as the iframe's `src`. Asset requests inside the
iframe will then need to resolve against the API. Use a `<base href>`
rewrite or, easier, **use Option A and avoid blob URLs entirely**.

### 7.2 Sandboxing

Always set:
```html
<iframe
  sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
  referrerpolicy="no-referrer"
  loading="lazy"
/>
```
The backend already sets `X-Frame-Options: SAMEORIGIN` and a strict CSP
on every preview response.

### 7.3 Reload semantics

When a new artifact arrives via the chat stream:
1. Update `selectedVersion = newArtifact.version`.
2. `iframeKey++` so React remounts the iframe.
3. Optionally show a toast: "Updated to v{N}".

Avoid `iframe.contentWindow.location.reload()` — full remount via key
is cleaner and stomps any old service-worker cache the AI might have
shipped.

### 7.4 Console capture (nice to have)

Inject a `postMessage` bridge so the parent window can show console
errors from the user's site in a small "Issues" panel under the iframe.
Implement only if you control the bundle — for v1, skip.

---

## 8. Publish Flow

```
User clicks "Publish"
        │
        ▼
PublishModal opens with version pre-filled
        │
        ▼
User types subdomain → debounced GET /studio/sites/check/{sub}
        │
        ▼  green
User clicks "Publish"
        │
        ▼
POST /studio/sites/{pid}/publish { artifact_id, subdomain }
        │
        ▼
Show success state with two URLs:
   • path_url     → https://{api-host}/s/{sub}/        (works today)
   • subdomain_url → https://{sub}.sites.{base}/        (only works if DNS is set up)
        │
        ▼
Update local publications cache; the project header chip flips to
"Live: my-portfolio.sites.…" (or the path URL if no base domain configured).
```

Frontend **MUST** show the path URL prominently and treat the subdomain
URL as secondary until backend reports `PUBLIC_SITES_BASE_DOMAINS` is
set. To keep the frontend simple, just show both URLs and let the user
discover which works. (Optional: probe the subdomain URL in the
background and only show it if the response is 200.)

---

## 9. Code Editor (Optional Power-User View)

The "Code" tab in `<SitePreviewPane />` shows the file map for the
current version, read-only for v1:

```tsx
const { data } = useSWR(
  `/studio/sites/${projectId}/files/${artifact.id}`,
  fetcher
);

<MonacoEditor
  files={data.files}                    // {path: content}
  language={inferFromExt}
  readOnly={true}
/>
```

Files prefixed `b64:` are binary (images, fonts, etc.) — don't try to
render them as text; show a thumbnail preview instead.

For v2, allow editing → emit a synthesised `revise_site` tool-use into
the chat conversation so the existing chat hook captures it as a new
artifact. (Don't try to short-circuit the chat path — it'd duplicate the
ingest pipeline.)

---

## 10. Streaming + Real-Time Patterns

The chat already streams via SSE. When the assistant emits a tool_use
block of type `generate_site` or `revise_site`, render an inline
activity card in the chat:

```
┌─────────────────────────────────────────────┐
│ 🛠  Building website…                        │
│    Generated 7 files (24 KB)                │
│    ✓ index.html                             │
│    ✓ styles/main.css                        │
│    ✓ scripts/app.js                         │
│    ✓ ...                                    │
└─────────────────────────────────────────────┘
```

When the matching `tool_result` arrives:
- Refetch `GET /studio/projects/{id}/artifacts` (or apply the artifact
  optimistically from the result payload — `file_id` + `filename` +
  `size_kb` are in the response).
- Bump `iframeKey` to reload the preview.
- Toast: `"Site updated to v{N}"`.

Same pattern for `revise_site`.

---

## 11. Empty / Loading / Error States

| Surface | Empty | Loading | Error |
|---|---|---|---|
| ProjectsGrid (no Sites) | Friendly empty state §6.7 with example prompts | Skeleton cards | "Couldn't load projects — Retry" |
| `<SitePreviewPane>` (no artifacts yet) | "Start a chat on the left to build your site" + suggested prompts | Skeleton browser-frame | "Preview unavailable — open in new tab" |
| Publish modal availability check | hidden | spinner inside the input | inline red text from `reason` |
| `<PublicationsPage>` | "You haven't published any sites yet." | Skeleton table rows | Banner with retry |

---

## 12. Accessibility & Keyboard Shortcuts

- All controls reachable by keyboard. Iframe gets `title="Live preview of {project title}, version {N}"` for screen readers.
- `⌘/Ctrl + R` inside the right pane → reload iframe (preventDefault on
  the global one only when focus is in the right pane).
- `⌘/Ctrl + P` → open Publish modal.
- `[` / `]` → previous / next version.
- `D` → toggle desktop/mobile/tablet device frame.
- High-contrast publish status colours; do not rely on green/red alone.

---

## 13. Security Notes

- Publish/unpublish/preview are all auth-gated on the backend. Don't
  surface admin-only actions to non-owners (the API will 403/404).
- Treat anything inside the iframe as untrusted — never read its DOM
  except via `postMessage` from a script you injected at extract time.
- The published path URL is fully public; remind users in the publish
  modal that anyone with the link can view the site.
- If the user adds custom JS that calls `fetch('/api/...')`, the same-
  origin fetch will hit your real API — surface this risk in the publish
  modal (single-line note is fine).

---

## 14. QA Checklist

- [ ] Create a Site project from the modal → workspace opens with empty
  preview pane and the chat ready.
- [ ] Send a one-line prompt → the assistant calls `generate_site` →
  iframe loads v1 within ~2s of the tool result.
- [ ] Send a follow-up like "make the buttons rounded" → `revise_site`
  fires → iframe auto-reloads to v2.
- [ ] Switch the version dropdown back to v1 → iframe shows v1 again.
- [ ] Click "Publish" → type a subdomain → see the green availability
  state → click submit → success state shows both URLs.
- [ ] Open the path URL `/s/<sub>/` in a new private tab (no auth) → site
  loads correctly.
- [ ] Edit your subdomain → publish again → second submit returns the
  same publication ID and the new artifact version is what's served.
- [ ] Unpublish → public URL now returns 404 within 1–2s.
- [ ] Try a reserved subdomain (`www`, `admin`, …) → modal blocks submit
  with the backend's reason.
- [ ] Try a subdomain another user owns → modal shows "already taken".
- [ ] Type subdomain with spaces / capitals → blocked client-side AND
  server-side (defence in depth).
- [ ] Switch to mobile device frame → iframe width is 375px, scaling
  preserved.
- [ ] Download zip → file is a valid archive containing the version's
  files.
- [ ] Refresh the workspace → state recovers correctly (artifacts list,
  selected version, publications).
- [ ] Sites tab on the Projects grid filters correctly.
- [ ] Empty state on Projects grid (no sites) shows the example prompts
  and one click creates a project pre-filled with that prompt.
- [ ] Keyboard shortcuts: `⌘P` opens publish, `[`/`]` change versions,
  `D` cycles device frames.
- [ ] No layout shift when iframe reloads (use a fixed-height container).
- [ ] All API errors show actionable toasts, not raw stack traces.

---

## Reference: Backend Endpoints (Cheat Sheet)

| Method | Path | Body / Notes |
|---|---|---|
| `POST`  | `/studio/projects` | `{ kind:'site', title }` → `{ project }` |
| `GET`   | `/studio/projects?kind=site` | filtered list |
| `GET`   | `/studio/projects/{id}` | `{ project, artifacts }` |
| `GET`   | `/studio/projects/{id}/artifacts/{aid}/download` | binary zip download |
| `GET`   | `/studio/sites/{pid}/preview/{version}` | HTML — iframe `src` |
| `GET`   | `/studio/sites/{pid}/preview/{version}/{path}` | static asset (CSS, JS, image…) |
| `GET`   | `/studio/sites/{pid}/files/{aid}` | `{ files: {path: content} }` |
| `GET`   | `/studio/sites/check/{subdomain}` | `{ available, reason? }` |
| `POST`  | `/studio/sites/{pid}/publish` | `{ artifact_id, subdomain }` → `{ publication, urls }` |
| `POST`  | `/studio/sites/{pid}/unpublish` | `{ publication_id }` |
| `GET`   | `/studio/sites/{pid}/publications` | per-project |
| `GET`   | `/studio/sites/publications` | global, current user |
| `GET`   | `/s/{subdomain}/...` | **public** — no auth, this is the live URL users share |

For full backend architecture see `Documentation/CONTENT_STUDIO_SITES_GUIDE.md`.
