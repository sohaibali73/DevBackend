#!/usr/bin/env python3
"""
Execute migration via Supabase using available methods.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Read the incremental migration SQL
migration_path = Path(__file__).parent.parent / 'db' / 'migrations' / '001_incremental_missing.sql'
sql = migration_path.read_text()

print("=" * 70)
print("SUPABASE MIGRATION - MISSING TABLES")
print("=" * 70)
print()
print("The following need to be created:")
print("  Tables: file_uploads, usage_events, presentations, audit_logs")
print("  Buckets: user-uploads, presentations, brain-docs")
print()
print("=" * 70)
print("MIGRATION SQL:")
print("=" * 70)
print()
print(sql)
print()
print("=" * 70)
print("INSTRUCTIONS:")
print("=" * 70)
print()
print("Option 1 - Supabase Dashboard (Recommended):")
print("  1. Open: https://supabase.com/dashboard/project/vekcfcmstpnxubxsaano/sql")
print("  2. Click 'New query'")
print("  3. Paste the SQL above")
print("  4. Click 'Run' (Ctrl+Enter)")
print()
print("Option 2 - Get Service Role Key:")
print("  1. Open: https://supabase.com/dashboard/project/vekcfcmstpnxubxsaano/settings/api")
print("  2. Copy the 'service_role' key (secret)")
print("  3. Add to .env: SUPABASE_SERVICE_KEY=your-key")
print("  4. Run this script again")
print()