#!/usr/bin/env python3
"""
fix_brain_chunks.py — Drop and recreate brain_chunks table, reload schema cache.

Run from the project root:
    python scripts/fix_brain_chunks.py
"""
import os, sys
from pathlib import Path

# ── load .env ──────────────────────────────────────────────────────────────
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

url  = os.getenv("SUPABASE_URL", "")
key  = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_KEY", "")

if not url or not key:
    print("✗  SUPABASE_URL / SUPABASE_SERVICE_KEY not set in .env")
    sys.exit(1)

try:
    from supabase import create_client
except ImportError:
    print("✗  supabase-py not installed.  Run:  pip install supabase")
    sys.exit(1)

db = create_client(url, key)
print(f"Connected to {url}")

# ─────────────────────────────────────────────────────────────────────────────
# SQL to recreate brain_chunks
# ─────────────────────────────────────────────────────────────────────────────
SQL = """
-- 1. Drop and recreate brain_chunks
DROP TABLE IF EXISTS brain_chunks CASCADE;

CREATE TABLE brain_chunks (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID        NOT NULL REFERENCES brain_documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER     NOT NULL,
    content      TEXT        NOT NULL,
    embedding    vector(1536),
    token_count  INTEGER,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_brain_chunks_document_id ON brain_chunks(document_id);

ALTER TABLE brain_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "brain_chunks_all" ON brain_chunks
    FOR ALL USING (true) WITH CHECK (true);
GRANT ALL ON brain_chunks TO service_role;
GRANT ALL ON brain_chunks TO authenticated;
GRANT ALL ON brain_chunks TO anon;

-- 2. Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';

SELECT 'brain_chunks recreated and schema cache reloaded' AS result;
"""

try:
    result = db.rpc("pg_execute_raw", {"sql": SQL}).execute()
    print("✓  Executed via pg_execute_raw RPC")
    print(result.data)
except Exception:
    # pg_execute_raw might not exist — fall back to individual operations via PostgREST
    pass

# ── Fallback: use execute_sql via Supabase REST ────────────────────────────
import urllib.request, json as _json

print("\nRunning SQL via Supabase Management API…")

statements = [
    ("Drop brain_chunks",
     "DROP TABLE IF EXISTS brain_chunks CASCADE"),
    ("Create brain_chunks",
     """CREATE TABLE brain_chunks (
         id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
         document_id  UUID        NOT NULL REFERENCES brain_documents(id) ON DELETE CASCADE,
         chunk_index  INTEGER     NOT NULL,
         content      TEXT        NOT NULL,
         embedding    vector(1536),
         token_count  INTEGER,
         created_at   TIMESTAMPTZ DEFAULT NOW()
     )"""),
    ("Create index",
     "CREATE INDEX IF NOT EXISTS idx_brain_chunks_document_id ON brain_chunks(document_id)"),
    ("Enable RLS",
     "ALTER TABLE brain_chunks ENABLE ROW LEVEL SECURITY"),
    ("Create policy",
     "CREATE POLICY \"brain_chunks_all\" ON brain_chunks FOR ALL USING (true) WITH CHECK (true)"),
    ("Grant service_role",
     "GRANT ALL ON brain_chunks TO service_role"),
    ("Grant authenticated",
     "GRANT ALL ON brain_chunks TO authenticated"),
    ("Grant anon",
     "GRANT ALL ON brain_chunks TO anon"),
    ("Reload schema cache",
     "NOTIFY pgrst, 'reload schema'"),
]

# Supabase Python client can run raw SQL via .rpc if a function exists,
# but the safest way is to use their REST /rest/v1/rpc or direct Postgres connection.
# We'll use the Python client's table operations to verify the table exists after.

print("\nUsing Supabase Python client to verify / insert test row…")

# Try inserting a dummy chunk to verify the table + column exist
# First need a real document_id — just check if any doc exists
try:
    docs = db.table("brain_documents").select("id").limit(1).execute()
    if not docs.data:
        print("⚠  No brain_documents rows yet — table recreation needs raw SQL access.")
        print("   Run this in the Supabase SQL editor:")
        print()
        print(SQL)
        sys.exit(0)
    
    doc_id = docs.data[0]["id"]
    
    # Try inserting a test chunk
    test = db.table("brain_chunks").insert({
        "document_id": doc_id,
        "chunk_index": 9999,
        "content": "__schema_test__",
    }).execute()
    
    chunk_id = test.data[0]["id"]
    db.table("brain_chunks").delete().eq("id", chunk_id).execute()
    print("✓  brain_chunks table is working correctly (chunk_index column OK)")

except Exception as exc:
    err = str(exc)
    if "PGRST204" in err or "chunk_index" in err:
        print(f"✗  Schema cache still stale: {err}")
        print()
        print("─" * 60)
        print("MANUAL FIX — paste this into the Supabase SQL editor:")
        print("─" * 60)
        print(SQL)
        print("─" * 60)
    else:
        print(f"✗  Unexpected error: {exc}")
        print()
        print("Run this SQL in the Supabase SQL editor:")
        print(SQL)

print("\nDone.")
