# Content Studio — Frontend Build Guide

This document is the complete spec for the Content Studio frontend. The
backend is live and committed. Your job is to build the UI on top of these
endpoints. USE THE SAME THEME AS THE REST OF THE APP, MAKE SURE THE POWERPOINT AND WORD DOCUMENT PREVIEW WORKS,

HIDE THE PAGE FROM THE NAVIGATION MENU

---

## Table of Contents

1. [Mental Model](#1-mental-model)
2. [Information Architecture](#2-information-architecture)
3. [Pages & Routes](#3-pages--routes)
4. [State Management](#4-state-management)
5. [API Client (TypeScript)](#5-api-client-typescript)
6. [Page-by-Page Component Spec](#6-page-by-page-component-spec)
7. [Slide / Document Renderers](#7-slide--document-renderers)
8. [Visual Editor — JSON Ops Contract](#8-visual-editor--json-ops-contract)
9. [Voice-Clone Wizard Flow](#9-voice-clone-wizard-flow)
10. [Humanizer UX](#10-humanizer-ux)
11. [Streaming + Real-Time Patterns](#11-streaming--real-time-patterns)
12. [Empty / Loading / Error States](#12-empty--loading--error-states)
13. [Accessibility & Keyboard Shortcuts](#13-accessibility--keyboard-shortcuts)
14. [QA Checklist](#14-qa-checklist)

---

## 1. Mental Model

```
Project = Conversation + Kind + Style + Versioned Artifacts
   │
   ├─ kind = 'pptx' | 'docx' | 'chat'
   ├─ conversation_id  ──► everything goes through POST /chat/agent
   ├─ style_profile_id ──► auto-injects cloned voice into the chat (no UI work)
   └─ artifacts[]      ──► v1, v2, v3, ...  (each is a real .pptx/.docx file)
```

Key rule: **all generation lives inside `/chat/agent`.** When a user is in a
project, every chat message that triggers `generate_pptx`, `revise_pptx`,
`generate_docx`, etc. automatically writes a new artifact version to the
project. You don't call any new generation endpoint.

Three independent subsystems:

- **Projects** (`/studio/projects`) — list, create, open, edit, download
- **Styles**   (`/studio/styles`)   — voice cloning wizard, attach to project
- **Humanize** (`/studio/humanize`) — paste any text → humanized output + scores

---

## 2. Information Architecture

Top-level navigation surface:

```
[ Sidebar ]
├─ Dashboard
├─ Chat               (existing)
├─ Content Studio  ◄── NEW (this is the entire feature)
│   ├─ Projects (default tab)        — recent grid of project cards
│   ├─ Styles                         — voice clones list
│   └─ Humanize                       — playground for the rewrite tool
├─ Knowledge Base     (existing)
└─ Settings           (existing)
```

Inside a single project the layout is **two-pane**:

```
┌──────────────────────────────────────────────────────────────────────┐
│  ProjectHeader: title (rename) · style chip · humanize chip · actions │
├─────────────────────────────────────┬────────────────────────────────┤
│                                     │                                │
│   Chat Pane                         │   Preview / Editor Pane        │
│                                     │                                │
│   • re-uses existing chat UI        │   • slide thumbnails or pages  │
│   • upload button (existing)        │   • Edit / Preview / Present   │
│   • streams /chat/agent             │     toggle                     │
│   • includes voice + humanize       │   • Download button            │
│     toggles in the input footer     │   • version dropdown (v1/v2/…) │
│                                     │                                │
└─────────────────────────────────────┴────────────────────────────────┘
```

Same shell for both `kind: 'pptx'` and `kind: 'docx'`. For `kind: 'chat'`
the right pane is collapsed and the chat takes the full width.

---

## 3. Pages & Routes

| Route | Component | Purpose |
|---|---|---|
| `/studio` | `StudioHome` | Tabs: Projects \| Styles \| Humanize. Default = Projects grid. |
| `/studio/projects/new` | `NewProjectModal` | Modal: pick kind, title, attach style, humanize default |
| `/studio/projects/:projectId` | `ProjectWorkspace` | The two-pane shell |
| `/studio/projects/:projectId/preview/:artifactId` | `ProjectWorkspace` (preview mode) | Same workspace, "Preview" tab active, version pinned |
| `/studio/projects/:projectId/present/:artifactId` | `PresentMode` | Fullscreen present (PPTX only) |
| `/studio/styles` | `StylesList` | Grid of voice profiles |
| `/studio/styles/new` | `StyleWizard` (step 1 of 4) | Wizard |
| `/studio/styles/:styleId` | `StyleDetail` | Inspect samples + voice card + preview |
| `/studio/humanize` | `HumanizePlayground` | Standalone text rewriter |

Use a query param like `?ver=3` for version selection inside a workspace
so the URL is shareable.

---

## 4. State Management

**Global**:
- `currentUser` (already exists — JWT)
- `studioProjects` cache (per-list, paginated; invalidate on create/update/delete)
- `studioStyles` cache
- Theme / preferences (existing)

**Per-workspace** (mount only when on `/studio/projects/:id`):
- `project: StudioProject`  — refetched on mount
- `artifacts: StudioArtifact[]`  — refetched after each chat-finish
- `currentArtifactId: string | null`
- `editorMode: 'preview' | 'edit' | 'present'`
- `pendingOps: EditOp[]`  — staged visual-editor ops, sent on Save
- `chatStreamState`: piggy-back on existing chat SDK store, just override `conversation_id` to `project.conversation_id`

**Recommended stack** (matches the rest of the app): TanStack Query for
server state + Zustand for the per-workspace local UI state. SWR also fine.

**Critical invalidation rule**: when the chat stream finishes (existing
`onFinish` callback), call:

```ts
queryClient.invalidateQueries({ queryKey: ['studio', 'project', projectId] });
```

That single line refreshes the artifact list — any newly captured pptx/docx
will appear in the right pane within a render.

---

## 5. API Client (TypeScript)

Drop this in `src/api/studio.ts` (or wherever your existing api client lives).

```ts
import { apiFetch, apiStreamPost } from './client';   // your existing helpers

// ───── Types ──────────────────────────────────────────────────────────────

export type ProjectKind = 'pptx' | 'docx' | 'chat';
export type ArtifactKind = 'pptx' | 'docx';
export type Intensity = 'light' | 'standard' | 'max';
export type SeoTarget = 'linkedin' | null;
export type StyleStatus = 'draft' | 'analyzing' | 'ready' | 'failed';

export interface HumanizeSettings {
  enabled: boolean;
  intensity: Intensity;
  seo_target: SeoTarget;
  preserve_facts: boolean;
  auto_apply?: boolean;
}

export interface StudioProject {
  id: string;
  user_id: string;
  conversation_id: string;
  kind: ProjectKind;
  title: string;
  description: string;
  style_profile_id: string | null;
  humanize_settings: HumanizeSettings;
  current_artifact_id: string | null;
  thumbnail_path: string | null;
  tags: string[];
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  last_opened_at: string;
}

export interface StudioArtifact {
  id: string;
  project_id: string;
  conversation_id: string | null;
  message_id: string | null;
  source_file_id: string | null;
  kind: ArtifactKind;
  version: number;
  filename: string;
  size_bytes: number;
  slide_count: number | null;
  page_count:  number | null;
  edit_state:  Record<string, any> | null;
  meta:        Record<string, any>;
  created_at:  string;
}

export interface StudioStyle {
  id: string;
  user_id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  status: StyleStatus;
  voice_card?: any;
  system_prompt?: string;
  exemplars?: Array<{ text: string; score: number }>;
  fidelity_score?: number | null;
  sample_count: number;
  total_words: number;
  created_at: string;
  updated_at: string;
}

export interface StudioStyleSample {
  id: string;
  style_id: string;
  title: string;
  source: 'paste' | 'file' | 'url';
  source_url?: string | null;
  source_file_id?: string | null;
  word_count: number;
  char_count: number;
  stats: any;
  created_at: string;
}

export interface HumanizeRun {
  run_id: string;
  output: string;
  input: string;
  scores: {
    ai_detection: number;       // 0..1, lower = more human
    components: Record<string, number>;
    binoculars_ratio: number | null;
    gltr: { top1_pct: number; top10_pct: number; top100_pct: number; ai_score: number } | null;
    roberta_p_ai: number | null;
    style_fidelity: number | null;
    stats_in:  any;
    stats_out: any;
    ai_detection_in: number;
  };
  passes_summary: Array<{ pass: string; ms: number; len_in: number; len_out: number; changed: boolean; ai_detection_after?: number }>;
  lost_facts: { numbers: string[]; quotes: string[]; names: string[] };
  detector_retries: number;
  duration_ms: number;
}

// ───── Edit ops ─────────────────────────────────────────────────────────

export type PptxOp =
  | { type: 'text';            slide: number; shape_index: number; value: string }
  | { type: 'text_replace';    slide?: number; find: string; replace: string; all?: boolean }
  | { type: 'add_slide_note';  slide: number; value: string }
  | { type: 'reorder_slides';  order: number[] }
  | { type: 'delete_slide';    slide: number }
  | { type: 'duplicate_slide'; slide: number };

export type DocxOp =
  | { type: 'text_replace';      find: string; replace: string; all?: boolean }
  | { type: 'replace_paragraph'; index: number; value: string }
  | { type: 'append_paragraph';  value: string; style?: string }
  | { type: 'append_heading';    value: string; level?: 1 | 2 | 3 };

export type EditOp = PptxOp | DocxOp;

// ───── Projects ─────────────────────────────────────────────────────────

export const studioApi = {
  listProjects: (opts: { kind?: ProjectKind; include_archived?: boolean; limit?: number; offset?: number } = {}) =>
    apiFetch<{ projects: StudioProject[]; count: number }>(`/studio/projects?${new URLSearchParams(opts as any)}`),

  createProject: (body: {
    kind: ProjectKind; title?: string; description?: string;
    style_profile_id?: string | null; humanize_settings?: HumanizeSettings;
    conversation_id?: string; tags?: string[];
  }) =>
    apiFetch<{ project: StudioProject }>('/studio/projects', { method: 'POST', body: JSON.stringify(body) }),

  getProject: (id: string) =>
    apiFetch<{ project: StudioProject; artifacts: StudioArtifact[] }>(`/studio/projects/${id}`),

  patchProject: (id: string, body: Partial<StudioProject>) =>
    apiFetch<{ project: StudioProject }>(`/studio/projects/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  deleteProject: (id: string, purge_files = true) =>
    apiFetch<{ deleted: true; id: string }>(`/studio/projects/${id}?purge_files=${purge_files}`, { method: 'DELETE' }),

  listArtifacts: (id: string) =>
    apiFetch<{ artifacts: StudioArtifact[] }>(`/studio/projects/${id}/artifacts`),

  getArtifact: (pid: string, aid: string) =>
    apiFetch<{ artifact: StudioArtifact }>(`/studio/projects/${pid}/artifacts/${aid}`),

  // Returns a Blob; do NOT JSON-parse this.
  downloadArtifact: (pid: string, aid: string): Promise<Blob> =>
    fetch(`${API_BASE}/studio/projects/${pid}/artifacts/${aid}/download`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    }).then(r => { if (!r.ok) throw new Error('download failed'); return r.blob(); }),

  applyEdits: (pid: string, aid: string, ops: EditOp[]) =>
    apiFetch<{ artifact: StudioArtifact }>(`/studio/projects/${pid}/artifacts/${aid}/edit`, {
      method: 'POST', body: JSON.stringify({ ops, save_edit_state: true }),
    }),

  uploadArtifact: (pid: string, file: File) => {
    const fd = new FormData(); fd.append('file', file);
    return apiFetch<{ artifact: StudioArtifact }>(`/studio/projects/${pid}/artifacts/upload`, { method: 'POST', body: fd });
  },

  // ───── Styles ───────────────────────────────────────────────────────────
  listStyles:    () => apiFetch<{ styles: StudioStyle[] }>('/studio/styles'),
  getStyle:      (id: string) => apiFetch<{ style: StudioStyle; samples: StudioStyleSample[] }>(`/studio/styles/${id}`),
  createStyle:   (body: { name: string; description?: string; icon?: string; color?: string }) =>
    apiFetch<{ style: StudioStyle }>('/studio/styles', { method: 'POST', body: JSON.stringify(body) }),
  patchStyle:    (id: string, body: Partial<StudioStyle>) =>
    apiFetch<{ style: StudioStyle }>(`/studio/styles/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteStyle:   (id: string) => apiFetch<{ deleted: true; id: string }>(`/studio/styles/${id}`, { method: 'DELETE' }),

  addSampleText: (id: string, body: { text: string; title?: string; source_url?: string; source_file_id?: string }) =>
    apiFetch<{ sample: StudioStyleSample }>(`/studio/styles/${id}/samples`, { method: 'POST', body: JSON.stringify(body) }),

  uploadSample:  (id: string, file: File, title = '') => {
    const fd = new FormData(); fd.append('file', file); fd.append('title', title);
    return apiFetch<{ sample: StudioStyleSample }>(`/studio/styles/${id}/samples/upload`, { method: 'POST', body: fd });
  },

  listSamples:   (id: string) => apiFetch<{ samples: StudioStyleSample[] }>(`/studio/styles/${id}/samples`),
  deleteSample:  (id: string, sampleId: string) =>
    apiFetch<{ deleted: true }>(`/studio/styles/${id}/samples/${sampleId}`, { method: 'DELETE' }),

  analyzeStyle:  (id: string, self_test = true) =>
    apiFetch<{ style: StudioStyle }>(`/studio/styles/${id}/analyze?self_test=${self_test}`, { method: 'POST' }),
  previewStyle:  (id: string, prompt: string, max_tokens = 400) =>
    apiFetch<{ output: string }>(`/studio/styles/${id}/preview`, {
      method: 'POST', body: JSON.stringify({ prompt, max_tokens }),
    }),
  getSystemPrompt: (id: string) =>
    apiFetch<{ status: string; system_prompt: string | null; fidelity_score: number | null; voice_card: any; exemplars: any[] }>(
      `/studio/styles/${id}/system_prompt`),

  // ───── Humanize ─────────────────────────────────────────────────────────
  humanize: (body: {
    text: string; intensity?: Intensity; seo_target?: SeoTarget;
    style_profile_id?: string | null; project_id?: string | null;
    preserve_facts?: boolean;
  }) => apiFetch<HumanizeRun>('/studio/humanize', { method: 'POST', body: JSON.stringify(body) }),

  scoreText: (text: string) => apiFetch<HumanizeRun['scores'] & any>('/studio/humanize/score', {
    method: 'POST', body: JSON.stringify({ text }),
  }),

  listHumanizeRuns: (project_id?: string, limit = 50) =>
    apiFetch<{ runs: any[] }>(`/studio/humanize/runs?${new URLSearchParams({ ...(project_id ? { project_id } : {}), limit: String(limit) })}`),
  getHumanizeRun:  (run_id: string) =>
    apiFetch<{ run: any; trace: any }>(`/studio/humanize/runs/${run_id}`),
};
```

> **Heads-up**: the auth header pattern should already match the rest of
> your app — every studio route uses the same Supabase JWT bearer token.

---

## 6. Page-by-Page Component Spec

### 6.1 `StudioHome` — `/studio`

A tabbed shell. Default tab = Projects.

```
┌─ Tabs: [ Projects ] [ Styles ] [ Humanize ] ──────── + New Project ─┐
│ Filter: [ All | PPTX | DOCX | Chat ]    Sort: [ Recent ▼ ]            │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──┐             │
│  │ thumb       │  │ thumb       │  │ thumb       │  │+│             │
│  │ Q1 Outlook  │  │ Fund Memo   │  │ Brand Brief │  └──┘             │
│  │ pptx · v3   │  │ docx · v1   │  │ pptx · v7   │                    │
│  │ 2h ago      │  │ Yesterday   │  │ 3d ago      │                    │
│  └─────────────┘  └─────────────┘  └─────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
```

`ProjectCard` (clickable):
- Renders `thumbnail_path` if present, else a kind-specific placeholder.
- Shows `title`, `kind`, `current_artifact?.version`, relative `updated_at`.
- Right-click / long-press → context menu: Rename · Duplicate · Archive · Delete.

`+ New Project` opens a modal:

```
What are you making?
( ) PowerPoint (.pptx)
( ) Word document (.docx)
( ) Just chat (no document)

Title: [_______________________]

Voice clone: [None ▼]   ← picks from /studio/styles?status=ready
Humanize:    [ ] On     intensity: [Standard ▼]   SEO: [None ▼]

[ Cancel ]                               [ Create & Open ]
```

On submit → `studioApi.createProject(...)` → `navigate(/studio/projects/${id})`.

---

### 6.2 `ProjectWorkspace` — `/studio/projects/:projectId`

The main page. Two-pane layout described above. Concrete components:

```
ProjectWorkspace
├─ ProjectHeader
│   ├─ Title (inline-editable; PATCH on blur)
│   ├─ KindBadge
│   ├─ StyleChip      ← if style_profile_id set, click to open detail in side modal
│   ├─ HumanizeToggle ← live edit; PATCH humanize_settings
│   ├─ VersionDropdown(v1, v2, v3 …)
│   ├─ ModeToggle [ Edit | Preview | Present ]   (Present hidden for docx)
│   └─ Actions: Download · Share · Archive · Delete
│
├─ Split (resizable)
│   ├─ ChatPane
│   │   ├─ MessageList   ← reuses your existing chat history component
│   │   ├─ FileChip strip (uploaded attachments)
│   │   ├─ HumanizeBanner (if humanize_settings.auto_apply)
│   │   └─ ChatInput
│   │       ├─ FileUpload button (existing)
│   │       ├─ Voice toggle (shows current style_profile_id)
│   │       └─ Send → POST /chat/agent (existing stream)
│   │
│   └─ PreviewPane
│       ├─ For PPTX:  <SlideReel artifact={current} mode={editorMode} />
│       └─ For DOCX:  <PageReel  artifact={current} mode={editorMode} />
└─ EditOpsBuffer (floating bottom-right, shown only in edit mode)
    ├─ "3 unsaved changes"
    ├─ [ Discard ]  [ Save → v(n+1) ]
```

### 6.3 `StylesList` — `/studio/styles`

Grid of voice cards. Each card shows:
- icon + color
- name + status badge (`Draft`, `Analyzing…`, `Ready`, `Failed`)
- sample_count, total_words
- fidelity_score as a 0–100 bar (only if `ready`)
- click → `/studio/styles/:id`

`+ New Voice` button → `/studio/styles/new`.

### 6.4 `StyleWizard` — 4 steps

See [§9](#9-voice-clone-wizard-flow) for the full step-by-step.

### 6.5 `StyleDetail` — `/studio/styles/:id`

```
┌ Header: name, status, fidelity bar, [Re-analyze], [Delete] ──────────┐
├ Tabs: [ Samples ] [ Voice Card ] [ System Prompt ] [ Preview ]       │
├──────────────────────────────────────────────────────────────────────┤
│  Samples tab:                                                         │
│   • table: title, source, words, added_at, [view] [delete]            │
│   • [ + Add sample ]   [ ⬆ Upload file ]                              │
│                                                                       │
│  Voice Card tab:                                                      │
│   • two-column JSON view of voice_card.qualitative + quantitative    │
│   • render do_rules / dont_rules as bullets                           │
│   • signature_phrases as chips                                        │
│                                                                       │
│  System Prompt tab:                                                   │
│   • read-only textarea with the cached system_prompt                  │
│   • [Copy]                                                            │
│                                                                       │
│  Preview tab:                                                         │
│   • textarea: "Write me a short LinkedIn hook about discipline."      │
│   • [Generate] → calls /preview, shows result with copy button        │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.6 `HumanizePlayground` — `/studio/humanize`

```
┌ Top bar: project picker [None ▼]   style picker [None ▼]            ┐
│ Intensity [ Standard ▼ ]   SEO target [ None | LinkedIn ]            │
│ [ ] Preserve facts                                                   │
├──────────────────────────────────────────────────────────────────────┤
│  ┌─ Input ───────────────┐   ┌─ Output ──────────────────┐           │
│  │                        │   │                          │           │
│  │  textarea              │   │  rendered output         │           │
│  │  [Score only]          │   │  (paragraphs)            │           │
│  │  [Humanize →]          │   │                          │           │
│  └────────────────────────┘   └──────────────────────────┘           │
├──────────────────────────────────────────────────────────────────────┤
│  Score panel:                                                         │
│  • AI detection: 18% [██░░░░░░░░] (was 71%)                          │
│  • Style fidelity: 0.78                                               │
│  • Detector breakdown: Binoculars 0.16  GLTR 0.19  Roberta 0.14      │
│  • Lost facts: numbers ✓ 0  quotes ✓ 0  names ✓ 0                    │
│  • Pass timeline (collapsible): scrub → burst → perp → fact-guard    │
└──────────────────────────────────────────────────────────────────────┘
```

Streaming note: the humanize endpoint is **not streamed** — it's a single
POST that can take 5–30 seconds. Show a progress indicator with `passes_summary`
labels animating ("Removing AI fingerprints…", "Varying sentence lengths…",
"Running detector ensemble…") to keep the user engaged.

---

## 7. Slide / Document Renderers

You said the frontend will render slides — here's the recommended approach.

### 7.1 PPTX rendering

Two libraries that work well:

| Library | License | What it gives you |
|---|---|---|
| **`pptxjs`** (Lior Vasilevsky) | MIT | Renders .pptx → HTML. Acceptable visual fidelity, no server needed. |
| **`react-pptx`** | MIT | Component-based; better for custom rendering. |
| **canvas-based custom** | — | Parse with `pptxgenjs` or `JSZip + pptx-parser`, draw to `<canvas>`. Best fidelity but most work. |

Recommended: start with **pptxjs** for fast TTM, swap in custom rendering later.

```tsx
import PPTXjs from 'pptxjs';   // or whichever wrapper you prefer

async function SlideReel({ projectId, artifact, mode }: Props) {
  const blob = await studioApi.downloadArtifact(projectId, artifact.id);
  const arrayBuffer = await blob.arrayBuffer();

  // Render slide thumbnails
  const slides = await PPTXjs.parse(arrayBuffer);

  return (
    <div className="slide-reel">
      <div className="slide-strip">
        {slides.map((s, i) => (
          <SlideThumb key={i} slide={s} active={i + 1 === activeSlide}
            onClick={() => setActiveSlide(i + 1)} />
        ))}
      </div>
      <div className="slide-stage">
        <SlideRenderer slide={slides[activeSlide - 1]} mode={mode} />
      </div>
    </div>
  );
}
```

`SlideRenderer` in **edit mode** wraps every text frame in a `contentEditable`
or click-to-edit overlay. When the user changes text, push an op to the
`pendingOps` buffer:

```ts
pendingOps.push({
  type: 'text',
  slide: activeSlide,
  shape_index: shape.index,
  value: newText,
});
```

When the user clicks **Save** in `EditOpsBuffer`, call:

```ts
const { artifact: v2 } = await studioApi.applyEdits(projectId, currentArtifactId, pendingOps);
setCurrentArtifactId(v2.id);
setPendingOps([]);
queryClient.invalidateQueries({ queryKey: ['studio', 'project', projectId] });
```

### 7.2 DOCX rendering

Use **`docx-preview`** (npm: `docx-preview`) — renders a .docx file into a
DOM container with high fidelity. Or `mammoth.js` if you only need text.

```tsx
import { renderAsync } from 'docx-preview';

const blob = await studioApi.downloadArtifact(projectId, artifact.id);
await renderAsync(blob, containerRef.current!);
```

Edit mode for DOCX is simpler — just expose a list of paragraphs in the
sidebar with `replace_paragraph` ops on edit, plus a global find-replace bar
that emits `text_replace` ops.

### 7.3 Present mode (PPTX only)

Fullscreen, keyboard-controlled (←/→, Esc, F). One slide at a time. No
edit overlays. Use the same `SlideRenderer` in `mode='present'`.

---

## 8. Visual Editor — JSON Ops Contract

The backend accepts a flat list of ops and applies them in order. The UI
should:

1. **Buffer** ops locally as the user makes edits (don't send each keystroke).
2. **Show a count** ("3 unsaved changes") with Discard / Save buttons.
3. **Save** posts the whole array. Backend produces `v(n+1)`.
4. **Optimistic UI**: assume success for trivial ops (text edit), show
   pending state for structural ops (delete_slide, reorder_slides) until
   the backend returns the new artifact.
5. **Unknown op types** are silently skipped server-side, so you can ship
   new op shapes ahead of backend updates safely.

Op cookbook for common UI actions:

| User action | Op |
|---|---|
| Edits text in a placeholder | `{type:'text', slide, shape_index, value}` |
| Find-replace bar | `{type:'text_replace', find, replace, all}` (no `slide` = whole deck/doc) |
| Adds a speaker note | `{type:'add_slide_note', slide, value}` |
| Drags slide thumb to reorder | `{type:'reorder_slides', order:[...]}` |
| Right-click → Delete slide | `{type:'delete_slide', slide}` |
| Right-click → Duplicate slide | `{type:'duplicate_slide', slide}` |

DOCX equivalents are trivial: `replace_paragraph`, `append_paragraph`,
`append_heading`, `text_replace`.

---

## 9. Voice-Clone Wizard Flow

Four screens, with a progress bar at the top.

### Step 1 — Name it

```
What should we call this voice?
[ ___________________________ ]    ← name
[ optional description ]
[ icon picker ]   [ color picker ]
                                      [ Cancel ] [ Next → ]
```

POST to `/studio/styles` with `{name, description, icon, color}`. Receive
`style.id`. Stash in wizard state.

### Step 2 — Add samples

```
Add 3+ samples of this person's writing.
The more samples, the better the clone.

[ ➕ Paste text ]   [ ⬆ Upload file (.txt/.md/.docx/.pdf) ]

Samples added (3):
 • LinkedIn post: "Discipline beats motivation…"   1,240 words   [×]
 • Newsletter Q1                                    3,012 words   [×]
 • Memo to team Mar-2024                            850  words   [×]

Recommended minimum: 3 samples / 1,500+ total words
                                       [ ← Back ] [ Analyze → ]
```

Each "Paste text" entry POSTs to `/studio/styles/{id}/samples`.
Each upload POSTs `multipart/form-data` to `/samples/upload`.

Disable **Analyze** until `samples.length >= 1` and `total_words >= 500`.

### Step 3 — Analyze (long-running)

```
Analyzing the voice...

[●] Extracting linguistic fingerprints
[●] Building voice card with Claude
[●] Picking exemplars
[ ] Self-test fidelity check
```

Call `POST /studio/styles/{id}/analyze?self_test=true`. This can take 30–90
seconds. The endpoint returns the full updated style row when done.

Pattern: while waiting, **poll** `GET /studio/styles/{id}` every 2 seconds
to keep the UI alive. Status transitions: `draft` → `analyzing` → `ready` |
`failed`. (The endpoint sets `analyzing` immediately, so polling shows
progress even though the backend currently runs it synchronously.)

### Step 4 — Vibe check + done

```
Voice cloned ✓     Fidelity: 0.78

Try it out:
[ Write a short LinkedIn hook about discipline ]
                                                 [Generate]

(generated output appears here, in the cloned voice)

[ Use this voice in a project → ]   ← opens NewProjectModal preselected
                                     [ Done ]
```

---

## 10. Humanizer UX

Three places it shows up:

### 10.1 Standalone playground (`/studio/humanize`)

Already described in §6.6. Use this as the showcase / debug tool.

### 10.2 Inline within a project (footer toolbar)

In the chat pane footer:

```
[ ✏ Humanize last reply ]   [ Auto-apply: ☐ ]
```

When the user clicks **Humanize last reply**, take the last assistant
message text → call `studioApi.humanize({ text, project_id, style_profile_id, intensity, seo_target })`
→ insert a new message at the end with the rewritten output (badged as
"humanized v1") so the original is preserved for compare.

If `Auto-apply` is on, do the same automatically every time the assistant
finishes a turn that produced text content (not tool results). Update the
project: `humanize_settings.auto_apply = true` via PATCH.

### 10.3 As a chat tool (no UI work)

The agent already has a `humanize_text` tool registered in `core/tools.py`.
Users can just say "humanize this for LinkedIn" inside chat and the agent
will call the tool. The tool result lands in the existing tool-result
rendering (you already have that surface).

---

## 11. Streaming + Real-Time Patterns

### 11.1 Chat → Artifact appearance

The existing chat SDK's `onFinish` callback is where you wire artifact
refresh. Pseudo-code:

```ts
const chat = useChat({
  api: '/chat/agent',
  body: { conversation_id: project.conversation_id },
  onFinish: () => {
    queryClient.invalidateQueries({ queryKey: ['studio', 'project', project.id] });
  },
});
```

When the assistant finishes a turn that called `generate_pptx`, the chat
hook on the backend has already written `v{n+1}.pptx` and inserted the
`studio_artifacts` row. Your invalidation pulls it into the UI.

**Optimization (optional)**: read the existing `tool-result` events from
the stream — if any have `tool === 'generate_pptx'` (etc), you can
optimistically add a "rendering preview…" tile to the right pane before
the invalidation lands.

### 11.2 Style analysis polling

```ts
const { data: style } = useQuery({
  queryKey: ['studio', 'style', styleId],
  queryFn: () => studioApi.getStyle(styleId),
  refetchInterval: (data) => data?.style.status === 'analyzing' ? 2000 : false,
});
```

### 11.3 Humanize progress

Since humanize is a single POST that takes time, do client-side simulated
progress:

```tsx
const phases = ['Removing AI fingerprints…', 'Varying sentence rhythm…',
  'Injecting unexpected word choices…', 'Running detector ensemble…',
  'Verifying facts…', 'Scoring style fidelity…'];

const [phaseIdx, setPhaseIdx] = useState(0);
useEffect(() => {
  if (!loading) return;
  const t = setInterval(() => setPhaseIdx((i) => Math.min(i + 1, phases.length - 1)), 4000);
  return () => clearInterval(t);
}, [loading]);
```

When the response arrives, show the **real** `passes_summary` underneath.

---

## 12. Empty / Loading / Error States

For each major surface:

| Surface | Empty | Loading | Error |
|---|---|---|---|
| Projects grid | "No projects yet — start a new pitch deck or fund memo" + big New button | Skeleton cards x6 | "Couldn't load projects. Retry." inline |
| Project workspace | "No artifacts yet. Ask the assistant to build a deck for you." in right pane | Skeleton header + skeleton chat + skeleton slide reel | "Project not found" → bounce to /studio |
| Styles list | "Train your first voice clone" hero CTA | skeleton cards x4 | inline retry |
| Style detail (`status='analyzing'`) | "Cloning the voice — this takes about a minute" with spinner | – | If `status='failed'`: show `meta.error`, [ Retry analyze ] |
| Humanize playground | input is empty by default; output panel shows tooltip | spinner + animated phase label | red banner with `error` from API |

Always show a **toast** for non-fatal errors (rename failure, edit-save 500,
etc.) and do not lose user input.

---

## 13. Accessibility & Keyboard Shortcuts

- All buttons must have `aria-label`s.
- Slide reel: `← →` jumps slides. `Enter` starts edit mode on the active text frame. `Esc` exits edit mode.
- Workspace: `Cmd/Ctrl + S` saves edits. `Cmd/Ctrl + B` toggles preview/edit.
- Present mode: `←/→` next/prev, `Esc` exit, `F` fullscreen.
- Modals: focus trap + `Esc` to close.
- Streamed chat: live region with `aria-live="polite"` for screen readers.

---

## 14. QA Checklist

Before shipping, verify each of these end-to-end:

**Projects**
- [ ] Create PPTX project → workspace opens with empty right pane.
- [ ] Send "Build a 10-slide outlook on AI" → assistant generates → artifact v1 appears in the right pane.
- [ ] Send a follow-up "Add a slide about risks" → v2 appears, version dropdown updates.
- [ ] Click v1 in dropdown → preview shows v1, chat is unchanged.
- [ ] Download → bytes match the `studio_artifacts.size_bytes` value.
- [ ] Rename project (PATCH) → grid card title updates.
- [ ] Archive → disappears from default grid; appears with `?include_archived=true`.
- [ ] Delete → confirms, removes from grid, hits DELETE.

**Visual editor (PPTX)**
- [ ] Edit a text frame → op staged in EditOpsBuffer (count = 1).
- [ ] Add another edit → count = 2.
- [ ] Save → v(n+1) appears, EditOpsBuffer clears, preview re-renders.
- [ ] Discard → buffer clears without server call.
- [ ] Find-replace bar → pushes single `text_replace` op with `all:true`.
- [ ] Reorder slides via drag → emits `reorder_slides`.
- [ ] Delete slide → emits `delete_slide`, count drops by 1.

**Visual editor (DOCX)**
- [ ] Edit paragraph → `replace_paragraph` op.
- [ ] Append heading via toolbar → `append_heading` op.
- [ ] Find-replace works.

**Voice clone wizard**
- [ ] Step 1 creates draft style.
- [ ] Step 2 supports paste + file upload, removes samples.
- [ ] Analyze button disabled until min words met.
- [ ] Step 3 polling updates state, eventually flips to ready.
- [ ] Step 4 preview generates a sample in the cloned voice.
- [ ] Voice card shows quantitative + qualitative sections.
- [ ] System prompt is copyable.

**Voice attached to project**
- [ ] Create project with `style_profile_id` set.
- [ ] Send a chat → response should sound like the cloned voice.
- [ ] Switch the project to a different style → next response uses the new voice.

**Humanizer**
- [ ] Playground: paste obvious AI text → output less AI-like, AI-detection score drops noticeably.
- [ ] LinkedIn SEO mode: output has hook in first 210 chars + hashtags.
- [ ] Style profile applied: output matches the voice card.
- [ ] Score-only path returns scores without rewriting.
- [ ] Lost facts indicator works (try a paragraph with a unique number — should always survive).
- [ ] Run history list & detail loads.

**General**
- [ ] All endpoints respect JWT (sign out → /studio/* returns 401).
- [ ] No memory leaks when switching between projects rapidly.
- [ ] Mobile: workspace stacks vertically (chat on top, preview below).
- [ ] All file downloads have correct filename + Content-Type.

---

## Appendix A — Suggested File Structure

```
src/
  routes/
    studio/
      index.tsx                       # /studio
      projects/
        new.tsx                       # /studio/projects/new
        [id]/
          index.tsx                   # /studio/projects/:id
          present/[aid].tsx           # /studio/projects/:id/present/:aid
      styles/
        index.tsx
        new.tsx
        [id]/
          index.tsx
      humanize/
        index.tsx
  components/
    studio/
      ProjectCard.tsx
      NewProjectModal.tsx
      ProjectHeader.tsx
      ChatPane.tsx
      PreviewPane.tsx
      SlideReel.tsx
      SlideRenderer.tsx
      PageReel.tsx
      EditOpsBuffer.tsx
      VersionDropdown.tsx
      ModeToggle.tsx
      HumanizeBanner.tsx
      HumanizeChip.tsx
      StyleChip.tsx
      StyleWizard.tsx
      StyleCard.tsx
      VoiceCardView.tsx
      HumanizePlayground.tsx
      ScorePanel.tsx
  api/
    studio.ts                         # the typed client from §5
  hooks/
    useStudioProject.ts
    useStudioArtifacts.ts
    useStudioStyle.ts
    useEditOps.ts
    useHumanize.ts
```

---

## Appendix B — Things you DO NOT need to build

- A new generation endpoint (re-use `/chat/agent`).
- A document parser (frontend-side renderers handle pptx/docx).
- Server-rendered slide previews (we deliberately removed LibreOffice).
- A separate backend WebSocket for studio events (the chat SSE stream is enough; invalidate on `onFinish`).
- Manual style application logic — backend auto-injects when `style_profile_id` is set on a project.
- Manual artifact capture — backend chat-hook handles it for every doc-generating tool.

---

That's it. Build the shell, hook up the api client from §5, render the
artifact bytes with `pptxjs` + `docx-preview`, and you've got Content Studio.
