# Knowledge Stacks — Backend Changes & Frontend Integration Guide

> Msty-style "Knowledge Stacks" for the Analyst by Potomac platform.
> This document covers everything that changed on the backend and exactly what
> the frontend team needs to build to expose it.

---

## 1. What Was Broken Before

| # | Bug | Impact |
|---|-----|--------|
| 1 | Chunk size hard-coded to **500 chars**, max **50 chunks** per doc | Any document longer than 25,000 chars was silently truncated. A 10-page PDF (~40k chars) lost more than half its content. |
| 2 | Each chunk inserted with its own `.execute()` call inside a `for` loop | 50–100 round trips to Supabase per upload → frequent timeouts on large files. |
| 3 | `_generate_embedding()` was only called at **search time** | Vector search always returned empty because no chunks ever had embeddings stored. The whole pgvector pipeline was unused. |
| 4 | `/knowledge-base/upload` delegated to `brain_upload` without forwarding `BackgroundTasks` | The default `BackgroundTasks()` in the function signature was a fresh, disconnected object — background indexing never ran. Files saved to disk were never chunked. |
| 5 | `content[i:i+500]` chunker — cut mid-sentence, no overlap | Killed RAG quality at chunk boundaries. |
| 6 | `/brain/upload-batch` ran extraction + classification + chunking synchronously inside the request | Multi-file uploads timed out on Railway. |
| 7 | No "stack" concept — files were just tagged with a flat `category` string | No way to group, configure, or attach a curated set of docs to a chat. |

All of these are now fixed.

---

## 2. What's New on the Backend

### 2.1 New Files

| File | Purpose |
|------|---------|
| `core/rag_chunker.py` | Sentence-boundary-aware chunker (1500 chars, 150 overlap, no cap). Batched Voyage embeddings. Single-call bulk INSERT into `brain_chunks`. |
| `api/routes/stacks.py` | New `/stacks/*` router — full CRUD + upload + search + RAG context retrieval. |
| `db/migrations/024_knowledge_stacks.sql` | New `knowledge_stacks` table, `brain_documents.stack_id` FK, auto-stats trigger, and `match_stack_chunks()` RPC. |
| `Documentation/KNOWLEDGE_STACKS_GUIDE.md` | This file. |

### 2.2 Modified Files

| File | What Changed |
|------|--------------|
| `api/routes/brain.py` | Uses `chunk_and_index()` from the new chunker. No more 50-chunk cap. Batch INSERT. Embeddings generated at ingest. |
| `api/routes/kb_admin.py` | Same fix for `bulk-upload` and `upload-preparsed`. |
| `api/routes/knowledge_base.py` | Fixed BackgroundTasks delegation bug — now `/knowledge-base/upload` actually indexes the file. |
| `main.py` | Registers the new `stacks` router. |

### 2.3 Database Migration (Run This First)

> **Action required**: Open the Supabase SQL editor and paste the contents of `db/migrations/024_knowledge_stacks.sql`, then run it. The migration is idempotent (safe to re-run).

It creates:
- `knowledge_stacks` table with per-stack JSONB `settings`
- `brain_documents.stack_id` FK column (nullable — old documents are unaffected)
- Trigger that auto-refreshes `document_count`, `total_chunks`, and `total_size_bytes` whenever documents change
- `match_stack_chunks(p_stack_id, query_embedding, threshold, count)` RPC for stack-scoped vector search

### 2.4 Optional Environment Variable

Set `VOYAGE_API_KEY` on Railway to enable embedding generation at ingest time.
Without it, everything still works — the system falls back to ILIKE text search.

---

## 3. New API Surface — `/stacks/*`

All endpoints require the user's Supabase JWT in the `Authorization: Bearer <token>` header (same auth as the rest of the app).

### 3.1 Stack CRUD

#### `POST /stacks` — Create a stack

```http
POST /stacks
Content-Type: application/json

{
  "name": "Earnings Reports 2024",
  "description": "Quarterly earnings PDFs for Q1–Q4 2024",
  "icon": "📊",
  "color": "#10b981",
  "settings": {
    "chunk_size": 1500,
    "chunk_count": 20,
    "overlap": 150,
    "load_mode": "static",
    "generate_embeddings": true
  }
}
```

Response (201):
```json
{
  "id": "8c7e...",
  "user_id": "...",
  "name": "Earnings Reports 2024",
  "description": "...",
  "icon": "📊",
  "color": "#10b981",
  "settings": { ... },
  "document_count": 0,
  "total_chunks": 0,
  "total_size_bytes": 0,
  "created_at": "2025-...",
  "updated_at": "2025-..."
}
```

`409 Conflict` is returned if a stack with the same name already exists for this user.

---

#### `GET /stacks` — List all user stacks

Response:
```json
{
  "stacks": [ { ...stack1 }, { ...stack2 } ],
  "count": 2
}
```

---

#### `GET /stacks/{stack_id}` — Get one stack

Returns the full stack object (including `settings` merged with defaults).

---

#### `PATCH /stacks/{stack_id}` — Update name / settings

```http
PATCH /stacks/8c7e...
Content-Type: application/json

{
  "name": "Renamed",
  "settings": {
    "chunk_size": 2000,
    "chunk_count": 30,
    "overlap": 200,
    "load_mode": "static",
    "generate_embeddings": true
  }
}
```

Any subset of fields may be sent.

---

#### `DELETE /stacks/{stack_id}?cascade=true`

- `cascade=true` (default): also deletes every document in the stack and removes the files from disk.
- `cascade=false`: documents are unlinked (`stack_id` set to NULL) but kept in the global KB.

---

### 3.2 File Ingestion

#### `POST /stacks/{stack_id}/upload` — Upload a single file

```http
POST /stacks/8c7e.../upload
Content-Type: multipart/form-data

file=<binary>
title=Q1 2024 Earnings (optional)
```

Returns **202 Accepted** immediately:
```json
{
  "status": "processing",
  "document_id": "...",
  "stack_id": "8c7e...",
  "ready": false,
  "message": "File uploaded; indexing in background."
}
```

If the same file (by SHA-256) is already in this stack:
```json
{
  "status": "duplicate",
  "document_id": "...",
  "stack_id": "8c7e...",
  "ready": true | false
}
```

---

#### `POST /stacks/{stack_id}/upload-batch` — Upload many files

```http
POST /stacks/8c7e.../upload-batch
Content-Type: multipart/form-data

files=<file1>
files=<file2>
files=<file3>
```

Returns 202 with per-file status:
```json
{
  "stack_id": "8c7e...",
  "total": 3,
  "queued": 2,
  "duplicates": 1,
  "errors": 0,
  "results": [
    { "filename": "a.pdf", "status": "processing", "document_id": "..." },
    { "filename": "b.pdf", "status": "duplicate",  "document_id": "..." },
    { "filename": "c.pdf", "status": "processing", "document_id": "..." }
  ]
}
```

---

#### Polling indexing status

For each `document_id` returned above, poll the existing endpoint:

```http
GET /brain/documents/{document_id}/status
```

Response:
```json
{ "document_id": "...", "status": "processing" | "ready" | "error", "ready": bool, ... }
```

---

### 3.3 Document Management

#### `GET /stacks/{stack_id}/documents?limit=100&offset=0`

```json
{
  "stack_id": "...",
  "total": 42,
  "has_more": false,
  "documents": [
    {
      "id": "...",
      "title": "...",
      "filename": "...",
      "file_type": "application/pdf",
      "file_size": 245678,
      "summary": "...",
      "tags": [],
      "chunk_count": 88,
      "is_processed": true,
      "processed_at": "2025-...",
      "created_at": "2025-..."
    }
  ]
}
```

---

#### `DELETE /stacks/{stack_id}/documents/{document_id}?delete_file_too=true`

- `delete_file_too=true` (default): document + chunks + file on disk all deleted.
- `delete_file_too=false`: document is just unlinked from the stack (`stack_id` → NULL), file kept.

---

#### `POST /stacks/{stack_id}/documents/{document_id}/move`

```json
{ "target_stack_id": "<other-stack-uuid>" }
```

---

### 3.4 RAG: Search & Context Retrieval

#### `POST /stacks/{stack_id}/search`

```json
{ "query": "What were Q3 2024 revenues?", "limit": 20 }
```

Response (vector if embeddings exist, else text):
```json
{
  "stack_id": "...",
  "query": "...",
  "search_type": "vector" | "text",
  "count": 5,
  "results": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "document_title": "Q3 2024 Earnings.pdf",
      "document_filename": "q3-2024.pdf",
      "chunk_index": 7,
      "content": "Total Q3 revenues were $4.2B...",
      "similarity": 0.8421,
      "search_type": "vector"
    }
  ]
}
```

---

#### `GET /stacks/{stack_id}/context` — for chat injection

This is the endpoint the chat UI should call when the user attaches a stack.

| Query param | Behaviour |
|-------------|-----------|
| `?query=...` | RAG mode — returns the top-K most relevant chunks. |
| `?full_content=true` | Msty's "Full Content Context" — returns full `raw_content` of every doc in the stack. |
| (neither) | Returns the first K chunks (`chunk_index ASC`) across all docs. |

`limit` overrides the stack's default `chunk_count`.

Example RAG response:
```json
{
  "stack_id": "...",
  "stack_name": "Earnings Reports 2024",
  "mode": "rag",
  "query": "Q3 revenues",
  "search_type": "vector",
  "chunk_count": 12,
  "chunks": [ { ...same shape as search results... } ]
}
```

Example Full-Content response:
```json
{
  "stack_id": "...",
  "stack_name": "Earnings Reports 2024",
  "mode": "full_content",
  "document_count": 4,
  "total_chars": 178432,
  "documents": [
    { "document_id": "...", "title": "...", "filename": "...", "content": "...", "char_count": 42188 },
    ...
  ]
}
```

---

#### `POST /stacks/{stack_id}/reindex`

After changing `settings.chunk_size`, `settings.overlap`, or `settings.generate_embeddings`, call this to re-chunk every document in the stack with the new settings. Returns 200 immediately; reindexing happens in the background.

---

## 4. Frontend Build Checklist

> **Estimated effort**: 1 frontend dev, 2–3 days.

### 4.1 Stack Management UI

Build a **"Knowledge Stacks"** page (sidebar navigation entry next to Files / Conversations).

**Required components**:

1. **Stacks list** (left rail or grid)
   - Cards showing: icon, color stripe, name, description, document count, chunk count, total size (humanized), updated_at relative time.
   - Click → opens stack detail view.
   - "+ New Stack" button → opens the create modal.

2. **Create / Edit Stack modal**
   - Fields: name, description, icon (emoji picker), color (color picker).
   - Settings panel (collapsible "Advanced"):
     - Chunk size slider (200–8000, default 1500)
     - Chunks per query slider (1–100, default 20)
     - Overlap slider (0–2000, default 150)
     - Load mode dropdown: Static / Dynamic / Sync
     - Generate embeddings toggle (default on)
   - "Reindex on save" checkbox if user changed any chunk setting (calls `POST /stacks/{id}/reindex`).

3. **Stack detail view**
   - Header: icon, name, description, settings summary, edit/delete buttons.
   - "Drop files here" upload zone calling `POST /stacks/{id}/upload-batch`.
   - Document table: filename, size, status (processing / ready / error), chunk count, uploaded date, actions menu (delete, move).
   - Polling: every ~2 s, hit `GET /brain/documents/{id}/status` for any documents in `processing` state until they go `ready` or `error`.

4. **Move document modal** — picker showing other stacks; on confirm calls `POST /stacks/{id}/documents/{doc_id}/move`.

5. **Delete confirmation modals**
   - Stack delete: "Also delete all N documents inside?" toggle (maps to `?cascade=true|false`).
   - Document delete: "Also delete the file from storage?" toggle.

### 4.2 Chat Integration

In the chat composer, add a **"Attach Stack"** dropdown next to the existing file-attach button.

**Behaviour**:

1. Dropdown lists the user's stacks (`GET /stacks`).
2. When the user picks a stack:
   - Persist the selection in chat state (e.g. `attachedStackId` per conversation).
   - Show a chip in the composer: `📊 Earnings Reports 2024 (4 docs, 312 chunks)`.
   - Add a small "mode" toggle on the chip:
     - **RAG** (default): for each user message, before sending, call
       `GET /stacks/{id}/context?query=<userMessage>&limit=<chunk_count>`
       and prepend the returned chunks to the chat as system context.
     - **Full Content**: call `GET /stacks/{id}/context?full_content=true`
       once and prepend the full doc text. Show a warning if `total_chars` is huge.

3. The chunks/documents returned should be prepended to the LLM prompt in a system message like:

   ```
   You have access to the following relevant context from the user's
   "Earnings Reports 2024" knowledge stack:

   [1] q3-2024.pdf (chunk 7):
   Total Q3 revenues were $4.2B...

   [2] q3-2024.pdf (chunk 12):
   ...

   Cite documents inline when you use them.
   ```

4. The frontend should also display "Sources" cards under each assistant message that referenced stack chunks (use `document_title` + `document_filename` from the response).

### 4.3 Backward Compatibility

The existing `/brain/upload`, `/knowledge-base/upload`, and `/kb-admin/bulk-upload` endpoints continue to work. Documents uploaded through them have `stack_id = NULL` and show up in the global "Library" view. Users can add them to a stack later by:

1. Adding a "Move to stack…" action to the existing Library document table.
2. Calling `POST /stacks/{id}/documents/{doc_id}/move` with the document already having no source (you'll need a small helper endpoint or do it via a direct UPDATE — let me know if you want me to add a "claim into stack" endpoint).

### 4.4 Stack Settings Cheat Sheet for Users

Include this copy in the "Advanced settings" panel:

| Setting | What it does | When to change |
|---------|--------------|----------------|
| **Chunk size** | How many characters of text go into each searchable piece. | Larger (2000–4000) for technical/legal docs where context matters. Smaller (800–1200) for FAQ-style content. |
| **Chunks per query** | How many pieces are pulled into the chat context for each question. | Higher = more context, more tokens used. Lower = faster, cheaper. |
| **Overlap** | How much consecutive chunks share. | Higher (200–400) for narrative documents. Zero for purely structured data. |
| **Load mode** | Static = index once. Dynamic = re-index on every query. Sync = re-index when files change. | Most users should leave this on Static. |
| **Generate embeddings** | Use semantic vector search (requires `VOYAGE_API_KEY`). | Off = falls back to keyword search. On = much smarter retrieval. |

---

## 5. Quick Smoke Tests (cURL)

```bash
# 1. Create a stack
curl -X POST $API/stacks \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","description":"Smoke test","icon":"🧪","color":"#ec4899"}'
# → returns { "id": "<STACK_ID>", ... }

# 2. Upload a file
curl -X POST $API/stacks/$STACK_ID/upload \
  -H "Authorization: Bearer $JWT" \
  -F "file=@./test.pdf"
# → 202, returns { "document_id": "<DOC_ID>", ... }

# 3. Wait for indexing
curl $API/brain/documents/$DOC_ID/status -H "Authorization: Bearer $JWT"
# → "status": "ready", "chunk_count": <some number, NOT capped at 50>

# 4. Search
curl -X POST $API/stacks/$STACK_ID/search \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"query":"revenue"}'

# 5. Chat-ready RAG context
curl "$API/stacks/$STACK_ID/context?query=revenue&limit=10" \
  -H "Authorization: Bearer $JWT"
```

---

## 6. Summary

✅ Backend: chunker rewritten, embeddings produced at ingest, batch inserts, BackgroundTasks bug fixed, full Knowledge Stacks API live.

🟡 Database migration: **paste `db/migrations/024_knowledge_stacks.sql` into the Supabase SQL editor and run it**.

🔵 Frontend: build the Stacks page + chat integration described in Section 4. The full API contract is in Section 3 — every endpoint is implemented and ready.

🟣 Optional: set `VOYAGE_API_KEY` on Railway to unlock semantic search.
