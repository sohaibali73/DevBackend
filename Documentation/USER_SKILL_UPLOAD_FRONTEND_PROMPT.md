# Frontend Cline Prompt — User-Uploaded Skills

> Copy-paste this whole document to your frontend Cline agent. It contains
> the full backend contract, all UI components, proxy routes, types,
> hooks, store, and wiring needed to ship the feature end-to-end.

---

## Goal

Let an authenticated user upload a Claude-style **Skill bundle** (`.zip` with
`SKILL.md`) **OR** author one inline (form fields). The skill is then visible
org-wide, editable/deletable by its uploader, and **immediately usable in
chats** via the existing skill picker — no chat-side code changes required.

---

## Backend contract (already shipped)

Base URL: `https://developer-potomaac.up.railway.app`. All endpoints require
`Authorization: Bearer <supabase_jwt>`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/skills?owned=me&category=&include_builtins=true` | List skills (merges portal + filesystem + DB-decorated) |
| `GET` | `/skills/{slug}` | Get one (returns `system_prompt` + `tools` for non-portal) |
| `POST` | `/skills/upload` | Upload bundle (multipart) — see §3 |
| `PATCH` | `/skills/{slug}` | Edit metadata / system prompt |
| `DELETE` | `/skills/{slug}` | Delete (owner or admin only) |
| `GET` | `/skills/{slug}/download` | Stream `<slug>.zip` |
| `POST` | `/skills/{slug}/duplicate` | Fork to a new slug owned by caller |
| `POST` | `/skills/{slug}/execute` | Already used by chat — unchanged |

### Skill object shape (response from `GET /skills`)

```ts
type SkillSource = "system" | "portal" | "upload" | "inline";
type SkillStorageKind = "portal" | "lightweight" | "bundle";

interface SkillDefinition {
  slug: string;
  name: string;
  description: string;
  category: string;            // e.g. "research" | "data" | "general" | ...
  tags: string[];
  max_tokens: number;
  enabled: boolean;
  supports_streaming: boolean;
  is_builtin: boolean;         // Anthropic-hosted (xlsx/pptx/pdf/docx)
  source: SkillSource;
  storage_kind: SkillStorageKind;
  created_by: string | null;   // user UUID for uploads, null otherwise
  created_at: string | null;   // ISO8601
  // GET /skills/{slug} also returns:
  system_prompt?: string;
  tools?: string[];
}
```

### Error envelope

All 4xx/5xx errors from the upload routes look like:

```json
{ "detail": { "code": "SLUG_TAKEN", "error": "Skill slug 'foo' is already in use (fs)." } }
```

Error codes you should map to friendly UI strings:

| Code | UI message |
|---|---|
| `INVALID_ZIP` | "That file isn't a valid `.zip`." |
| `EMPTY_UPLOAD` | "The bundle is empty." |
| `BUNDLE_TOO_LARGE` | "Bundle exceeds 25 MB compressed / 50 MB extracted." |
| `TOO_MANY_FILES` | "Bundle contains too many files (max 500)." |
| `UNSAFE_PATH` | "Bundle contains an unsafe path (`..`, absolute path, or symlink)." |
| `MISSING_SKILL_MD` | "Bundle must contain `SKILL.md` (or `skill.json` + `prompt.md`)." |
| `MISSING_NAME` | "Skill is missing a name." |
| `MISSING_DESCRIPTION` | "Skill is missing a description." |
| `MISSING_PROMPT` | "System prompt is required." |
| `BAD_SLUG` | "Slug must be kebab-case (3–64 chars, lowercase, start with a letter)." |
| `SLUG_TAKEN` | "That slug is already taken — pick another." |
| `INVALID_SKILL_JSON` | "`skill.json` is not valid JSON." |
| `FORBIDDEN` | "You don't have permission to modify this skill." |
| `NOT_FOUND` | "Skill not found." |
| `MATERIALIZE_FAILED`, `DB_INSERT_FAILED`, `DB_UPDATE_FAILED`, `DB_DELETE_FAILED` | "Server error — please try again." |

---

## Bundle formats

### Format A — Anthropic SKILL.md bundle (preferred for power users)

```
my-skill.zip
├── SKILL.md            ← required, with YAML frontmatter
├── references/         ← optional reference docs
├── scripts/            ← optional helpers (.py / .js)
├── assets/             ← optional images / templates
└── examples/           ← optional sample inputs
```

```markdown
---
name: my-skill
description: >
  Trigger description / system overview.
category: research
tags: [research, valuation]
---

# My Skill

System prompt body lives here.
```

Bundles containing `scripts/`, `assets/`, or `references/` are auto-routed
to the sandbox-mounted `ClaudeSkills/<slug>/` location server-side.

### Format B — Lightweight (form-only)

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
  "description": "...",
  "category": "research",
  "tags": [],
  "tools": [],
  "max_tokens": 8192,
  "timeout": 120,
  "enabled": true,
  "aliases": []
}
```

`prompt.md` is the system prompt body.

The frontend's "Author inline" form synthesizes a Format A 1-file zip
(SKILL.md only) on the client and posts it to `/skills/upload`.

---

## File-by-file frontend implementation

### 1. Install client deps

```bash
pnpm add jszip js-yaml
pnpm add -D @types/js-yaml
```

(`jszip` parses uploaded zips client-side for the live preview, and synthesizes
the inline-form zip. `js-yaml` parses SKILL.md frontmatter.)

---

### 2. `src/types/skills.ts` — extend the shared type

```ts
export type SkillSource = "system" | "portal" | "upload" | "inline";
export type SkillStorageKind = "portal" | "lightweight" | "bundle";

export interface SkillDefinition {
  slug: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  max_tokens: number;
  enabled: boolean;
  supports_streaming: boolean;
  is_builtin: boolean;
  source: SkillSource;
  storage_kind: SkillStorageKind;
  created_by: string | null;
  created_at: string | null;
  system_prompt?: string;
  tools?: string[];
}

export interface SkillUploadResponse {
  skill: SkillDefinition;
  warnings: string[];
  archived: boolean;
  storage_kind: SkillStorageKind;
  storage_path: string;
}

export interface SkillErrorPayload {
  detail: { code: string; error: string };
}

export const SKILL_ERROR_MESSAGES: Record<string, string> = {
  INVALID_ZIP: "That file isn't a valid .zip.",
  EMPTY_UPLOAD: "The bundle is empty.",
  BUNDLE_TOO_LARGE: "Bundle exceeds 25 MB compressed / 50 MB extracted.",
  TOO_MANY_FILES: "Bundle contains too many files (max 500).",
  UNSAFE_PATH: "Bundle contains an unsafe path.",
  MISSING_SKILL_MD: "Bundle must contain SKILL.md (or skill.json + prompt.md).",
  MISSING_NAME: "Skill is missing a name.",
  MISSING_DESCRIPTION: "Skill is missing a description.",
  MISSING_PROMPT: "System prompt is required.",
  BAD_SLUG:
    "Slug must be kebab-case (3–64 chars, lowercase, start with a letter).",
  SLUG_TAKEN: "That slug is already taken — pick another.",
  INVALID_SKILL_JSON: "skill.json is not valid JSON.",
  FORBIDDEN: "You don't have permission to modify this skill.",
  NOT_FOUND: "Skill not found.",
  MATERIALIZE_FAILED: "Server error — please try again.",
  DB_INSERT_FAILED: "Server error — please try again.",
  DB_UPDATE_FAILED: "Server error — please try again.",
  DB_DELETE_FAILED: "Server error — please try again.",
};

export function explainSkillError(payload: unknown): string {
  const code = (payload as SkillErrorPayload | undefined)?.detail?.code;
  const fallback = (payload as SkillErrorPayload | undefined)?.detail?.error;
  return (code && SKILL_ERROR_MESSAGES[code]) || fallback || "Unknown error";
}

export const KEBAB_SLUG_RE = /^[a-z][a-z0-9-]{2,63}$/;

export const SKILL_CATEGORIES = [
  { value: "general", label: "General" },
  { value: "research", label: "Research" },
  { value: "document", label: "Document" },
  { value: "presentation", label: "Presentation" },
  { value: "data", label: "Data" },
  { value: "ui", label: "UI" },
  { value: "backtest", label: "Backtest" },
  { value: "market_analysis", label: "Market Analysis" },
  { value: "quant", label: "Quant" },
  { value: "financial_modeling", label: "Financial Modeling" },
  { value: "afl", label: "AFL" },
  { value: "code", label: "Code" },
] as const;
```

---

### 3. Next.js proxy routes

Mirror your existing `app/api/skills/...` proxy pattern. All 5 of these
new routes simply forward `Authorization` and the request body to the
backend.

#### `app/api/skills/upload/route.ts`

```ts
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL || "https://developer-potomaac.up.railway.app";

export async function POST(req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth) return NextResponse.json({ detail: "unauthorized" }, { status: 401 });

  const formData = await req.formData();

  const res = await fetch(`${BACKEND}/skills/upload`, {
    method: "POST",
    headers: { Authorization: auth },
    body: formData,
  });

  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
  });
}

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
```

#### `app/api/skills/[slug]/route.ts` (extend existing GET; add PATCH + DELETE)

```ts
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL || "https://developer-potomaac.up.railway.app";

async function proxy(method: string, slug: string, req: NextRequest) {
  const auth = req.headers.get("authorization");
  if (!auth) return NextResponse.json({ detail: "unauthorized" }, { status: 401 });

  const init: RequestInit = {
    method,
    headers: { Authorization: auth, "Content-Type": "application/json" },
  };
  if (method === "PATCH") init.body = await req.text();

  const res = await fetch(`${BACKEND}/skills/${slug}`, init);
  const text = await res.text();
  return new NextResponse(text || null, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("content-type") || "application/json" },
  });
}

export async function GET(req: NextRequest, { params }: { params: { slug: string } }) {
  return proxy("GET", params.slug, req);
}
export async function PATCH(req: NextRequest, { params }: { params: { slug: string } }) {
  return proxy("PATCH", params.slug, req);
}
export async function DELETE(req: NextRequest, { params }: { params: { slug: string } }) {
  return proxy("DELETE", params.slug, req);
}
```

#### `app/api/skills/[slug]/download/route.ts`

```ts
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL || "https://developer-potomaac.up.railway.app";

export async function GET(req: NextRequest, { params }: { params: { slug: string } }) {
  const auth = req.headers.get("authorization");
  if (!auth) return NextResponse.json({ detail: "unauthorized" }, { status: 401 });

  const res = await fetch(`${BACKEND}/skills/${params.slug}/download`, {
    headers: { Authorization: auth },
  });
  return new NextResponse(res.body, {
    status: res.status,
    headers: {
      "Content-Type": "application/zip",
      "Content-Disposition": res.headers.get("content-disposition") || `attachment; filename="${params.slug}.zip"`,
    },
  });
}

export const runtime = "nodejs";
```

#### `app/api/skills/[slug]/duplicate/route.ts`

```ts
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL || "https://developer-potomaac.up.railway.app";

export async function POST(req: NextRequest, { params }: { params: { slug: string } }) {
  const auth = req.headers.get("authorization");
  if (!auth) return NextResponse.json({ detail: "unauthorized" }, { status: 401 });
  const body = await req.text();

  const res = await fetch(`${BACKEND}/skills/${params.slug}/duplicate`, {
    method: "POST",
    headers: { Authorization: auth, "Content-Type": "application/json" },
    body,
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
```

#### `app/api/skills/route.ts` (extend existing — pass `owned` through)

If the existing GET handler doesn't already proxy query params, ensure it does:

```ts
const url = new URL(req.url);
const qs = url.searchParams.toString();
const res = await fetch(`${BACKEND}/skills${qs ? `?${qs}` : ""}`, { headers: { Authorization: auth } });
```

---

### 4. Skills client SDK — `src/lib/skills/api.ts`

```ts
import type { SkillDefinition, SkillUploadResponse } from "@/types/skills";

async function authHeaders(): Promise<HeadersInit> {
  // Replace with your actual token-getter (Supabase session / store)
  const { useAuthStore } = await import("@/stores/auth");
  const token = useAuthStore.getState().accessToken;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function listSkills(opts?: {
  owned?: "me";
  category?: string;
  include_builtins?: boolean;
}): Promise<{ skills: SkillDefinition[]; count: number }> {
  const qs = new URLSearchParams();
  if (opts?.owned) qs.set("owned", opts.owned);
  if (opts?.category) qs.set("category", opts.category);
  if (opts?.include_builtins !== undefined) qs.set("include_builtins", String(opts.include_builtins));
  const res = await fetch(`/api/skills${qs.toString() ? `?${qs}` : ""}`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw await res.json().catch(() => ({}));
  return res.json();
}

export async function getSkill(slug: string): Promise<SkillDefinition> {
  const res = await fetch(`/api/skills/${slug}`, { headers: await authHeaders() });
  if (!res.ok) throw await res.json().catch(() => ({}));
  return res.json();
}

export async function uploadSkill(
  zip: Blob | File,
  metadata?: Record<string, unknown>,
): Promise<SkillUploadResponse> {
  const fd = new FormData();
  fd.append("file", zip, (zip as File).name || "skill.zip");
  if (metadata) fd.append("metadata", JSON.stringify(metadata));

  const res = await fetch(`/api/skills/upload`, {
    method: "POST",
    headers: await authHeaders(),
    body: fd,
  });
  if (!res.ok) throw await res.json().catch(() => ({}));
  return res.json();
}

export async function patchSkill(
  slug: string,
  patch: Partial<{
    name: string;
    description: string;
    category: string;
    tags: string[];
    enabled: boolean;
    system_prompt: string;
  }>,
): Promise<{ skill: SkillDefinition }> {
  const res = await fetch(`/api/skills/${slug}`, {
    method: "PATCH",
    headers: { ...(await authHeaders()), "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw await res.json().catch(() => ({}));
  return res.json();
}

export async function deleteSkill(slug: string): Promise<void> {
  const res = await fetch(`/api/skills/${slug}`, {
    method: "DELETE",
    headers: await authHeaders(),
  });
  if (!res.ok && res.status !== 204) throw await res.json().catch(() => ({}));
}

export async function duplicateSkill(
  slug: string,
  body: { new_slug?: string; new_name?: string } = {},
): Promise<{ skill: SkillDefinition }> {
  const res = await fetch(`/api/skills/${slug}/duplicate`, {
    method: "POST",
    headers: { ...(await authHeaders()), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await res.json().catch(() => ({}));
  return res.json();
}

export function downloadSkillURL(slug: string): string {
  return `/api/skills/${slug}/download`;
}
```

---

### 5. Bundle parser — `src/lib/skills/parseBundle.ts`

Parses an uploaded `.zip` client-side for live preview and synthesizes
SKILL.md zips for inline mode.

```ts
import JSZip from "jszip";
import yaml from "js-yaml";
import { KEBAB_SLUG_RE } from "@/types/skills";

export interface ParsedFrontmatter {
  name?: string;
  description?: string;
  slug?: string;
  category?: string;
  tags?: string[];
  [k: string]: unknown;
}

export interface ParsedBundlePreview {
  ok: boolean;
  errors: string[];
  warnings: string[];
  frontmatter: ParsedFrontmatter;
  body: string;
  fileTree: { path: string; size: number }[];
  storageKindGuess: "lightweight" | "bundle";
}

const ALLOWED_EXTS = new Set([
  ".md", ".txt", ".json", ".yaml", ".yml",
  ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs",
  ".csv", ".tsv",
  ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
  ".pdf",
  ".html", ".htm", ".css", ".xml",
]);

const FRONTMATTER_RE = /^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/;

export async function parseBundle(file: File): Promise<ParsedBundlePreview> {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (file.size > 25 * 1024 * 1024) {
    return { ok: false, errors: ["Bundle exceeds 25 MB."], warnings: [], frontmatter: {}, body: "", fileTree: [], storageKindGuess: "lightweight" };
  }

  let zip: JSZip;
  try {
    zip = await JSZip.loadAsync(file);
  } catch {
    return { ok: false, errors: ["Not a valid .zip."], warnings: [], frontmatter: {}, body: "", fileTree: [], storageKindGuess: "lightweight" };
  }

  // Strip common single-folder prefix
  const allPaths = Object.keys(zip.files).filter((p) => !zip.files[p].dir);
  const tops = new Set(allPaths.map((p) => p.split("/")[0]));
  const rootFiles = allPaths.filter((p) => !p.includes("/"));
  const stripPrefix =
    tops.size === 1 && rootFiles.length === 0 ? `${[...tops][0]}/` : "";

  const fileTree: { path: string; size: number }[] = [];
  let skillMdRaw: string | null = null;
  let skillJsonRaw: string | null = null;
  let promptMdRaw: string | null = null;
  let totalUncompressed = 0;

  for (const path of allPaths) {
    const norm = stripPrefix && path.startsWith(stripPrefix) ? path.slice(stripPrefix.length) : path;
    const ext = (norm.match(/\.[^./]+$/)?.[0] || "").toLowerCase();
    if (ext && !ALLOWED_EXTS.has(ext)) {
      warnings.push(`Skipped: ${norm}`);
      continue;
    }
    const entry = zip.files[path];
    const data = await entry.async("uint8array");
    totalUncompressed += data.byteLength;
    if (totalUncompressed > 50 * 1024 * 1024) {
      errors.push("Bundle exceeds 50 MB extracted.");
      break;
    }
    fileTree.push({ path: norm, size: data.byteLength });
    const text = new TextDecoder().decode(data);
    if (norm === "SKILL.md") skillMdRaw = text;
    else if (norm === "skill.json") skillJsonRaw = text;
    else if (norm === "prompt.md") promptMdRaw = text;
  }

  let frontmatter: ParsedFrontmatter = {};
  let body = "";

  if (skillMdRaw) {
    const m = skillMdRaw.match(FRONTMATTER_RE);
    if (m) {
      try {
        frontmatter = (yaml.load(m[1]) as ParsedFrontmatter) || {};
      } catch (e) {
        warnings.push("YAML frontmatter could not be parsed.");
      }
      body = m[2];
    } else {
      body = skillMdRaw;
      warnings.push("SKILL.md has no YAML frontmatter.");
    }
  } else if (skillJsonRaw) {
    try {
      frontmatter = JSON.parse(skillJsonRaw) as ParsedFrontmatter;
    } catch {
      errors.push("skill.json is not valid JSON.");
    }
    if (promptMdRaw) body = promptMdRaw;
  } else {
    errors.push("Missing SKILL.md (or skill.json + prompt.md) at root.");
  }

  if (!frontmatter.name) errors.push("name is required");
  if (!frontmatter.description) errors.push("description is required");
  if (frontmatter.slug && !KEBAB_SLUG_RE.test(String(frontmatter.slug))) {
    errors.push("slug must be kebab-case (3–64 chars).");
  }

  const hasNested = fileTree.some((f) => f.path.includes("/"));
  const storageKindGuess: "lightweight" | "bundle" = hasNested ? "bundle" : "lightweight";

  return {
    ok: errors.length === 0,
    errors,
    warnings,
    frontmatter,
    body,
    fileTree,
    storageKindGuess,
  };
}

/** Build a 1-file SKILL.md bundle from inline form fields. Returns a Blob ready to POST. */
export async function buildInlineBundle(opts: {
  name: string;
  description: string;
  systemPrompt: string;
  slug?: string;
  category?: string;
  tags?: string[];
}): Promise<Blob> {
  const slug = (opts.slug || slugify(opts.name)).toLowerCase();
  const frontmatter = [
    "---",
    `name: ${slug}`,
    "description: >",
    ...wrapBlock(opts.description, 2),
    `category: ${opts.category || "general"}`,
    opts.tags?.length ? `tags: [${opts.tags.join(", ")}]` : null,
    "---",
    "",
    `# ${opts.name}`,
    "",
    opts.systemPrompt.trim(),
    "",
  ]
    .filter((l) => l !== null)
    .join("\n");

  const zip = new JSZip();
  zip.file("SKILL.md", frontmatter);
  return zip.generateAsync({ type: "blob", compression: "DEFLATE" });
}

function slugify(name: string): string {
  let s = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  if (!s) s = "skill";
  if (!/^[a-z]/.test(s)) s = "s-" + s;
  return s.slice(0, 64);
}

function* wrapBlock(text: string, indent = 2, width = 80): Generator<string> {
  const pad = " ".repeat(indent);
  const words = text.split(/\s+/);
  let line: string[] = [];
  let len = 0;
  for (const w of words) {
    if (len + w.length + 1 > width && line.length) {
      yield pad + line.join(" ");
      line = [w];
      len = w.length;
    } else {
      line.push(w);
      len += w.length + 1;
    }
  }
  if (line.length) yield pad + line.join(" ");
}
```

---

### 6. Cache invalidation — `src/stores/skills.ts`

Fixes the existing `ChatSkillSelector.tsx` staleness bug. Components read
`version` and re-fetch when it bumps.

```ts
import { create } from "zustand";

interface SkillsState {
  version: number;
  bumpVersion: () => void;
}

export const useSkillsStore = create<SkillsState>((set) => ({
  version: 0,
  bumpVersion: () => set((s) => ({ version: s.version + 1 })),
}));
```

Use it from any component that lists skills:

```ts
const version = useSkillsStore((s) => s.version);
useEffect(() => { fetchSkills(); }, [version]);
```

---

### 7. Patch `ChatSkillSelector.tsx`

Find this pattern (or similar — module-level "fetched once" cache):

```ts
let fetched = false;
let cached: SkillDefinition[] = [];
```

Replace with:

```ts
import { useSkillsStore } from "@/stores/skills";
// ...inside component:
const version = useSkillsStore((s) => s.version);
const [skills, setSkills] = useState<SkillDefinition[]>([]);
const [loading, setLoading] = useState(false);

useEffect(() => {
  let cancelled = false;
  setLoading(true);
  listSkills({ include_builtins: true })
    .then((r) => { if (!cancelled) setSkills(r.skills); })
    .finally(() => { if (!cancelled) setLoading(false); });
  return () => { cancelled = true; };
}, [version]);
```

No other chat changes needed — the selector already passes `skill_slug` to
`/api/chat`, which routes it through `/chat/agent`, which resolves it via
the backend's loader (now refreshed on every upload).

---

### 8. `CreateSkillModal.tsx` — the main UI

A two-tab modal: **Upload bundle** + **Author inline**. Drop into your
existing dialog system (shadcn `Dialog`, Radix, etc.).

```tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, Upload, FileText, AlertTriangle, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import { uploadSkill } from "@/lib/skills/api";
import { parseBundle, buildInlineBundle, ParsedBundlePreview } from "@/lib/skills/parseBundle";
import { explainSkillError, KEBAB_SLUG_RE, SKILL_CATEGORIES } from "@/types/skills";
import { useSkillsStore } from "@/stores/skills";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (slug: string) => void;
}

export function CreateSkillModal({ open, onOpenChange, onCreated }: Props) {
  const [tab, setTab] = useState<"upload" | "inline">("upload");
  const [submitting, setSubmitting] = useState(false);
  const bumpVersion = useSkillsStore((s) => s.bumpVersion);

  // Upload tab state
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ParsedBundlePreview | null>(null);
  const [overrideSlug, setOverrideSlug] = useState("");
  const [overrideCategory, setOverrideCategory] = useState("");

  // Inline tab state
  const [iName, setIName] = useState("");
  const [iSlug, setISlug] = useState("");
  const [iSlugTouched, setISlugTouched] = useState(false);
  const [iDescription, setIDescription] = useState("");
  const [iCategory, setICategory] = useState("general");
  const [iTagsRaw, setITagsRaw] = useState("");
  const [iPrompt, setIPrompt] = useState("");

  const dropRef = useRef<HTMLDivElement>(null);

  // Auto-derive slug from name on inline tab
  useEffect(() => {
    if (!iSlugTouched) {
      setISlug(slugify(iName));
    }
  }, [iName, iSlugTouched]);

  // Parse the uploaded zip whenever file changes
  useEffect(() => {
    let cancelled = false;
    if (!file) {
      setPreview(null);
      return;
    }
    parseBundle(file).then((p) => { if (!cancelled) setPreview(p); });
    return () => { cancelled = true; };
  }, [file]);

  function reset() {
    setFile(null); setPreview(null); setOverrideSlug(""); setOverrideCategory("");
    setIName(""); setISlug(""); setISlugTouched(false); setIDescription("");
    setICategory("general"); setITagsRaw(""); setIPrompt("");
    setSubmitting(false); setTab("upload");
  }

  async function handleUploadSubmit() {
    if (!file || !preview?.ok) return;
    setSubmitting(true);
    try {
      const metadata: Record<string, unknown> = {};
      if (overrideSlug) metadata.slug = overrideSlug;
      if (overrideCategory) metadata.category = overrideCategory;
      const res = await uploadSkill(file, metadata);
      toast.success(`Uploaded "${res.skill.name}"`);
      if (res.warnings.length) toast.message(`${res.warnings.length} warning(s)`, { description: res.warnings.join("\n") });
      bumpVersion();
      onCreated?.(res.skill.slug);
      onOpenChange(false);
      reset();
    } catch (err) {
      toast.error(explainSkillError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleInlineSubmit() {
    if (!iName.trim() || !iDescription.trim() || !iPrompt.trim()) return;
    if (!KEBAB_SLUG_RE.test(iSlug)) {
      toast.error("Slug must be kebab-case (3–64 chars, lowercase, start with a letter).");
      return;
    }
    setSubmitting(true);
    try {
      const tags = iTagsRaw.split(",").map((t) => t.trim()).filter(Boolean);
      const blob = await buildInlineBundle({
        name: iName.trim(),
        description: iDescription.trim(),
        systemPrompt: iPrompt.trim(),
        slug: iSlug,
        category: iCategory,
        tags,
      });
      const file = new File([blob], `${iSlug}.zip`, { type: "application/zip" });
      const res = await uploadSkill(file, { mode: "inline", slug: iSlug, name: iName, description: iDescription, category: iCategory, tags });
      toast.success(`Created "${res.skill.name}"`);
      bumpVersion();
      onCreated?.(res.skill.slug);
      onOpenChange(false);
      reset();
    } catch (err) {
      toast.error(explainSkillError(err));
    } finally {
      setSubmitting(false);
    }
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f && f.name.toLowerCase().endsWith(".zip")) setFile(f);
    else toast.error("Drop a .zip file.");
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>New skill</DialogTitle>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(v) => setTab(v as "upload" | "inline")}>
          <TabsList className="grid grid-cols-2 w-full">
            <TabsTrigger value="upload">Upload bundle</TabsTrigger>
            <TabsTrigger value="inline">Author inline</TabsTrigger>
          </TabsList>

          <TabsContent value="upload" className="space-y-4 pt-4">
            <div
              ref={dropRef}
              onDragOver={(e) => e.preventDefault()}
              onDrop={onDrop}
              className="border-2 border-dashed rounded-lg p-8 text-center hover:bg-accent/40 transition-colors cursor-pointer"
              onClick={() => document.getElementById("skill-zip-input")?.click()}
            >
              <Upload className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
              <p className="text-sm">
                {file ? <strong>{file.name}</strong> : "Drop a .zip skill bundle, or click to browse"}
              </p>
              <input
                id="skill-zip-input"
                type="file"
                accept=".zip,application/zip"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </div>

            {preview && (
              <div className="space-y-3 text-sm">
                <div className="flex items-center gap-2">
                  {preview.ok ? (
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 text-yellow-600" />
                  )}
                  <span className="font-medium">
                    {preview.ok ? "Bundle looks good" : "Bundle has issues"}
                  </span>
                  <Badge variant="secondary">{preview.storageKindGuess}</Badge>
                </div>
                {preview.errors.length > 0 && (
                  <ul className="text-red-600 list-disc list-inside">
                    {preview.errors.map((e) => <li key={e}>{e}</li>)}
                  </ul>
                )}
                {preview.warnings.length > 0 && (
                  <ul className="text-yellow-600 list-disc list-inside">
                    {preview.warnings.map((w) => <li key={w}>{w}</li>)}
                  </ul>
                )}
                {preview.frontmatter.name && (
                  <div className="rounded border bg-muted/40 p-3 space-y-1">
                    <div><span className="text-muted-foreground">Name:</span> <strong>{String(preview.frontmatter.name)}</strong></div>
                    <div><span className="text-muted-foreground">Slug:</span> {String(preview.frontmatter.slug || preview.frontmatter.name)}</div>
                    <div><span className="text-muted-foreground">Category:</span> {String(preview.frontmatter.category || "general")}</div>
                    {preview.frontmatter.description && (
                      <div className="text-muted-foreground line-clamp-2">{String(preview.frontmatter.description)}</div>
                    )}
                  </div>
                )}
                <details className="text-xs">
                  <summary className="cursor-pointer text-muted-foreground">{preview.fileTree.length} files</summary>
                  <ul className="mt-1 max-h-40 overflow-auto font-mono">
                    {preview.fileTree.map((f) => (
                      <li key={f.path} className="flex justify-between gap-4">
                        <span>{f.path}</span>
                        <span className="text-muted-foreground">{(f.size / 1024).toFixed(1)} KB</span>
                      </li>
                    ))}
                  </ul>
                </details>

                <div className="grid grid-cols-2 gap-3 pt-2">
                  <div>
                    <Label htmlFor="ovr-slug">Override slug (optional)</Label>
                    <Input id="ovr-slug" value={overrideSlug} onChange={(e) => setOverrideSlug(e.target.value)} placeholder={String(preview.frontmatter.slug || "")} />
                  </div>
                  <div>
                    <Label htmlFor="ovr-cat">Override category</Label>
                    <select id="ovr-cat" value={overrideCategory} onChange={(e) => setOverrideCategory(e.target.value)}
                      className="w-full rounded border bg-background px-3 py-2 text-sm">
                      <option value="">— keep bundle's —</option>
                      {SKILL_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent value="inline" className="space-y-3 pt-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="i-name">Name</Label>
                <Input id="i-name" value={iName} onChange={(e) => setIName(e.target.value)} placeholder="My Skill" />
              </div>
              <div>
                <Label htmlFor="i-slug">Slug</Label>
                <Input id="i-slug" value={iSlug} onChange={(e) => { setISlugTouched(true); setISlug(e.target.value); }} placeholder="my-skill" />
              </div>
            </div>

            <div>
              <Label htmlFor="i-desc">Description (also used as trigger hint)</Label>
              <Textarea id="i-desc" rows={3} value={iDescription} onChange={(e) => setIDescription(e.target.value)} placeholder="One-paragraph description of when to use this skill." />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="i-cat">Category</Label>
                <select id="i-cat" value={iCategory} onChange={(e) => setICategory(e.target.value)}
                  className="w-full rounded border bg-background px-3 py-2 text-sm">
                  {SKILL_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <Label htmlFor="i-tags">Tags (comma-separated)</Label>
                <Input id="i-tags" value={iTagsRaw} onChange={(e) => setITagsRaw(e.target.value)} placeholder="research, valuation" />
              </div>
            </div>

            <div>
              <Label htmlFor="i-prompt">System prompt</Label>
              <Textarea id="i-prompt" rows={10} value={iPrompt} onChange={(e) => setIPrompt(e.target.value)}
                placeholder="You are a senior research analyst. Always cite sources..." />
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>Cancel</Button>
          {tab === "upload" ? (
            <Button onClick={handleUploadSubmit} disabled={submitting || !file || !preview?.ok}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Upload skill
            </Button>
          ) : (
            <Button onClick={handleInlineSubmit} disabled={submitting || !iName.trim() || !iDescription.trim() || !iPrompt.trim()}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create skill
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function slugify(name: string): string {
  let s = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  if (!s) return "";
  if (!/^[a-z]/.test(s)) s = "s-" + s;
  return s.slice(0, 64);
}
```

---

### 9. Skill card — `SkillCard.tsx` (used on the Skills explorer page)

```tsx
"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreHorizontal, Download, Copy, Pencil, Trash2 } from "lucide-react";
import type { SkillDefinition } from "@/types/skills";
import { deleteSkill, downloadSkillURL, duplicateSkill } from "@/lib/skills/api";
import { useSkillsStore } from "@/stores/skills";
import { useAuthStore } from "@/stores/auth";
import { toast } from "sonner";

const SOURCE_BADGE: Record<string, { label: string; variant: "default" | "secondary" | "outline" }> = {
  system:   { label: "Built-in", variant: "secondary" },
  portal:   { label: "Anthropic", variant: "default" },
  upload:   { label: "Custom",   variant: "outline" },
  inline:   { label: "Inline",   variant: "outline" },
};

export function SkillCard({ skill, onEdit }: { skill: SkillDefinition; onEdit: (s: SkillDefinition) => void }) {
  const bumpVersion = useSkillsStore((s) => s.bumpVersion);
  const userId = useAuthStore((s) => s.user?.id);
  const isAdmin = useAuthStore((s) => s.user?.is_admin);

  const isMine = !!userId && skill.created_by === userId;
  const canModify = (isMine || isAdmin) && skill.source !== "system" && skill.source !== "portal";
  const badge = SOURCE_BADGE[skill.source] ?? SOURCE_BADGE.system;

  async function handleDelete() {
    if (!confirm(`Delete "${skill.name}"? This cannot be undone.`)) return;
    try {
      await deleteSkill(skill.slug);
      toast.success(`Deleted ${skill.name}`);
      bumpVersion();
    } catch (e: any) {
      toast.error(e?.detail?.error || "Delete failed");
    }
  }

  async function handleDuplicate() {
    try {
      const r = await duplicateSkill(skill.slug);
      toast.success(`Duplicated as ${r.skill.slug}`);
      bumpVersion();
    } catch (e: any) {
      toast.error(e?.detail?.error || "Duplicate failed");
    }
  }

  return (
    <div className="rounded-xl border bg-card p-4 flex flex-col gap-3 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold truncate">{skill.name}</h3>
          <p className="text-xs text-muted-foreground font-mono truncate">{skill.slug}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Badge variant={badge.variant}>{badge.label}</Badge>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="icon" variant="ghost" className="h-7 w-7"><MoreHorizontal className="h-4 w-4" /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem asChild>
                <a href={downloadSkillURL(skill.slug)} download><Download className="mr-2 h-4 w-4" />Download</a>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleDuplicate}><Copy className="mr-2 h-4 w-4" />Duplicate</DropdownMenuItem>
              {canModify && (
                <>
                  <DropdownMenuItem onClick={() => onEdit(skill)}><Pencil className="mr-2 h-4 w-4" />Edit</DropdownMenuItem>
                  <DropdownMenuItem onClick={handleDelete} className="text-red-600"><Trash2 className="mr-2 h-4 w-4" />Delete</DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <p className="text-sm text-muted-foreground line-clamp-3">{skill.description}</p>
      <div className="flex flex-wrap gap-1 mt-auto">
        <Badge variant="outline" className="text-xs">{skill.category}</Badge>
        {skill.tags.slice(0, 3).map((t) => <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>)}
      </div>
    </div>
  );
}
```

---

### 10. Edit modal — `EditSkillModal.tsx`

```tsx
"use client";

import { useEffect, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { getSkill, patchSkill } from "@/lib/skills/api";
import { explainSkillError, SKILL_CATEGORIES, SkillDefinition } from "@/types/skills";
import { useSkillsStore } from "@/stores/skills";

interface Props {
  skill: SkillDefinition | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditSkillModal({ skill, open, onOpenChange }: Props) {
  const bumpVersion = useSkillsStore((s) => s.bumpVersion);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("general");
  const [tagsRaw, setTagsRaw] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [isLightweight, setIsLightweight] = useState(false);

  useEffect(() => {
    if (!open || !skill) return;
    setLoading(true);
    getSkill(skill.slug)
      .then((full) => {
        setName(full.name);
        setDescription(full.description);
        setCategory(full.category);
        setTagsRaw((full.tags || []).join(", "));
        setEnabled(full.enabled);
        setSystemPrompt(full.system_prompt || "");
        setIsLightweight(full.storage_kind === "lightweight");
      })
      .catch((e) => toast.error(explainSkillError(e)))
      .finally(() => setLoading(false));
  }, [open, skill]);

  async function handleSave() {
    if (!skill) return;
    setSubmitting(true);
    try {
      const tags = tagsRaw.split(",").map((t) => t.trim()).filter(Boolean);
      await patchSkill(skill.slug, {
        name, description, category, tags, enabled,
        ...(isLightweight ? { system_prompt: systemPrompt } : {}),
      });
      toast.success("Saved");
      bumpVersion();
      onOpenChange(false);
    } catch (e) {
      toast.error(explainSkillError(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit skill — {skill?.name}</DialogTitle>
        </DialogHeader>
        {loading ? (
          <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>
        ) : (
          <div className="space-y-3">
            <div>
              <Label>Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label>Description</Label>
              <Textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Category</Label>
                <select value={category} onChange={(e) => setCategory(e.target.value)}
                  className="w-full rounded border bg-background px-3 py-2 text-sm">
                  {SKILL_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <Label>Tags</Label>
                <Input value={tagsRaw} onChange={(e) => setTagsRaw(e.target.value)} />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={enabled} onCheckedChange={setEnabled} />
              <Label>Enabled</Label>
            </div>
            {isLightweight && (
              <div>
                <Label>System prompt</Label>
                <Textarea rows={10} value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} />
              </div>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>Cancel</Button>
          <Button onClick={handleSave} disabled={submitting || loading}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

---

### 11. Wire it into `app/(protected)/skills/page.tsx`

Add a **+ New Skill** button, a **My Skills** filter, and the two modals.
Sketch (merge with your existing layout):

```tsx
"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Plus } from "lucide-react";

import { listSkills } from "@/lib/skills/api";
import type { SkillDefinition } from "@/types/skills";
import { useSkillsStore } from "@/stores/skills";
import { SkillCard } from "@/components/skills/SkillCard";
import { CreateSkillModal } from "@/components/skills/CreateSkillModal";
import { EditSkillModal } from "@/components/skills/EditSkillModal";

export default function SkillsPage() {
  const version = useSkillsStore((s) => s.version);
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<"all" | "mine">("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<SkillDefinition | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listSkills(filter === "mine" ? { owned: "me" } : {})
      .then((r) => { if (!cancelled) setSkills(r.skills); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [version, filter]);

  return (
    <div className="container py-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Skills</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> New skill
        </Button>
      </div>

      <Tabs value={filter} onValueChange={(v) => setFilter(v as "all" | "mine")}>
        <TabsList>
          <TabsTrigger value="all">All skills</TabsTrigger>
          <TabsTrigger value="mine">My skills</TabsTrigger>
        </TabsList>
        <TabsContent value={filter}>
          {loading ? (
            <p className="text-muted-foreground">Loading…</p>
          ) : skills.length === 0 ? (
            <p className="text-muted-foreground">No skills yet.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {skills.map((s) => (
                <SkillCard key={s.slug} skill={s} onEdit={setEditing} />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <CreateSkillModal open={createOpen} onOpenChange={setCreateOpen} />
      <EditSkillModal skill={editing} open={!!editing} onOpenChange={(v) => !v && setEditing(null)} />
    </div>
  );
}
```

---

## Smoke test for the frontend agent

1. Sign in.
2. Go to **Skills**, click **+ New skill**, switch to **Author inline**.
3. Enter:
   - Name: `Hello Skill`
   - Description: `Demo skill that says hello.`
   - System prompt: `You are a friendly greeter. Always start replies with "Hello!".`
4. Submit. Toast says "Created Hello Skill".
5. Open a chat, click the skill picker — `hello-skill` should appear immediately (no refresh).
6. Pick it, send "who are you?" — response should start with "Hello!".
7. Back on Skills page → **My skills** tab → card appears with **Custom** badge → menu → **Edit** → change description → save → list updates.
8. Menu → **Duplicate** → new card `hello-skill-copy` appears.
9. Menu → **Delete** on the copy → it disappears.
10. Menu → **Download** → browser downloads `hello-skill.zip`.

If all 10 steps pass, you're done.

---

## What you do NOT need to do

- No changes to chat request flow — `skill_slug` already routes to `/chat/agent`.
- No changes to the skills exec endpoint.
- No changes to the auth flow.
- No additional environment variables (`BACKEND_URL` already exists).
- No Supabase Storage client work — backend handles archiving.
