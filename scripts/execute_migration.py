#!/usr/bin/env python3
"""
Execute database migration using Supabase REST API.
Uses the anon key since service role is not available.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import requests
import json

def execute_migration():
    """Execute the migration SQL via Supabase REST API."""
    
    url = os.getenv('SUPABASE_URL')
    anon_key = os.getenv('SUPABASE_KEY')
    
    if not url or not anon_key:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set")
        return False
    
    # Read migration file
    migration_path = Path(__file__).parent.parent / 'db' / 'migrations' / '001_initial_schema.sql'
    if not migration_path.exists():
        print(f"ERROR: Migration file not found: {migration_path}")
        return False
    
    sql = migration_path.read_text()
    print(f"Read migration file: {len(sql)} bytes")
    
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json"
    }
    
    # Split SQL into individual statements
    # We'll execute them in batches
    
    # First, let's check existing tables using REST API
    print("\n=== Checking existing database state ===\n")
    
    tables_to_check = [
        'user_profiles', 'conversations', 'messages', 'file_uploads',
        'conversation_files', 'brain_documents', 'afl_codes', 'afl_history',
        'user_feedback', 'usage_events', 'presentations', 'audit_logs'
    ]
    
    existing_tables = []
    for table in tables_to_check:
        try:
            resp = requests.get(
                f"{url}/rest/v1/{table}?select=id&limit=1",
                headers=headers
            )
            if resp.status_code == 200:
                existing_tables.append(table)
                print(f"  [OK] {table} exists")
            elif resp.status_code == 404:
                print(f"  [MISSING] {table} does not exist")
            else:
                print(f"  [?] {table} - status {resp.status_code}")
        except Exception as e:
            print(f"  [ERROR] {table} - error: {e}")
    
    print(f"\nExisting tables: {len(existing_tables)}/{len(tables_to_check)}")
    
    if len(existing_tables) == len(tables_to_check):
        print("\n✅ All tables already exist! Migration may have been run previously.")
        return True
    
    # Check for storage buckets
    print("\n=== Checking storage buckets ===\n")
    try:
        resp = requests.get(
            f"{url}/storage/v1/bucket",
            headers=headers
        )
        if resp.status_code == 200:
            buckets = resp.json()
            bucket_names = [b.get('name', b.get('id')) for b in buckets]
            print(f"  Existing buckets: {bucket_names}")
            
            required_buckets = ['user-uploads', 'presentations', 'brain-docs']
            for bucket in required_buckets:
                if bucket in bucket_names:
                    print(f"  ✓ {bucket} exists")
                else:
                    print(f"  ✗ {bucket} needs to be created")
        else:
            print(f"  Could not check buckets: {resp.status_code}")
    except Exception as e:
        print(f"  Error checking buckets: {e}")
    
    print("\n" + "="*60)
    print("MIGRATION REQUIRED")
    print("="*60)
    print("""
The Supabase MCP or REST API cannot execute DDL statements directly.
You need to run the migration via Supabase Dashboard or psql.

QUICKEST OPTION:
1. Open: https://supabase.com/dashboard/project/vekcfcmstpnxubxsaano/sql
2. Click "New query"
3. Paste the contents of: db/migrations/001_initial_schema.sql
4. Click "Run" (or press Ctrl+Enter)

The migration will create:
- 12 tables with RLS policies
- 3 storage buckets
- Triggers for auto-updates and audit logging
- Full-text search indexes
""")
    
    return False


if __name__ == "__main__":
    execute_migration()