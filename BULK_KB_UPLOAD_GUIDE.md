# Bulk KB Upload Guide

Upload hundreds of documents to the shared Knowledge Base from your local machine — **no browser, no Supabase JWT, no SSH into the server needed**.

---

## How it works

```
Your machine                       Railway server
─────────────                      ────────────────────────────────────────────
bulk_kb_upload.py  ──multipart──▶  POST /kb-admin/bulk-upload
                   X-Admin-Key     │
                                   ├─ extract text (PDF, DOCX, XLSX, CSV…)
                                   ├─ dedup by SHA-256 hash
                                   ├─ save file to Railway volume (/data/…)
                                   ├─ insert row → brain_documents
                                   └─ insert rows → brain_chunks (RAG chunks)
```

Uploaded documents are **visible to every user** in the KB (no per-user filter on the list/search endpoints).

---

## Step 1 — Set the secret on Railway

Generate a long random string and add it as an environment variable:

```powershell
# Option A — Railway CLI
railway variables set ADMIN_UPLOAD_SECRET="$(python -c "import secrets; print(secrets.token_urlsafe(32))")"

# Option B — Railway dashboard
# Project → Service → Variables → + New Variable
# Name:  ADMIN_UPLOAD_SECRET
# Value: <your-random-string>
```

> **Keep this secret private.** Anyone who has it can write documents into your KB.

---

## Step 2 — Create your local config file

```powershell
Copy-Item .env.local.example .env.local
```

Edit `.env.local`:

```ini
KB_UPLOAD_URL=https://your-app.up.railway.app
ADMIN_UPLOAD_SECRET=the-same-secret-you-set-on-railway
```

> `.env.local` is already in `.gitignore` — it will **not** be committed.

---

## Step 3 — Install the script's dependencies

```powershell
pip install requests python-dotenv
```

(`python-dotenv` is optional — the script has a built-in parser as fallback.)

---

## Step 4 — Test the connection

```powershell
python scripts/bulk_kb_upload.py --dir . --env-file .env.local --check
```

Expected output:
```
  ✓ Connection successful!
{
  "total_documents": 12,
  "total_chunks": 847,
  ...
}
```

---

## Step 5 — Upload files

### Upload an entire folder (recursive by default)

```powershell
python scripts/bulk_kb_upload.py `
    --dir C:\Users\you\Documents\KB-Docs `
    --env-file .env.local `
    --category research `
    --tags "2024,earnings,annual-report"
```

### Upload specific files

```powershell
python scripts/bulk_kb_upload.py `
    --files report.pdf strategy.docx notes.txt `
    --env-file .env.local `
    --category strategy
```

### Dry-run first (see what would be uploaded, nothing sent)

```powershell
python scripts/bulk_kb_upload.py `
    --dir ./docs `
    --env-file .env.local `
    --dry-run
```

### Pass credentials inline (no .env file)

```powershell
python scripts/bulk_kb_upload.py `
    --dir ./docs `
    --url https://your-app.up.railway.app `
    --key YOUR_SECRET `
    --category general
```

---

## Options reference

| Flag | Default | Description |
|------|---------|-------------|
| `--dir PATH [PATH…]` | — | Upload directory (recursive) |
| `--files FILE [FILE…]` | — | Upload specific files |
| `--no-recursive` | off | Disable subdirectory recursion |
| `--url URL` | env | API base URL |
| `--key SECRET` | env | ADMIN_UPLOAD_SECRET value |
| `--env-file FILE` | — | Read URL + key from a .env file |
| `--category TEXT` | `general` | KB category for all uploaded files |
| `--tags TEXT` | `` | Comma-separated tags |
| `--batch-size N` | `20` | Files per HTTP request |
| `--timeout N` | `120` | Request timeout in seconds |
| `--dry-run` | off | List files without uploading |
| `--check` | off | Test connection + secret, then exit |
| `--json-output` | off | Print JSON summary at the end |

---

## Supported file types

`.pdf` `.docx` `.doc` `.xlsx` `.xls` `.csv` `.txt` `.md`
`.html` `.htm` `.pptx` `.ppt` `.json` `.xml` `.rtf`

---

## Raw curl (no script needed)

```bash
# Single file
curl -X POST https://your-app.up.railway.app/kb-admin/bulk-upload \
     -H "X-Admin-Key: YOUR_SECRET" \
     -F "files=@report.pdf" \
     -F "category=research"

# Multiple files
curl -X POST https://your-app.up.railway.app/kb-admin/bulk-upload \
     -H "X-Admin-Key: YOUR_SECRET" \
     -F "files=@report.pdf" \
     -F "files=@notes.docx" \
     -F "files=@data.csv" \
     -F "category=general" \
     -F "tags=2024,q1"
```

---

## Admin API endpoints

All require `X-Admin-Key: <ADMIN_UPLOAD_SECRET>` header.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/kb-admin/bulk-upload` | Upload 1–200 files |
| `GET`  | `/kb-admin/list` | List all KB documents |
| `GET`  | `/kb-admin/stats` | Document count, disk usage, categories |
| `DELETE` | `/kb-admin/documents/{id}` | Delete a document |

### List all KB documents

```powershell
Invoke-RestMethod `
    -Uri "https://your-app.up.railway.app/kb-admin/list?limit=50" `
    -Headers @{ "X-Admin-Key" = "YOUR_SECRET" }
```

### Delete a document

```powershell
Invoke-RestMethod `
    -Method DELETE `
    -Uri "https://your-app.up.railway.app/kb-admin/documents/DOCUMENT_UUID" `
    -Headers @{ "X-Admin-Key" = "YOUR_SECRET" }
```

---

## Deduplication

Every file is SHA-256 hashed **before** insert. If the exact same bytes have already been uploaded, the document is skipped (`status: "duplicate"`) — you can safely re-run the script on the same folder without creating duplicates.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `503 ADMIN_UPLOAD_SECRET is not configured` | Add the env var to Railway and redeploy |
| `401 Invalid or missing X-Admin-Key` | Check `--key` matches the Railway variable exactly |
| `413` file too large | Files must be ≤ 10 MB |
| `error: Could not extract any text` | File may be image-only PDF or binary — not supported |
| Connection timeout | Increase `--timeout 300` for large batches |
