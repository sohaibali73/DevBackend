# Knowledge Base + Knowledge Stacks — Frontend Integration Brief

Complete picture of how the backend works, every route the frontend will touch, and the exact pattern for **"show the original document to the user, but feed the chunked RAG version to the model."**

---

## 1. The Two Layers (key mental model)

The backend has **two parallel systems** sitting on top of the same `brain_documents` + `brain_chunks` tables:

| Layer | Purpose | Path prefix | Scope |
|---|---|---|---|
| **Knowledge Base (Library)** | Flat, global "all my files" view. Every uploaded file lives here. | `/brain/*` and the alias `/knowledge-base/*` | Per-user, no grouping |
| **Knowledge Stacks** | Msty-style curated collections you attach to a chat. Each stack has its own RAG settings (chunk size, top-K, embeddings on/off). | `/stacks/*` | Per-user, grouped by `stack_id` |

A document is a row in `brain_documents`:

- `stack_id IS NULL` → only in the Library.
- `stack_id` set → appears in that stack **and** in the Library.

Chunks for both layers live in `brain_chunks` (FK → `brain_documents.id`, cascade delete).

### Per-document storage

| What | Where | Used for |
|---|---|---|
| **Original file binary** | Railway volume at `storage_path` (untouched, exactly as uploaded) | The user-facing preview / download |
| **`raw_content`** | Full extracted plaintext on the document row | "Full Content" mode and quick text previews |
| **`brain_chunks`** | 1500-char overlapping chunks + pgvector embeddings | RAG retrieval for the model |

All endpoints require `Authorization: Bearer <supabase JWT>`.

---

## 2. Knowledge Base routes (`/brain/*`, mirrored at `/knowledge-base/*`)

### Upload / ingest

| Method | Path | Notes |
|---|---|---|
| `POST` | `/brain/upload` | multipart `file`, optional `title`, `category`. Returns 202 with `document_id`. Background task extracts text → chunks → embeds → batch-inserts. |
| `POST` | `/brain/upload-batch` | multiple `files=`, returns 202 with per-file results. |
| `POST` | `/brain/upload-text` | plain-text upload (no file). |
| `POST` | `/knowledge-base/upload` | alias of `/brain/upload`. |

### Status polling (use after every upload)

- `GET /brain/documents/{document_id}/status` → `{ status: "processing" | "ready" | "error", ready, chunk_count, ... }`
- Poll every ~2 s until `ready === true`.

### Listing / metadata

| Method | Path | Returns |
|---|---|---|
| `GET` | `/brain/documents` | Paginated list (raw shape). |
| `GET` | `/knowledge-base/files?limit&offset&search&category&tags` | Friendly shape: `id, name, filename, size, type, upload_date, tags, description, category, page_count`. |
| `GET` | `/brain/stats` / `/knowledge-base/stats` | Totals. |
| `GET` | `/brain/documents/{id}` | Full row including `raw_content` (for previews). |
| `GET` | `/knowledge-base/files/{id}` | Same but with a 500-char `raw_content_preview` and usage stats. |
| `PATCH` | `/knowledge-base/files/{id}` | Update `tags` / `description`. |

### File bytes — these power the preview UI

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/brain/documents/{id}/download` | **Original binary**, `Content-Disposition: inline`, cacheable. **Use this for in-app preview/viewer.** |
| `GET` | `/brain/documents/{id}/content` | Same bytes but `attachment` (Save As). |
| `GET` | `/knowledge-base/files/{id}/download` | Alias of the above. |
| `GET` | `/files/{file_id}/preview` | **Structured JSON preview** for PPTX (slides[]) and DOCX (sections[]). Backed by in-memory `core/file_store` — works for files produced by skills/tools, not necessarily KB-uploaded files. For uploaded files prefer the `/download` + client-side parsing route. |

### Search (global, all user docs)

- `POST /brain/search` / `POST /knowledge-base/search`
- Body: `{ query, category?, limit }`
- Vector if embeddings exist, else ILIKE fallback.
- Returns chunk-level hits with `document_id`, `content`, `similarity`.

### Reindex / delete

| Method | Path | Notes |
|---|---|---|
| `POST` | `/brain/documents/{id}/reindex` | Re-chunk one doc. |
| `POST` | `/brain/reindex-all` | Re-chunk every doc. |
| `DELETE` | `/brain/documents/{id}` | Deletes row + cascades chunks + removes file from disk. |
| `DELETE` | `/knowledge-base/files/{id}` | Alias. |

---

## 3. Knowledge Stacks routes (`/stacks/*`)

A stack is a row in `knowledge_stacks` with its own `settings` JSON:

```json
{
  "chunk_size": 1500,        // 200..8000
  "chunk_count": 20,         // top-K, 1..100
  "overlap": 150,            // 0..2000
  "load_mode": "static",     // "static" | "dynamic" | "sync"
  "generate_embeddings": true
}
```

A DB trigger keeps `document_count`, `total_chunks`, `total_size_bytes` up to date automatically.

### Stack CRUD

| Method | Path | Notes |
|---|---|---|
| `POST` | `/stacks` | Create. Body: `{ name, description, icon, color, settings? }`. 409 on duplicate name. |
| `GET` | `/stacks` | `{ stacks: [...], count }`. |
| `GET` | `/stacks/{id}` | Full stack with merged-with-defaults settings. |
| `PATCH` | `/stacks/{id}` | Partial update of name / description / icon / color / settings. |
| `DELETE` | `/stacks/{id}?cascade=true|false` | `true` (default) deletes docs + files. `false` just unlinks (`stack_id → NULL`, docs stay in Library). |

### Files inside a stack

| Method | Path | Notes |
|---|---|---|
| `POST` | `/stacks/{id}/upload` | Single file. SHA-256 dedup *within the stack*. Returns 202 `{ document_id, status: "processing" \| "duplicate", ready }`. |
| `POST` | `/stacks/{id}/upload-batch` | Many files at once. |
| `GET` | `/stacks/{id}/documents?limit&offset` | Paginated docs. |
| `DELETE` | `/stacks/{id}/documents/{doc_id}?delete_file_too=true|false` | Same delete-vs-unlink choice. |
| `POST` | `/stacks/{id}/documents/{doc_id}/move` | Body `{ target_stack_id }`. |

> Status polling for stack uploads uses the same global endpoint: `GET /brain/documents/{id}/status`.

### Stack-scoped RAG (this is what chat uses)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/stacks/{id}/search` | Body `{ query, limit? }`. Tries vector (`match_stack_chunks` RPC), falls back to ILIKE. Returns `{ search_type: "vector" \| "text", results: [{chunk_id, document_id, document_title, document_filename, chunk_index, content, similarity}] }`. |
| `POST` | `/stacks/{id}/reindex` | Re-chunk every doc in the stack with current settings (use after editing chunk_size / overlap / embeddings toggle). |

### `GET /stacks/{id}/context` — the chat-injection endpoint

The one your chat composer calls. Three behaviours:

| Query | Mode | Returns |
|---|---|---|
| `?query=<userMessage>&limit=K` | `"rag"` | Top-K most relevant **chunks** for the message. |
| `?full_content=true` | `"full_content"` | Every doc's full `raw_content` (warn the user — can be huge, see `total_chars`). |
| (neither) | `"head"` | First K chunks across all docs (deterministic preview). |

---

## 4. The "preview original / model uses chunks" pattern

This is already exactly how the backend is designed. The user-facing preview and the model-facing context come from **two completely different endpoints** for the same `document_id`:

```
                          document_id
                          ┌─────┴─────┐
                          ▼           ▼
              USER PREVIEW         MODEL CONTEXT
              ─────────────        ──────────────
GET /brain/documents/{id}/download    POST /stacks/{id}/search
   → original .pdf/.docx/.pptx        GET  /stacks/{id}/context?query=...
   → render with pdfjs/mammoth/etc.   → returns chunks[]
                                      → inject into LLM prompt
```

### A. Library / Stack detail UI — what the user sees

- Render thumbnails / file icons + metadata from `GET /knowledge-base/files` (or `/stacks/{id}/documents`).
- Clicking a file opens a viewer that fetches `GET /brain/documents/{id}/download` and renders the **original**:

| Extension | Render with |
|---|---|
| `.pdf` | `pdfjs-dist` |
| `.docx` | `mammoth` |
| `.xlsx` | `xlsx` (SheetJS) + `react-data-grid` |
| `.pptx` | iframe a server-rendered preview, or call `GET /files/{id}/preview` if available; otherwise just offer download |
| `.csv` | `papaparse` + grid |
| `.txt` / `.md` | render directly |

- **Never show the user the chunked text.** Chunks are 1500-char fragments cut on sentence boundaries — they look ugly and are for the model only.
- Quick text preview without a full download: use `raw_content_preview` (500 chars) from `GET /knowledge-base/files/{id}`, or full `raw_content` from `GET /brain/documents/{id}` as a scrollable plaintext fallback.

### B. Chat — what the model sees

When the user attaches a stack (`attachedStackId` saved per conversation):

1. Render a chip in the composer:
   `📊 Earnings Reports 2024 — 4 docs · 312 chunks`
   with a mode toggle (**RAG** ⇄ **Full Content**).

2. **On every user message** (RAG mode):

   ```
   GET /stacks/{stackId}/context?query=<encoded user message>&limit=20
   ```

   Build a system message from the returned `chunks[]`:

   ```
   You have access to the following relevant context from
   the user's "Earnings Reports 2024" knowledge stack:

   [1] q3-2024.pdf (chunk 7):
   <chunk content>

   [2] q3-2024.pdf (chunk 12):
   <chunk content>

   Cite documents inline when you use them.
   ```

   Send that to the LLM **before** the user's message. The user never sees this raw chunk text in the chat bubble.

3. After the assistant replies, render a **Sources** strip below the assistant message — one card per unique `document_id` referenced. Each card shows `document_title` + `document_filename`; on click, open the **original document preview** (rule A), optionally jumping near the chunk by searching the rendered text for the chunk's first ~80 chars.

4. **Full Content mode** (alternative): call `GET /stacks/{id}/context?full_content=true` once per conversation and prepend `documents[].content`. Warn if `total_chars > ~200000`.

### C. Keep the two layers cleanly separated in your data layer

Suggested TS types:

```ts
// What the user sees in the file browser & viewer
type KBDocument = {
  id: string;
  title: string;
  filename: string;
  file_type: string;
  file_size: number;
  chunk_count: number;
  is_processed: boolean;
  created_at: string;
  stack_id: string | null;
};

// What the model gets
type RagChunk = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  document_filename: string;
  chunk_index: number;
  content: string;
  similarity: number | null;
  search_type: "vector" | "text";
};
```

Two API client modules:

- `kbApi.ts` — list / get / download / delete. Deals in `KBDocument` and binary blobs. **Preview side.**
- `stacksApi.ts` — stacks CRUD + `getContext(stackId, query) → RagChunk[]`. **Chat side.**

The chat composer should **never** call `/download`, and the file viewer should **never** call `/context`. That separation is exactly what gives you "user sees original, model sees chunks" for free.

---

## 5. UI surfaces to build

1. **Library page** (`/knowledge-base/files`)
   - Table + drag-drop upload (`POST /brain/upload`)
   - Status polling on each row
   - Viewer modal that calls `/download` and renders client-side

2. **Stacks page** (`/stacks`)
   - Grid of stack cards (icon, color, name, doc count, chunk count, size)
   - "+ New Stack" modal with the settings panel: chunk_size slider, chunk_count slider, overlap slider, load_mode dropdown, generate_embeddings toggle

3. **Stack detail page**
   - Header with edit / delete
   - Drop-zone (`/stacks/{id}/upload-batch`)
   - Document table (filename, size, status, chunk count, actions: delete / move)
   - "Reindex" button (`POST /stacks/{id}/reindex`) after any settings change

4. **Chat composer add-on**
   - "Attach Stack" dropdown listing `GET /stacks`
   - Chip with RAG / Full toggle
   - Pre-flight every send with `GET /stacks/{id}/context`

5. **Sources strip** under each assistant message that used stack chunks — links back into the Library viewer for the original doc.

---

## 6. Reference docs already in the repo

- `Documentation/KNOWLEDGE_STACKS_GUIDE.md` — Section 3 has every request/response shape, smoke-test cURLs, and a frontend build checklist.
- `Documentation/SWIFT_KNOWLEDGE_BASE_API.md` — Swift-flavoured walk-through of the same endpoints (preview/download/search).
- `api/routes/stacks.py` — source of truth for stack endpoints.
- `api/routes/brain.py`, `api/routes/knowledge_base.py`, `api/routes/preview.py` — source of truth for KB endpoints.
