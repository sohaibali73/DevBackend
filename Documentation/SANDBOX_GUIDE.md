# Sandbox System — Complete Guide

> **Audience:** Backend developers + Next.js frontend developers building Generative UI chatbot apps.  
> **Last updated:** v3 — auto-install, file downloads, plotly capture, relaxed security (os/sys/shutil safe proxies).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [How State Persists](#2-how-state-persists)
3. [Complete API Reference](#3-complete-api-reference)
4. [Wiring in a Next.js Generative UI Chatbot](#4-wiring-in-a-nextjs-generative-ui-chatbot)
5. [Rendering Artifacts on the Frontend](#5-rendering-artifacts-on-the-frontend)
6. [Session Management Across Turns](#6-session-management-across-turns)
7. [Supabase — What to Paste](#7-supabase--what-to-paste)
8. [What's New in v3](#8-whats-new-in-v3)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js App (Generative UI chatbot)                        │
│                                                             │
│  useChat() → message stream → <ArtifactRenderer />         │
└──────────────────────┬──────────────────────────────────────┘
                       │  POST /api/chat  (Vercel AI SDK)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Next.js API Route  (server-side)                           │
│                                                             │
│  streamUI / streamText  ─────────────── AI Tool:           │
│                                         executeSandbox()   │
└──────────────────────────────────────┬──────────────────────┘
                                        │  POST /sandbox/execute
                                        │  (carries session_id)
                                        ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Backend                                            │
│                                                             │
│  SandboxManager                                             │
│  ├── PythonSandbox  → exec() + stdout capture + AST check  │
│  │   └── SQLite: load/save namespace (session_id)          │
│  ├── NodeSandbox    → Node.js subprocess                    │
│  └── ReactSandbox   → CDN Babel HTML wrapper (no subprocess)│
│                                                             │
│  ~/ .sandbox/                                               │
│  ├── sandbox.db          ← SQLite (sessions, artifacts…)   │
│  ├── python_venv/        ← user-installed Python packages   │
│  ├── node_packages/      ← user-installed JS packages       │
│  └── node_cache/         ← npm cache (persistent)          │
└─────────────────────────────────────────────────────────────┘
```

### What each sandbox returns

| `language` | How it runs | What comes back |
|---|---|---|
| `python` | `exec()` in restricted globals | `output` (stdout) + optional `artifacts` (images, HTML, plotly charts, files) |
| `javascript` | Node.js subprocess | `output` (stdout / console.log) |
| `react` | Inline HTML wrap — **no subprocess** | `artifacts[0].data` = full HTML page (iframe it) |

---

## 2. How State Persists

### Python session namespaces

Every Python execution accepts a `session_id`. Variables created in one turn are available in the next.

```
Turn 1:  POST /sandbox/execute  { code: "x = 42", session_id: "abc" }
         ← success, x saved to SQLite

Turn 2:  POST /sandbox/execute  { code: "print(x * 2)", session_id: "abc" }
         ← output: "84"
```

The SQLite database lives at `~/.sandbox/sandbox.db` (or `$SANDBOX_DATA_DIR/sandbox.db`).  
Sessions expire after **7 days** of inactivity.

### Node modules cache

npm packages are cached at `~/.sandbox/node_cache/<md5_of_deps>/`.  
After the first install they load instantly from disk — survives server restarts.

### User-installed packages

`POST /sandbox/packages/install` now actually runs `pip` or `npm`.  
- Python → `~/.sandbox/python_venv/` (added to `sys.path` immediately)
- JavaScript → `~/.sandbox/node_packages/`

---

## 3. Complete API Reference

**Base URL:** `https://your-backend.railway.app`  
All sandbox endpoints are under `/sandbox`.

---

### 3.1 Execute Code

```
POST /sandbox/execute
```

**Request body:**
```json
{
  "code": "import pandas as pd\ndf = pd.DataFrame({'x': [1,2,3]})\nprint(df)",
  "language": "python",
  "timeout": 30,
  "context": { "user_name": "Alice" },
  "session_id": "conv-abc-123"
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `code` | string | required | Source code to execute |
| `language` | string | `"python"` | `"python"`, `"javascript"`, or `"react"` |
| `timeout` | int | `30` | Max execution seconds |
| `context` | object | null | Variables injected into execution scope |
| `session_id` | string | auto UUID | Pass the same ID across turns to share state |

**Response:**
```json
{
  "success": true,
  "output": "   x\n0  1\n1  2\n2  3",
  "error": null,
  "execution_time_ms": 43.2,
  "language": "python",
  "execution_id": "uuid-of-this-run",
  "session_id": "conv-abc-123",
  "display_type": "text",
  "variables": { "df": "   x\n0  1\n..." },
  "artifacts": []
}
```

**When code generates an image (matplotlib):**
```json
{
  "success": true,
  "output": "Code executed successfully",
  "display_type": "image",
  "artifacts": [
    {
      "artifact_id": "uuid",
      "type": "image/png",
      "display_type": "image",
      "data": "<base64-encoded-png>",
      "encoding": "base64",
      "metadata": { "format": "png", "source": "matplotlib" }
    }
  ]
}
```

**When language is `"react"`:**
```json
{
  "success": true,
  "output": "React component compiled successfully",
  "display_type": "react",
  "artifacts": [
    {
      "artifact_id": "uuid",
      "type": "text/html",
      "display_type": "react",
      "data": "<!DOCTYPE html><html>...<script type=\"text/babel\">...</script></html>",
      "encoding": "utf-8",
      "metadata": { "renderer": "client", "framework": "react18" }
    }
  ]
}
```
→ The `data` field is a complete, self-contained HTML page. **Put it in an `<iframe srcDoc={...} />`**.

---

### 3.2 React Shorthand

```
POST /sandbox/react/execute
```

Same body as `/execute` — always uses `language="react"`. Convenience wrapper.

---

### 3.3 List Languages

```
GET /sandbox/languages
```

**Response:**
```json
{ "languages": ["python", "javascript", "react"] }
```

---

### 3.4 Pre-approved Packages

```
GET /sandbox/packages/{language}
```

Returns the list of packages available without installation.

---

### 3.5 All Packages

```
GET /sandbox/packages/{language}/all?user_id=optional
```

**Response:**
```json
{
  "language": "python",
  "preinstalled": [{ "name": "numpy", "status": "preinstalled" }, ...],
  "cached": [],
  "user_installed": [{ "name": "polars", "version": "0.20.0", "status": "installed" }]
}
```

---

### 3.6 Install Packages

```
POST /sandbox/packages/install
```

**Request:**
```json
{
  "language": "python",
  "packages": ["polars", "statsmodels==0.14.0"],
  "user_id": "optional-rate-limit-key"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Processed 2 package(s)",
  "packages": [
    {
      "name": "polars",
      "version": null,
      "status": "installed",
      "language": "python",
      "install_time_ms": 4200,
      "install_path": "/root/.sandbox/python_venv"
    }
  ],
  "logs": [
    "📦 Installing 'polars'…",
    "✅ 'polars' installed in 4200ms"
  ]
}
```

---

### 3.7 Package Status

```
GET /sandbox/packages/{language}/status/{name}
```

```json
{
  "installed": true,
  "status": "installed",
  "version": "0.20.0",
  "install_path": "/root/.sandbox/python_venv",
  "installed_at": 1712600000
}
```

---

### 3.8 Clear Package Cache

```
POST /sandbox/packages/cache/clear
```

Clears the in-memory package cache (not the disk cache or installed packages).

---

### 3.9 Get Artifacts for an Execution

```
GET /sandbox/artifacts/{execution_id}
```

Returns artifact metadata (without the raw data). Use the `/raw` endpoint for data.

```json
{
  "execution_id": "uuid",
  "artifacts": [
    {
      "artifact_id": "uuid",
      "type": "image/png",
      "display_type": "image",
      "encoding": "base64",
      "created_at": 1712600000
    }
  ],
  "count": 1
}
```

---

### 3.10 Get Raw Artifact

```
GET /sandbox/artifacts/{artifact_id}/raw
```

Returns the artifact with the correct `Content-Type` header.
- Images → binary bytes (`Content-Type: image/png`)
- HTML / React → UTF-8 HTML (`Content-Type: text/html`)

Use this to display artifacts in `<img src="...">` or `<iframe src="...">` via a direct URL.

---

### 3.11 Session History

```
GET /sandbox/session/{session_id}/history?limit=20
```

```json
{
  "session_id": "conv-abc-123",
  "executions": [
    {
      "execution_id": "uuid",
      "language": "python",
      "success": 1,
      "output": "84",
      "exec_time_ms": 12.4,
      "created_at": 1712600000,
      "code_preview": "print(x * 2)"
    }
  ],
  "count": 1
}
```

---

### 3.12 Session Variables

```
GET /sandbox/session/{session_id}/variables
```

```json
{
  "session_id": "conv-abc-123",
  "variables": { "x": 42, "df_shape": [3, 1] },
  "count": 2
}
```

---

### 3.13 Delete Session

```
DELETE /sandbox/session/{session_id}
```

Deletes the session, all its executions, and all its artifacts from SQLite.

---

### 3.14 LLM Sandbox (Docker)

```
POST /sandbox/llm/execute    — execute in isolated Docker container
GET  /sandbox/llm/status     — check Docker availability
```

---

### 3.15 Download a File Artifact ⭐ NEW

```
GET /sandbox/download/{artifact_id}
GET /sandbox/download/{artifact_id}?filename=my_report.xlsx
```

Downloads any artifact as a **file attachment** — the browser will trigger a Save-As dialog. This endpoint is the complement to `/artifacts/{artifact_id}/raw` (which returns the file **inline**).

**When is this used?**  
When Python code calls `open('report.csv', 'w')`, `df.to_excel('output.xlsx')`, `df.to_csv('data.csv')`, `pptx.save('deck.pptx')`, etc., the written file is automatically captured as a `FileArtifact` and stored in the DB. This endpoint lets users download those files directly.

**Path params:**

| Param | Description |
|---|---|
| `artifact_id` | The `artifact_id` from the artifacts array in the execute response |

**Query params:**

| Param | Type | Description |
|---|---|---|
| `filename` | string (optional) | Override the filename for the download. If omitted, uses the stored filename from `metadata.filename` |

**Response headers:**

```
Content-Type: text/csv
Content-Disposition: attachment; filename="output.csv"
Content-Length: 1234
Cache-Control: no-cache
```

**Response body:** Raw file bytes (binary for xlsx/pptx/pdf, UTF-8 for csv/txt/json).

**Full round-trip example:**

1. **Execute code that generates a file:**
```http
POST /sandbox/execute
Content-Type: application/json

{
  "code": "import pandas as pd\ndf = pd.DataFrame({'name': ['Alice','Bob'], 'score': [95, 87]})\ndf.to_csv('scores.csv', index=False)",
  "language": "python"
}
```

2. **Response contains the file artifact:**
```json
{
  "success": true,
  "output": "Code executed successfully",
  "display_type": "file",
  "artifacts": [
    {
      "artifact_id": "a1b2c3d4-...",
      "type": "text/csv",
      "display_type": "file",
      "data": "name,score\nAlice,95\nBob,87\n",
      "encoding": "utf-8",
      "metadata": {
        "filename": "scores.csv",
        "size_bytes": 28,
        "extension": ".csv",
        "downloadable": true
      }
    }
  ]
}
```

3. **Let the user download it:**
```
GET /sandbox/download/a1b2c3d4-...
→ Downloads "scores.csv" with Content-Disposition: attachment
```

**Supported file types and their MIME types:**

| Extension | MIME Type | Notes |
|---|---|---|
| `.csv` | `text/csv` | UTF-8 text |
| `.tsv` | `text/tab-separated-values` | UTF-8 text |
| `.txt` / `.log` / `.md` | `text/plain` / `text/markdown` | UTF-8 text |
| `.json` | `application/json` | UTF-8 text |
| `.xml` / `.yaml` / `.toml` | `application/xml` / `application/x-yaml` / `application/toml` | UTF-8 text |
| `.py` / `.js` | `text/x-python` / `application/javascript` | UTF-8 text |
| `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | Binary |
| `.xls` | `application/vnd.ms-excel` | Binary |
| `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | Binary |
| `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Binary |
| `.pdf` | `application/pdf` | Binary |
| `.png` / `.jpg` / `.gif` / `.bmp` | `image/*` | Binary |
| `.svg` | `image/svg+xml` | UTF-8 text |
| `.zip` / `.gz` / `.tar` | `application/zip` / `application/gzip` / `application/x-tar` | Binary |
| `.parquet` / `.pkl` / `.feather` | `application/octet-stream` | Binary |
| `.mp3` / `.wav` / `.mp4` | `audio/*` / `video/*` | Binary |

**Limits:** Max file size is **50 MB** per file. Files larger than this are silently skipped.

---

### 3.16 View Raw Artifact (Inline) — Updated

```
GET /sandbox/artifacts/{artifact_id}/raw
```

Returns the artifact with the correct `Content-Type` but as **inline** content (browser renders/displays it rather than downloading). For plotly HTML, this renders the chart. For images, the browser displays them directly.

Use **`/download/{artifact_id}`** when you want a Save-As dialog.
Use **`/artifacts/{artifact_id}/raw`** when you want to display in `<img>`, `<iframe>`, or `<embed>`.

---

## 4. Wiring in a Next.js Generative UI Chatbot

### 4.1 How session_id flows through the conversation

```
Supabase conversations table
└── conversation_id  (UUID)
└── sandbox_session_id  (UUID)  ← same as session_id sent to /sandbox/execute
```

Every time the AI calls the sandbox tool in this conversation, it passes the **same `sandbox_session_id`**. That's how Python variables persist across turns.

---

### 4.2 Next.js API Route (`app/api/chat/route.ts`)

```typescript
import { streamText, tool } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { createClient } from '@/lib/supabase/server';

export async function POST(req: Request) {
  const { messages, conversationId } = await req.json();

  // Get (or create) the sandbox_session_id for this conversation
  const supabase = createClient();
  const { data: conv } = await supabase
    .from('conversations')
    .select('sandbox_session_id')
    .eq('id', conversationId)
    .single();

  const sandboxSessionId = conv?.sandbox_session_id ?? crypto.randomUUID();

  // If it's new, save it
  if (!conv?.sandbox_session_id) {
    await supabase
      .from('conversations')
      .upsert({ id: conversationId, sandbox_session_id: sandboxSessionId });
  }

  const result = streamText({
    model: anthropic('claude-3-5-sonnet-20241022'),
    system: `You are a helpful coding assistant with access to a code execution sandbox.
When asked to run code, analyze data, or create visualizations, use the executeSandbox tool.
The sandbox remembers variables across turns in this conversation.
For React/UI components, use language: "react".`,
    messages,
    tools: {
      executeSandbox: tool({
        description: 'Execute Python, JavaScript, or React code in a sandbox.',
        parameters: z.object({
          code: z.string().describe('The code to execute'),
          language: z.enum(['python', 'javascript', 'react'])
            .default('python')
            .describe('python for data/analysis, react for UI components'),
          install_packages: z.array(z.string()).optional()
            .describe('Python/npm packages to install before running'),
        }),
        execute: async ({ code, language, install_packages }) => {
          const BACKEND = process.env.BACKEND_URL ?? 'http://localhost:8000';

          // Install packages first if requested
          if (install_packages?.length) {
            await fetch(`${BACKEND}/sandbox/packages/install`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ language, packages: install_packages }),
            });
          }

          // Execute the code
          const res = await fetch(`${BACKEND}/sandbox/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              code,
              language,
              timeout: 60,
              session_id: sandboxSessionId,   // ← KEY: pass the conversation's session
            }),
          });

          const data = await res.json();
          return data; // Full SandboxExecuteResponse — streamed to client
        },
      }),
    },
  });

  return result.toDataStreamResponse();
}
```

---

### 4.3 Frontend Chat Component (`components/Chat.tsx`)

```tsx
'use client';

import { useChat } from 'ai/react';
import { ArtifactRenderer } from './ArtifactRenderer';

export function Chat({ conversationId }: { conversationId: string }) {
  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: '/api/chat',
    body: { conversationId },      // sent with every request
  });

  return (
    <div className="flex flex-col h-screen">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message) => (
          <div key={message.id}>
            {/* Regular text content */}
            {message.content && (
              <div className={message.role === 'user' ? 'text-right' : 'text-left'}>
                <p className="text-sm">{message.content}</p>
              </div>
            )}

            {/* Tool results (sandbox output) */}
            {message.toolInvocations?.map((invocation) => {
              if (invocation.toolName !== 'executeSandbox') return null;
              if (invocation.state !== 'result') return null;

              return (
                <ArtifactRenderer
                  key={invocation.toolCallId}
                  result={invocation.result}
                />
              );
            })}
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="p-4 border-t">
        <input
          value={input}
          onChange={handleInputChange}
          placeholder="Ask me to run code, analyze data, or build a component..."
          className="w-full border rounded-lg px-4 py-2"
          disabled={isLoading}
        />
      </form>
    </div>
  );
}
```

---

### 4.4 Artifact Renderer (`components/ArtifactRenderer.tsx`)

This is the core component that inspects `display_type` and renders accordingly.  
**Updated for v3** — adds `"plotly"` and `"file"` display types.

```tsx
'use client';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';

interface Artifact {
  artifact_id: string;
  type: string;
  /** "react" | "html" | "plotly" | "image" | "json" | "file" | "text" */
  display_type: string;
  data: string;
  encoding: string;
  metadata?: Record<string, unknown>;
}

interface SandboxResult {
  success: boolean;
  output?: string;
  error?: string;
  language: string;
  display_type: string;
  execution_time_ms: number;
  execution_id: string;
  session_id: string;
  artifacts: Artifact[];
  variables?: Record<string, string>;
}

export function ArtifactRenderer({ result }: { result: SandboxResult }) {
  if (!result.success) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 font-mono text-sm text-red-800">
        <p className="font-semibold mb-1">Execution Error</p>
        <pre className="whitespace-pre-wrap">{result.error}</pre>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Text output (stdout) */}
      {result.output && result.output !== 'Code executed successfully' && (
        <div className="bg-gray-900 text-green-400 rounded-lg p-4 font-mono text-sm">
          <pre className="whitespace-pre-wrap overflow-x-auto">{result.output}</pre>
        </div>
      )}

      {/* Artifacts */}
      {result.artifacts.map((artifact) => (
        <ArtifactItem key={artifact.artifact_id} artifact={artifact} />
      ))}

      {/* Execution footer */}
      <div className="text-xs text-gray-400 flex gap-3">
        <span>{result.language}</span>
        <span>{result.execution_time_ms.toFixed(0)}ms</span>
        <span className="font-mono opacity-50">{result.execution_id?.slice(0, 8)}</span>
      </div>
    </div>
  );
}

function ArtifactItem({ artifact }: { artifact: Artifact }) {
  switch (artifact.display_type) {

    // ── Interactive React components ──────────────────────────────────────
    case 'react':
    case 'html':
      return (
        <div className="rounded-lg overflow-hidden border border-gray-200 shadow-sm">
          <iframe
            srcDoc={artifact.data}
            className="w-full"
            style={{ minHeight: '400px', height: 'auto' }}
            sandbox="allow-scripts allow-same-origin"
            title="Sandbox output"
            onLoad={(e) => {
              const iframe = e.currentTarget;
              try {
                const h = iframe.contentDocument?.documentElement?.scrollHeight;
                if (h) iframe.style.height = `${h + 16}px`;
              } catch {}
            }}
          />
        </div>
      );

    // ── Plotly interactive charts ⭐ NEW ───────────────────────────────────
    // display_type="plotly" means artifact.data is a full self-contained
    // Plotly HTML string (include_plotlyjs="cdn"). Iframe it like React.
    case 'plotly':
      return (
        <div className="rounded-lg overflow-hidden border border-gray-200 shadow-sm bg-white">
          <iframe
            srcDoc={artifact.data}
            className="w-full"
            style={{ minHeight: '450px', height: 'auto' }}
            sandbox="allow-scripts allow-same-origin"
            title="Plotly chart"
            onLoad={(e) => {
              const iframe = e.currentTarget;
              try {
                const h = iframe.contentDocument?.documentElement?.scrollHeight;
                if (h && h > 100) iframe.style.height = `${h + 16}px`;
              } catch {}
            }}
          />
        </div>
      );

    // ── Static images (matplotlib, pillow, SVG) ───────────────────────────
    case 'image':
      if (artifact.type === 'image/svg+xml') {
        // SVG stored as utf-8 string
        return (
          <div
            className="rounded-lg overflow-hidden border border-gray-200 p-4 bg-white"
            dangerouslySetInnerHTML={{ __html: artifact.data }}
          />
        );
      }
      return (
        <div className="rounded-lg overflow-hidden border border-gray-200">
          <img
            src={`data:${artifact.type};base64,${artifact.data}`}
            alt="Generated chart"
            className="w-full h-auto"
          />
        </div>
      );

    // ── Downloadable files ⭐ NEW ──────────────────────────────────────────
    // display_type="file" means code wrote a file (CSV, xlsx, pptx, pdf…)
    // The artifact.data already contains the content, but for the best UX
    // link to the /sandbox/download/ endpoint which sets the right headers.
    case 'file': {
      const meta = (artifact.metadata ?? {}) as Record<string, unknown>;
      const filename = (meta.filename as string) ?? `file${artifact.metadata?.extension ?? ''}`;
      const sizeBytes = meta.size_bytes as number | undefined;
      const sizeLabel = sizeBytes
        ? sizeBytes > 1_000_000
          ? `${(sizeBytes / 1_000_000).toFixed(1)} MB`
          : sizeBytes > 1_000
          ? `${(sizeBytes / 1_000).toFixed(1)} KB`
          : `${sizeBytes} B`
        : '';

      const downloadUrl = `${BACKEND_URL}/sandbox/download/${artifact.artifact_id}`;

      return (
        <div className="flex items-center gap-3 p-3 border border-gray-200 rounded-lg bg-gray-50">
          {/* File icon */}
          <div className="text-2xl">
            {artifact.type.includes('spreadsheet') || artifact.type.includes('excel')
              ? '📊'
              : artifact.type.includes('presentation')
              ? '📑'
              : artifact.type.includes('pdf')
              ? '📄'
              : artifact.type.includes('zip') || artifact.type.includes('gzip')
              ? '🗜️'
              : artifact.type.startsWith('image/')
              ? '🖼️'
              : artifact.type.startsWith('audio/')
              ? '🎵'
              : artifact.type.startsWith('video/')
              ? '🎬'
              : '📁'}
          </div>

          {/* Filename + size */}
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm truncate">{filename}</p>
            <p className="text-xs text-gray-500">{artifact.type} {sizeLabel ? `· ${sizeLabel}` : ''}</p>
          </div>

          {/* Download button */}
          <a
            href={downloadUrl}
            download={filename}
            className="shrink-0 px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors"
          >
            ⬇ Download
          </a>

          {/* Preview button for text files */}
          {(artifact.encoding === 'utf-8' && artifact.type !== 'application/octet-stream') && (
            <button
              onClick={() => {
                const win = window.open('', '_blank');
                if (win) {
                  win.document.write(
                    `<pre style="font-family:monospace;padding:16px;white-space:pre-wrap">${
                      artifact.data.replace(/</g, '&lt;')
                    }</pre>`
                  );
                }
              }}
              className="shrink-0 px-3 py-1.5 text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors"
            >
              👁 Preview
            </button>
          )}
        </div>
      );
    }

    // ── JSON structured data ───────────────────────────────────────────────
    case 'json':
      return (
        <div className="bg-gray-100 rounded-lg p-4 font-mono text-sm overflow-x-auto">
          <pre>{(() => { try { return JSON.stringify(JSON.parse(artifact.data), null, 2); } catch { return artifact.data; } })()}</pre>
        </div>
      );

    // ── Plain text ─────────────────────────────────────────────────────────
    case 'text':
    default:
      return (
        <div className="bg-gray-50 border rounded-lg p-4 text-sm">
          <pre className="whitespace-pre-wrap font-mono">{artifact.data}</pre>
        </div>
      );
  }
}
```

### 4.4b Environment variable needed for download links

Add to `.env.local` so the `ArtifactRenderer` can build download URLs:

```bash
# Public backend URL (accessible from the browser)
NEXT_PUBLIC_BACKEND_URL=https://your-app.railway.app
```

---

### 4.5 Environment Variables (`.env.local`)

```bash
# URL of your FastAPI backend
BACKEND_URL=https://your-app.railway.app

# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://xxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# AI
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 5. Rendering Artifacts on the Frontend

### display_type decision matrix

| `display_type` | What it is | How to render |
|---|---|---|
| `"text"` | Plain stdout | `<pre>` inside a dark code block |
| `"image"` | PNG/SVG from matplotlib/pillow | `<img src="data:image/png;base64,..." />` |
| `"html"` | HTML fragment from `display(HTML(...))` | `<iframe srcDoc={...} sandbox="allow-scripts" />` |
| `"react"` | Complete React app (CDN Babel) | `<iframe srcDoc={...} sandbox="allow-scripts allow-same-origin" />` |
| `"plotly"` ⭐ NEW | Interactive Plotly chart (self-contained HTML) | `<iframe srcDoc={...} sandbox="allow-scripts allow-same-origin" />` |
| `"json"` | Structured data | `<pre>{JSON.stringify(data, null, 2)}</pre>` |
| `"file"` ⭐ NEW | File written by code (CSV, Excel, PPTX, PDF, etc.) | Download button → `GET /sandbox/download/{artifact_id}` |

### Artifact `encoding` field

| `encoding` | Content of `data` field | How to use |
|---|---|---|
| `"utf-8"` | Raw string (HTML, CSV, JSON, SVG…) | Use directly in `srcDoc`, `href`, `innerHTML` |
| `"base64"` | Base64-encoded binary | Decode with `atob()` or pass to `<img src="data:...;base64,...">` |

### Python helpers available in every execution

```python
# ── Matplotlib ──────────────────────────────────────────────
plt.plot([1, 2, 3], [4, 5, 6])
plt.show()                          # → image artifact (PNG, base64)
# (any uncalled plt figures are auto-captured at the end of execution)

# ── Plotly ⭐ ─────────────────────────────────────────────────
import plotly.express as px
fig = px.bar(x=["A","B","C"], y=[10, 20, 15], title="My Chart")
fig.show()                          # → plotly artifact (self-contained HTML, cdn)
# OR:
display(fig)                        # → same plotly artifact
# (any plotly.Figure left in local vars is also auto-captured)

# ── HTML ─────────────────────────────────────────────────────
display(HTML("<table><tr><td>Hello</td></tr></table>"))  # → html artifact

# ── SVG ──────────────────────────────────────────────────────
display(SVG("<svg viewBox='0 0 100 100'><circle cx='50' cy='50' r='40'/></svg>"))

# ── JSON ─────────────────────────────────────────────────────
display(JSON({"key": "value", "list": [1, 2, 3]}))

# ── Files ⭐ ──────────────────────────────────────────────────
import pandas as pd
df = pd.DataFrame({"x": [1,2,3], "y": [4,5,6]})
df.to_csv("output.csv", index=False)      # → file artifact, download via /sandbox/download/
df.to_excel("output.xlsx", index=False)   # → file artifact
# Python pptx, docx, etc. work too:
from pptx import Presentation
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[5])
prs.save("deck.pptx")                     # → file artifact

# ── Regular print ────────────────────────────────────────────
print("hello")                            # → captured in output field
```

### os / sys / shutil — now allowed ⭐ NEW

The sandbox provides **safe proxies** for `os`, `sys`, and `shutil`. These intercept the real modules and restrict dangerous operations:

```python
import os
print(os.getcwd())          # → /tmp/sbx_<exec_id>/   (sandbox temp dir)
os.makedirs("subdir")       # OK — creates inside sandbox dir
os.listdir(".")             # OK — lists sandbox dir

import sys
print(sys.version)          # OK — version metadata only
# sys.exit(), sys.path manipulation → restricted

import shutil
shutil.copy("a.csv", "b.csv")    # OK — sandboxed to temp dir
shutil.make_archive("files", "zip")  # OK — creates zip in temp dir → downloadable!

import pathlib              # real module — safe for path manipulation
from pathlib import Path
p = Path("output.csv")
p.write_text("a,b\n1,2\n")  # writes to CWD (sandbox dir) → downloadable
```

### React sandbox example (AI generates this JSX)

```jsx
// language: "react"
import { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';

const data = [
  { name: 'Jan', value: 400 },
  { name: 'Feb', value: 300 },
  { name: 'Mar', value: 600 },
];

export default function App() {
  const [active, setActive] = useState(null);
  return (
    <div className="p-6">
      <h2 className="text-xl font-bold mb-4">Monthly Revenue</h2>
      <BarChart width={400} height={250} data={data}>
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="value" fill="#6366f1" />
      </BarChart>
    </div>
  );
}
```
→ Returns a self-contained HTML page. Iframe it. No Node.js needed.

---

## 6. Session Management Across Turns

### The pattern

1. Each **conversation** gets one `sandbox_session_id` (a UUID stored in Supabase).
2. The Next.js API route fetches this ID before calling the AI.
3. Every call to `POST /sandbox/execute` includes `"session_id": sandboxSessionId`.
4. Python variables from turn 1 are available in turn 2, 3, etc.
5. When the user starts a new conversation, a new UUID is generated.

### What persists vs what doesn't

| Persists ✅ | Doesn't persist ❌ |
|---|---|
| Python primitive values (int, float, str, bool, list, dict) | numpy arrays, pandas DataFrames |
| JSON-serializable structures | matplotlib figures |
| Variables named without underscore prefix | `_private` variables |
| Values across server restarts | Values from failed executions |

Tip: to persist a DataFrame across turns, convert it to a dict first:
```python
# Turn 1
df = pd.DataFrame({"x": [1,2,3], "y": [4,5,6]})
df_data = df.to_dict("records")   # ← this persists (JSON-serializable list)

# Turn 2
df = pd.DataFrame(df_data)         # ← reconstruct from persisted list
print(df.head())
```

### Clearing a session

```
DELETE /sandbox/session/{session_id}
```

Call this when the user clicks "New Conversation" or "Clear Context".

---

## 7. Supabase — What to Paste

Paste this SQL into the **Supabase SQL Editor** (`Database → SQL Editor → New query`).

> **Note:** The sandbox itself stores its state in a local SQLite file (`~/.sandbox/sandbox.db` on the Railway server). You do **not** need to create SQLite-related tables in Supabase. These Supabase tables are for your **chatbot application layer** — conversations, messages, and linking users to their sandbox sessions.

```sql
-- ============================================================
-- Conversations
-- Each row is one chat thread. Holds the sandbox_session_id
-- so Python variables persist across all turns in a thread.
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    title               TEXT,
    sandbox_session_id  UUID NOT NULL DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- Messages
-- Each message in a conversation. Stores both user messages
-- and AI responses. Tool results (sandbox output) are stored
-- in the tool_result JSONB field.
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content         TEXT,

    -- For tool calls (AI calling the sandbox)
    tool_call_id    TEXT,
    tool_name       TEXT,

    -- Full SandboxExecuteResponse stored here
    -- Includes: success, output, artifacts, display_type, execution_id, etc.
    tool_result     JSONB,

    -- Convenience columns extracted from tool_result for quick queries
    execution_id    TEXT,
    sandbox_language TEXT,
    display_type    TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_execution    ON messages(execution_id);
CREATE INDEX idx_messages_created      ON messages(conversation_id, created_at);

-- ============================================================
-- RLS Policies (Row Level Security)
-- Users can only read/write their own conversations and messages.
-- ============================================================
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages      ENABLE ROW LEVEL SECURITY;

-- Conversations: owned by user
CREATE POLICY "Users own their conversations"
    ON conversations
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Messages: visible if user owns the parent conversation
CREATE POLICY "Users can read messages in their conversations"
    ON messages
    FOR SELECT
    USING (
        conversation_id IN (
            SELECT id FROM conversations WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert messages in their conversations"
    ON messages
    FOR INSERT
    WITH CHECK (
        conversation_id IN (
            SELECT id FROM conversations WHERE user_id = auth.uid()
        )
    );

-- ============================================================
-- Useful view: last message per conversation (for sidebar)
-- ============================================================
CREATE OR REPLACE VIEW conversation_summaries AS
SELECT
    c.id,
    c.title,
    c.sandbox_session_id,
    c.created_at,
    c.updated_at,
    c.user_id,
    m.content AS last_message,
    m.created_at AS last_message_at
FROM conversations c
LEFT JOIN LATERAL (
    SELECT content, created_at
    FROM messages
    WHERE conversation_id = c.id
    ORDER BY created_at DESC
    LIMIT 1
) m ON true;
```

### How to save a sandbox result to Supabase (Next.js)

After the AI returns a tool result, save it to the `messages` table:

```typescript
// Inside your /api/chat route, after tool execution
const sandboxResult = await executeSandbox({ code, language });

await supabase.from('messages').insert({
  conversation_id: conversationId,
  role: 'tool',
  tool_call_id: toolCallId,
  tool_name: 'executeSandbox',
  tool_result: sandboxResult,             // full JSONB blob
  execution_id: sandboxResult.execution_id,
  sandbox_language: sandboxResult.language,
  display_type: sandboxResult.display_type,
});
```

### Fetching conversation history with sandbox results

```typescript
const { data: messages } = await supabase
  .from('messages')
  .select('*')
  .eq('conversation_id', conversationId)
  .order('created_at', { ascending: true });

// Reconstruct for Vercel AI SDK messages format
const aiMessages = messages.map((m) => {
  if (m.role === 'tool') {
    return {
      role: 'tool' as const,
      content: [{
        type: 'tool-result',
        toolCallId: m.tool_call_id,
        toolName: m.tool_name,
        result: m.tool_result,
      }],
    };
  }
  return { role: m.role as 'user' | 'assistant', content: m.content };
});
```

---

## 8. What's New in v3

### 8.1 Auto-install missing packages

If the AI asks for `import plotly.express as px` and plotly isn't installed on the server, the sandbox now **automatically runs `pip install plotly -q`** in the background and retries the import. This works for any package on the approved list.

- First run: may add a few seconds (pip install)
- Subsequent runs: uses the already-installed version

The approved list includes: plotly, seaborn, statsmodels, networkx, scikit-learn, and 60+ other packages.

### 8.2 Plotly interactive charts

```python
import plotly.express as px
fig = px.line(x=[1,2,3,4], y=[10,15,13,18], title="My Line Chart")
fig.show()   # → captured as display_type="plotly" artifact
```

The artifact is a **self-contained HTML page** with Plotly loaded from CDN — no external dependencies. Iframe it the same way as React components.

Also auto-captures any `plotly.graph_objects.Figure` left in local variables without `.show()` being called.

### 8.3 File downloads

Any file written by code is captured and made downloadable:

```python
# All of these create downloadable file artifacts:
df.to_csv("report.csv")
df.to_excel("report.xlsx")
prs.save("slides.pptx")
with open("summary.txt", "w") as f:
    f.write("Hello!")
import shutil; shutil.make_archive("all_files", "zip")
```

New endpoint: **`GET /sandbox/download/{artifact_id}`** — triggers browser Save-As.

### 8.4 Relaxed security

| Module | Before | Now |
|---|---|---|
| `import os` | ❌ Blocked | ✅ Safe proxy — no `system()`, `fork()`, `popen()` |
| `import sys` | ❌ Blocked | ✅ Safe proxy — version/platform info only |
| `import shutil` | ❌ Blocked | ✅ Safe proxy — file ops sandboxed to temp dir |
| `import pathlib` | ❌ Blocked | ✅ Real module |
| `import glob` | ❌ Blocked | ✅ Real module |
| `import inspect` | ❌ Blocked | ✅ Real module |
| `open(...)` write mode | ❌ Blocked | ✅ Forces writes into sandbox temp dir |
| `open(...)` read mode | ❌ Blocked | ✅ Allowed (libraries need to read data files) |

Still blocked: `subprocess`, `socket`, `ctypes`, `multiprocessing`, `signal`, `eval`, `compile`, `exec`.

---

## Quick Test Checklist

After deploying, verify everything works end-to-end:

```bash
# 1. Confirm sandbox is up
curl https://your-backend.railway.app/sandbox/languages
# → {"languages":["python","javascript","react"]}

# 2. Run Python code
curl -X POST https://your-backend.railway.app/sandbox/execute \
  -H "Content-Type: application/json" \
  -d '{"code":"x = 10\nprint(x**2)","language":"python","session_id":"test-1"}'
# → {"success":true,"output":"100\n",...}

# 3. Variable persists in next turn
curl -X POST https://your-backend.railway.app/sandbox/execute \
  -H "Content-Type: application/json" \
  -d '{"code":"print(x + 5)","language":"python","session_id":"test-1"}'
# → {"success":true,"output":"15\n",...}

# 4. React component
curl -X POST https://your-backend.railway.app/sandbox/react/execute \
  -H "Content-Type: application/json" \
  -d '{"code":"export default function App() { return <h1 className=\"text-blue-500\">Hello!</h1> }"}'
# → {"success":true,"display_type":"react","artifacts":[{"type":"text/html",...}]}

# 5. Plotly chart (NEW)
curl -X POST https://your-backend.railway.app/sandbox/execute \
  -H "Content-Type: application/json" \
  -d '{"code":"import plotly.express as px\nfig=px.bar(x=[\"A\",\"B\"],[1,2])\nfig.show()","language":"python"}'
# → {"success":true,"display_type":"plotly","artifacts":[{"display_type":"plotly","type":"text/html",...}]}

# 6. CSV file download (NEW)
curl -X POST https://your-backend.railway.app/sandbox/execute \
  -H "Content-Type: application/json" \
  -d '{"code":"import pandas as pd\npd.DataFrame({\"x\":[1,2,3]}).to_csv(\"out.csv\",index=False)","language":"python"}'
# → {"success":true,"display_type":"file","artifacts":[{"display_type":"file","metadata":{"filename":"out.csv",...}}]}

# Then download it:
curl -L https://your-backend.railway.app/sandbox/download/<artifact_id> -o out.csv
```
