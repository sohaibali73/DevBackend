# Next.js Frontend Integration Guide
## pptx-automizer + All Office Tools — Complete Reference

This guide covers all changes made in the pptx-automizer integration sprint, the complete tool registry, API endpoints, and exact Next.js / TypeScript code to handle every tool result.

---

## Table of Contents

1. [What Changed](#what-changed)
2. [Architecture Overview](#architecture-overview)
3. [API Endpoints Reference](#api-endpoints-reference)
4. [Tool Registry — Complete List](#tool-registry--complete-list)
5. [Streaming Response Parsing](#streaming-response-parsing)
6. [Detecting Tool Results by Tool Name](#detecting-tool-results-by-tool-name)
7. [File Upload (for template_file_id)](#file-upload-for-template_file_id)
8. [File Download + Download Button](#file-download--download-button)
9. [PPTX Preview with PPTXjs](#pptx-preview-with-pptxjs)
10. [Complete React Components](#complete-react-components)
11. [TypeScript Types](#typescript-types)
12. [Environment Variables](#environment-variables)

---

## What Changed

### New Tool: `generate_pptx_template` ⭐

The biggest addition. Loads an **existing .pptx** and injects fresh data — preserving all designer formatting.

**Backend files modified:**
| File | Change |
|---|---|
| `core/sandbox/automizer_sandbox.py` | NEW — `AutomizerSandbox` class + embedded Node.js runner |
| `core/tools_v2/document_tools.py` | Added `GENERATE_PPTX_TEMPLATE_TOOL_DEF` + `handle_generate_pptx_template()` |
| `core/tools.py` | Added tool to `TOOL_DEFINITIONS` + `elif` dispatch |

**Template files committed:**
```
ClaudeSkills/potomac-pptx/automizer-templates/
  potomac-content-slides.pptx    (5 slides)
  potomac-chart-slides.pptx      (3 slides with real charts)
  potomac-table-slides.pptx      (3 slides with styled tables)
  potomac-fund-fact-sheet.pptx   (1 slide, {{tagged}} placeholders)
```

### npm Cache Optimization

The `pptx-automizer` npm package now shares `~/.sandbox/pptx_cache/` with `pptxgenjs` — one node_modules directory for both tools.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Next.js Frontend                                    │
│                                                      │
│  1. Upload .pptx  →  POST /files/upload              │
│     (returns file_id)                                │
│                                                      │
│  2. Chat message  →  POST /chat/stream               │
│     (SSE stream — AI picks tools automatically)      │
│                                                      │
│  3. Parse SSE for tool_result events                 │
│     (tool_name + result JSON)                        │
│                                                      │
│  4. On PPTX result:  render download button          │
│     On PPTX template result:  render preview + DL   │
└─────────────────────────────────────────────────────┘
                        │
                        ▼ Railway API
┌─────────────────────────────────────────────────────┐
│  Backend                                             │
│                                                      │
│  /chat/stream    → claude_engine → tools dispatch    │
│  /files/upload   → stores in Railway volume          │
│  /files/{id}/download  → streams bytes               │
│  /files/{id}/preview   → returns text/JSON profile  │
└─────────────────────────────────────────────────────┘
```

---

## API Endpoints Reference

### `POST /files/upload`
Upload a file (PPTX, image, PDF, Excel, etc.) to get a `file_id`.

**Request:**
```typescript
const formData = new FormData()
formData.append('file', file)            // File object
formData.append('user_id', userId)       // optional

const res = await fetch(`${API_URL}/files/upload`, {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: formData,
})
const { file_id, filename, size_kb } = await res.json()
```

**Response:**
```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "Q4_2025_Fund_Report.pptx",
  "size_kb": 842.3,
  "file_type": "pptx",
  "upload_url": "/files/550e8400.../download"
}
```

---

### `GET /files/{file_id}/download`
Stream file bytes for download.

```typescript
const downloadUrl = `${API_URL}/files/${fileId}/download`
// Use as href for <a download> or window.open()
```

**Response:** `application/octet-stream` binary

---

### `GET /files/{file_id}/preview`
Get text/structured preview of a PPTX (slide titles, text content, shape names).

```typescript
const res = await fetch(`${API_URL}/files/${fileId}/preview`, {
  headers: { 'Authorization': `Bearer ${token}` }
})
const { slides } = await res.json()
// slides[0].title, slides[0].text_content, slides[0].shapes
```

---

### `POST /chat/stream`
Main chat endpoint — SSE stream.

```typescript
const res = await fetch(`${API_URL}/chat/stream`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    message: userMessage,
    conversation_id: conversationId,  // optional
    user_id: userId,
  })
})
// Read as EventSource / ReadableStream
```

---

### `GET /chat/stream` (EventSource)
Alternative streaming via EventSource for simpler clients.

```typescript
const url = new URL(`${API_URL}/chat/stream`)
url.searchParams.set('message', userMessage)
url.searchParams.set('token', token)
const es = new EventSource(url.toString())
```

---

## Tool Registry — Complete List

All tools available to the AI. The frontend needs to handle `tool_result` events for each relevant tool.

### Document Generation Tools

| Tool Name | Output | Frontend Action |
|---|---|---|
| `generate_pptx` | `.pptx` download | Download button + PPTXjs preview |
| `generate_pptx_freestyle` | `.pptx` download | Download button + PPTXjs preview |
| **`generate_pptx_template`** | `.pptx` download | Download button + PPTXjs preview + warnings |
| `generate_docx` | `.docx` download | Download button |
| `generate_xlsx` | `.xlsx` download | Download button |
| `revise_pptx` | `.pptx` download | Download button + diff summary |
| `analyze_pptx` | JSON profile | Display slide count, shape names, compliance score |
| `analyze_xlsx` | JSON profile | Display columns, stats, sample rows |
| `transform_xlsx` | `.xlsx` download | Download button + row count |

### All Tool Names (for `tool_name` matching in SSE)

```typescript
const PPTX_TOOLS = [
  'generate_pptx',
  'generate_pptx_freestyle',
  'generate_pptx_template',    // NEW
  'revise_pptx',
]

const ANALYSIS_TOOLS = [
  'analyze_pptx',
  'analyze_xlsx',
]

const FILE_DOWNLOAD_TOOLS = [
  'generate_pptx',
  'generate_pptx_freestyle',
  'generate_pptx_template',    // NEW
  'generate_docx',
  'generate_xlsx',
  'revise_pptx',
  'transform_xlsx',
]
```

---

## Streaming Response Parsing

The chat endpoint sends Server-Sent Events (SSE). Each event has a `data:` field with JSON.

### SSE Event Types

```
event: text_delta        → AI is typing text (append to message)
event: tool_start        → Tool call starting (show spinner)
event: tool_result       → Tool completed (render result card)
event: message_complete  → AI response done
event: error             → Error occurred
```

### Next.js SSE Parser

```typescript
// hooks/useChat.ts

export async function streamChat(
  message: string,
  token: string,
  onTextDelta: (text: string) => void,
  onToolResult: (toolName: string, result: ToolResult) => void,
  onComplete: () => void,
) {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  })

  if (!res.ok || !res.body) throw new Error(`Stream failed: ${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data:')) continue

      const raw = line.slice(5).trim()
      if (raw === '[DONE]') { onComplete(); continue }

      try {
        const event = JSON.parse(raw)

        switch (event.type) {
          case 'text_delta':
            onTextDelta(event.text ?? event.delta ?? '')
            break

          case 'tool_result':
            onToolResult(event.tool_name, event.result)
            break

          case 'message_complete':
            onComplete()
            break
        }
      } catch {
        // ignore malformed JSON lines
      }
    }
  }
}
```

---

## Detecting Tool Results by Tool Name

The `result` object shape differs per tool. Here are the exact shapes.

### PPTX Generation Tools (generate_pptx, generate_pptx_freestyle, generate_pptx_template)

```typescript
interface PptxResult {
  status: 'success' | 'error'
  file_id: string
  filename: string
  size_kb: number
  download_url: string        // e.g. "/files/{uuid}/download"
  exec_time_ms: number
  message: string

  // generate_pptx_template only:
  mode?: 'update' | 'assembly'
  warnings?: string[]         // non-fatal pptx-automizer warnings
}
```

### generate_pptx_template — Extra Fields

```typescript
// mode = "update":
// message includes: "4 global replacements, 2 slides modified"

// mode = "assembly":
// message includes: "3 slides assembled"

// warnings: shape names not found, column mismatches, etc.
// Non-fatal — the file is still generated
```

### analyze_pptx

```typescript
interface AnalyzePptxResult {
  status: 'success' | 'error'
  file_id: string
  filename: string
  exec_time_ms: number
  profile: {
    slide_count: number
    title: string
    slides: Array<{
      number: number
      title: string
      text_content: string[]
      shapes: Array<{ name: string; type: string }>
      has_chart: boolean
      has_table: boolean
      has_image: boolean
    }>
    brand_compliance: {
      score: number              // 0–100
      issues: string[]
    }
  }
  message: string
}
```

### generate_docx

```typescript
interface DocxResult {
  status: 'success' | 'error'
  file_id: string
  filename: string
  size_kb: number
  download_url: string
  exec_time_ms: number
  message: string
}
```

### revise_pptx

```typescript
interface RevisePptxResult {
  status: 'success' | 'error'
  file_id: string
  filename: string
  size_kb: number
  download_url: string
  operations_applied: number
  replacements_made: number
  exec_time_ms: number
  message: string
}
```

---

## File Upload (for template_file_id)

Before calling `generate_pptx_template`, the user must upload their existing deck. Here's the complete flow:

### Upload Component

```tsx
// components/PptxUploader.tsx
'use client'

import { useState, useCallback } from 'react'

interface UploadedFile {
  file_id: string
  filename: string
  size_kb: number
}

export function PptxUploader({
  onUploaded,
}: {
  onUploaded: (file: UploadedFile) => void
}) {
  const [uploading, setUploading] = useState(false)
  const [uploaded, setUploaded] = useState<UploadedFile | null>(null)

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (!file || !file.name.endsWith('.pptx')) return
    await upload(file)
  }, [])

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    await upload(file)
  }

  const upload = async (file: File) => {
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/files/upload`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${localStorage.getItem('auth_token')}`,
          },
          body: form,
        }
      )
      const data = await res.json()
      setUploaded(data)
      onUploaded(data)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      className="border-2 border-dashed border-yellow-400 rounded-lg p-6 text-center cursor-pointer hover:bg-yellow-50 transition"
    >
      <input
        type="file"
        accept=".pptx"
        className="hidden"
        id="pptx-upload"
        onChange={handleChange}
      />
      <label htmlFor="pptx-upload" className="cursor-pointer">
        {uploading ? (
          <span className="text-gray-500">Uploading…</span>
        ) : uploaded ? (
          <div className="text-green-700">
            <p className="font-bold">✓ {uploaded.filename}</p>
            <p className="text-sm text-gray-500">{uploaded.size_kb.toFixed(1)} KB uploaded</p>
            <p className="text-xs text-gray-400 font-mono mt-1">ID: {uploaded.file_id}</p>
          </div>
        ) : (
          <>
            <p className="text-gray-600 font-medium">Drop your .pptx here</p>
            <p className="text-sm text-gray-400 mt-1">or click to browse</p>
          </>
        )}
      </label>
    </div>
  )
}
```

### Telling the AI the file_id

After upload, include the file_id in the chat message:

```typescript
// In your chat input handler:
const message = uploadedFile
  ? `Update this deck with Q1 2026 data. Template file_id: ${uploadedFile.file_id}. 
     Replace all "Q4 2025" with "Q1 2026". Update the performance chart on slide 4 
     with these returns: Jan: 2.1%, Feb: 0.9%, Mar: 1.5%. 
     Update the holdings table on slide 7 with current top holdings.`
  : userMessage

sendMessage(message)
```

---

## File Download + Download Button

All PPTX/DOCX/XLSX tools return a `download_url` relative path. Construct the full URL:

### Download Button Component

```tsx
// components/FileDownloadCard.tsx
'use client'

interface FileDownloadCardProps {
  toolName: string
  result: {
    status: string
    filename?: string
    size_kb?: number
    download_url?: string
    warnings?: string[]
    mode?: string
    operations_applied?: number
    replacements_made?: number
    exec_time_ms?: number
    message?: string
  }
}

const TOOL_ICONS: Record<string, string> = {
  generate_pptx:          '📊',
  generate_pptx_freestyle:'🎨',
  generate_pptx_template: '⚡',
  generate_docx:          '📄',
  generate_xlsx:          '📈',
  revise_pptx:            '✏️',
  transform_xlsx:         '🔄',
}

const TOOL_LABELS: Record<string, string> = {
  generate_pptx:          'PowerPoint Generated',
  generate_pptx_freestyle:'Custom PowerPoint Generated',
  generate_pptx_template: 'Presentation Updated',
  generate_docx:          'Word Document Generated',
  generate_xlsx:          'Excel Workbook Generated',
  revise_pptx:            'Presentation Revised',
  transform_xlsx:         'Data Transformed',
}

export function FileDownloadCard({ toolName, result }: FileDownloadCardProps) {
  if (result.status !== 'success' || !result.download_url) return null

  const fullUrl = `${process.env.NEXT_PUBLIC_API_URL}${result.download_url}`
  const icon    = TOOL_ICONS[toolName] ?? '📁'
  const label   = TOOL_LABELS[toolName] ?? 'File Ready'
  const ext     = result.filename?.split('.').pop()?.toUpperCase() ?? 'FILE'

  const handleDownload = () => {
    const a = document.createElement('a')
    a.href = fullUrl
    a.download = result.filename ?? 'download'
    a.click()
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden mt-2">
      {/* Header bar */}
      <div className="bg-yellow-400 px-4 py-2 flex items-center gap-2">
        <span className="text-xl">{icon}</span>
        <span className="font-bold text-gray-900 text-sm">{label}</span>
        {result.mode && (
          <span className="ml-auto text-xs bg-gray-900 text-yellow-400 px-2 py-0.5 rounded-full font-mono uppercase">
            {result.mode}
          </span>
        )}
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-gray-900 text-sm">{result.filename}</p>
            <p className="text-xs text-gray-400 mt-0.5">
              {result.size_kb?.toFixed(1)} KB
              {result.exec_time_ms && ` · ${(result.exec_time_ms / 1000).toFixed(1)}s`}
              {result.operations_applied != null && ` · ${result.operations_applied} operations`}
              {result.replacements_made != null && ` · ${result.replacements_made} replacements`}
            </p>
          </div>
          <button
            onClick={handleDownload}
            className="flex items-center gap-2 bg-gray-900 text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-gray-700 transition"
          >
            ↓ Download {ext}
          </button>
        </div>

        {/* Warnings (generate_pptx_template) */}
        {result.warnings && result.warnings.length > 0 && (
          <details className="mt-2">
            <summary className="text-xs text-yellow-600 cursor-pointer hover:text-yellow-800">
              ⚠ {result.warnings.length} warning{result.warnings.length > 1 ? 's' : ''}
            </summary>
            <ul className="mt-1 space-y-0.5">
              {result.warnings.map((w, i) => (
                <li key={i} className="text-xs text-gray-500 font-mono pl-2 border-l-2 border-yellow-300">
                  {w}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  )
}
```

---

## PPTX Preview with PPTXjs

For PPTX results, you can render an in-chat preview using [PPTXjs](https://github.com/meshesha/PPTXjs).

### Install

```bash
npm install pptxjs
# or CDN in layout.tsx:
# <script src="https://cdn.jsdelivr.net/npm/pptxjs@1.1.0/dist/pptxjs.min.js" />
```

### Preview Component

```tsx
// components/PptxPreview.tsx
'use client'

import { useEffect, useRef, useState } from 'react'

interface PptxPreviewProps {
  downloadUrl: string   // full URL e.g. https://...railway.app/files/{id}/download
  filename: string
}

export function PptxPreview({ downloadUrl, filename }: PptxPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [open, setOpen]       = useState(false)

  useEffect(() => {
    if (!open || !containerRef.current) return

    const load = async () => {
      try {
        setLoading(true)
        setError(null)

        // Fetch PPTX bytes
        const res = await fetch(downloadUrl, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('auth_token')}`,
          },
        })
        const arrayBuffer = await res.arrayBuffer()

        // PPTXjs render
        // @ts-ignore — global from CDN
        const pptx = new PPTX()
        await pptx.load(arrayBuffer)
        if (containerRef.current) {
          containerRef.current.innerHTML = ''
          await pptx.render(containerRef.current)
        }
      } catch (err) {
        setError('Preview unavailable — download to view')
      } finally {
        setLoading(false)
      }
    }

    load()
  }, [open, downloadUrl])

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(!open)}
        className="text-xs text-blue-600 hover:underline"
      >
        {open ? '▲ Hide preview' : '▼ Preview slides'}
      </button>

      {open && (
        <div className="mt-2 border border-gray-200 rounded-lg overflow-hidden">
          {loading && (
            <div className="h-32 flex items-center justify-center text-gray-400 text-sm">
              Loading preview…
            </div>
          )}
          {error && (
            <div className="h-16 flex items-center justify-center text-yellow-600 text-sm">
              {error}
            </div>
          )}
          <div
            ref={containerRef}
            className="pptx-preview-container overflow-x-auto"
            style={{ minHeight: loading ? 0 : 300 }}
          />
        </div>
      )}
    </div>
  )
}
```

### Combined Card with Preview

```tsx
// components/PptxResultCard.tsx
import { FileDownloadCard } from './FileDownloadCard'
import { PptxPreview }      from './PptxPreview'

export function PptxResultCard({
  toolName,
  result,
}: {
  toolName: string
  result: any
}) {
  if (result.status !== 'success') return null

  const fullUrl = `${process.env.NEXT_PUBLIC_API_URL}${result.download_url}`

  return (
    <div>
      <FileDownloadCard toolName={toolName} result={result} />
      <PptxPreview downloadUrl={fullUrl} filename={result.filename} />
    </div>
  )
}
```

---

## Complete React Components

### Tool Result Router

Plug this into your message rendering to automatically render the right card for each tool result.

```tsx
// components/ToolResultCard.tsx
import { FileDownloadCard } from './FileDownloadCard'
import { PptxResultCard }   from './PptxResultCard'
import { AnalysisPptxCard } from './AnalysisPptxCard'

const PPTX_DOWNLOAD_TOOLS = new Set([
  'generate_pptx',
  'generate_pptx_freestyle',
  'generate_pptx_template',
  'revise_pptx',
])

const DOCX_XLSX_TOOLS = new Set([
  'generate_docx',
  'generate_xlsx',
  'transform_xlsx',
])

export function ToolResultCard({
  toolName,
  result,
}: {
  toolName: string
  result: any
}) {
  if (!result || result.status === 'error') {
    return result?.error ? (
      <div className="text-red-500 text-sm mt-1 p-2 bg-red-50 rounded">
        Tool error: {result.error}
      </div>
    ) : null
  }

  if (PPTX_DOWNLOAD_TOOLS.has(toolName)) {
    return <PptxResultCard toolName={toolName} result={result} />
  }

  if (DOCX_XLSX_TOOLS.has(toolName)) {
    return <FileDownloadCard toolName={toolName} result={result} />
  }

  if (toolName === 'analyze_pptx') {
    return <AnalysisPptxCard result={result} />
  }

  // Default: nothing rendered (tool handled via AI text response)
  return null
}
```

### analyze_pptx Result Card

```tsx
// components/AnalysisPptxCard.tsx
export function AnalysisPptxCard({ result }: { result: any }) {
  if (result.status !== 'success') return null

  const { profile } = result
  const compliance  = profile.brand_compliance

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden mt-2">
      <div className="bg-gray-900 px-4 py-2 flex items-center gap-2">
        <span>🔍</span>
        <span className="font-bold text-white text-sm">Presentation Analysis</span>
        <span className="ml-auto text-yellow-400 font-bold text-sm">
          {profile.slide_count} slides
        </span>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Title */}
        {profile.title && (
          <p className="font-semibold text-gray-900">{profile.title}</p>
        )}

        {/* Brand compliance */}
        <div className="flex items-center gap-3">
          <div className="flex-1 bg-gray-100 rounded-full h-2">
            <div
              className="h-2 rounded-full"
              style={{
                width: `${compliance?.score ?? 0}%`,
                backgroundColor: (compliance?.score ?? 0) >= 80
                  ? '#22c55e' : (compliance?.score ?? 0) >= 50
                  ? '#fec00f' : '#ef4444',
              }}
            />
          </div>
          <span className="text-sm font-semibold text-gray-700 w-16 text-right">
            {compliance?.score ?? 0}% brand
          </span>
        </div>

        {/* Slides summary */}
        <div className="grid grid-cols-3 gap-2 text-xs text-gray-600">
          <div className="bg-gray-50 rounded p-2 text-center">
            <div className="font-bold text-gray-900">
              {profile.slides?.filter((s: any) => s.has_chart).length ?? 0}
            </div>
            charts
          </div>
          <div className="bg-gray-50 rounded p-2 text-center">
            <div className="font-bold text-gray-900">
              {profile.slides?.filter((s: any) => s.has_table).length ?? 0}
            </div>
            tables
          </div>
          <div className="bg-gray-50 rounded p-2 text-center">
            <div className="font-bold text-gray-900">
              {profile.slides?.filter((s: any) => s.has_image).length ?? 0}
            </div>
            images
          </div>
        </div>
      </div>
    </div>
  )
}
```

---

## Complete Chat Integration Example

```tsx
// app/chat/page.tsx (simplified)
'use client'

import { useState, useRef } from 'react'
import { ToolResultCard }   from '@/components/ToolResultCard'
import { PptxUploader }     from '@/components/PptxUploader'

interface Message {
  role: 'user' | 'assistant'
  content: string
  toolResults?: Array<{ toolName: string; result: any }>
}

export default function ChatPage() {
  const [messages, setMessages]       = useState<Message[]>([])
  const [input, setInput]             = useState('')
  const [streaming, setStreaming]     = useState(false)
  const [uploadedFile, setUploadedFile] = useState<any>(null)

  const sendMessage = async () => {
    if (!input.trim() || streaming) return

    const userMessage = uploadedFile
      ? `${input}\n\n[Attached PPTX: file_id=${uploadedFile.file_id}, filename=${uploadedFile.filename}]`
      : input

    setMessages(prev => [...prev, { role: 'user', content: input }])
    setInput('')
    setStreaming(true)

    // Add placeholder assistant message
    let assistantIdx = -1
    setMessages(prev => {
      assistantIdx = prev.length
      return [...prev, { role: 'assistant', content: '', toolResults: [] }]
    })

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`,
        },
        body: JSON.stringify({ message: userMessage }),
      })

      const reader  = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer    = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          const raw = line.slice(5).trim()
          if (raw === '[DONE]') continue

          try {
            const event = JSON.parse(raw)

            if (event.type === 'text_delta') {
              setMessages(prev => prev.map((m, i) =>
                i === assistantIdx
                  ? { ...m, content: m.content + (event.text ?? event.delta ?? '') }
                  : m
              ))
            }

            if (event.type === 'tool_result') {
              setMessages(prev => prev.map((m, i) =>
                i === assistantIdx
                  ? {
                      ...m,
                      toolResults: [...(m.toolResults ?? []),
                        { toolName: event.tool_name, result: event.result }
                      ]
                    }
                  : m
              ))
            }
          } catch {
            // ignore
          }
        }
      }
    } finally {
      setStreaming(false)
    }
  }

  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto p-4 gap-4">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] ${msg.role === 'user' ? 'bg-yellow-100' : 'bg-white border'} rounded-xl p-3`}>
              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>

              {/* Render tool result cards */}
              {msg.toolResults?.map((tr, ti) => (
                <ToolResultCard key={ti} toolName={tr.toolName} result={tr.result} />
              ))}
            </div>
          </div>
        ))}
        {streaming && (
          <div className="text-gray-400 text-sm animate-pulse">AI is thinking…</div>
        )}
      </div>

      {/* Upload zone (optional) */}
      <PptxUploader onUploaded={setUploadedFile} />

      {/* Input */}
      <div className="flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMessage()}
          placeholder={
            uploadedFile
              ? `Ask about ${uploadedFile.filename} or request an update…`
              : "Ask anything or request a document…"
          }
          className="flex-1 border border-gray-300 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-yellow-400"
          disabled={streaming}
        />
        <button
          onClick={sendMessage}
          disabled={streaming || !input.trim()}
          className="bg-yellow-400 text-gray-900 font-bold px-5 py-2 rounded-xl hover:bg-yellow-300 disabled:opacity-50 transition"
        >
          Send
        </button>
      </div>
    </div>
  )
}
```

---

## TypeScript Types

```typescript
// types/tools.ts

export interface ToolResult {
  status: 'success' | 'error'
  error?: string
}

export interface PptxToolResult extends ToolResult {
  file_id: string
  filename: string
  size_kb: number
  download_url: string
  exec_time_ms: number
  message: string
}

export interface PptxTemplateResult extends PptxToolResult {
  mode: 'update' | 'assembly'
  warnings: string[]
}

export interface RevisePptxResult extends PptxToolResult {
  operations_applied: number
  replacements_made: number
}

export interface AnalyzePptxResult extends ToolResult {
  file_id: string
  filename: string
  exec_time_ms: number
  profile: {
    slide_count: number
    title: string
    slides: SlideProfile[]
    brand_compliance: {
      score: number
      issues: string[]
    }
  }
  message: string
}

export interface SlideProfile {
  number: number
  title: string
  text_content: string[]
  shapes: { name: string; type: string }[]
  has_chart: boolean
  has_table: boolean
  has_image: boolean
}

export interface UploadedFile {
  file_id: string
  filename: string
  size_kb: number
  file_type: string
  upload_url: string
}
```

---

## Environment Variables

```env
# .env.local

NEXT_PUBLIC_API_URL=https://developer-potomaac.up.railway.app

# Or for local dev:
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Quick Reference Cheat Sheet

### User wants to update a quarterly deck

```
1. User uploads .pptx → POST /files/upload → file_id
2. User types: "Update this to Q1 2026 data. file_id: {id}"
3. AI calls: generate_pptx_template(mode="update", ...)
4. SSE event: { type: "tool_result", tool_name: "generate_pptx_template", result: {...} }
5. Frontend renders: <PptxResultCard /> with download button + preview
```

### User wants a new deck from scratch

```
1. User types: "Create a Q1 2026 investor update for Defensive Alpha"
2. AI calls: generate_pptx(slides: [...])
   OR:       generate_pptx_freestyle(code: "...")
3. SSE event: { type: "tool_result", tool_name: "generate_pptx", result: {...} }
4. Frontend renders: <PptxResultCard />
```

### User uploads and asks about a deck

```
1. User uploads .pptx
2. User types: "What's on slide 4? What are the shape names?"
3. AI calls: analyze_pptx(file_id: "...")
4. SSE event: { type: "tool_result", tool_name: "analyze_pptx", result: {...} }
5. Frontend renders: <AnalysisPptxCard /> with slide count, charts/tables, compliance score
```
