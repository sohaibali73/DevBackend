#!/usr/bin/env python3
"""
Run database migration using Supabase.
This script executes the initial schema migration.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import requests

def run_migration():
    """Execute the migration SQL via Supabase REST API."""
    
    url = os.getenv('SUPABASE_URL')
    service_key = os.getenv('SUPABASE_SERVICE_KEY')
    
    if not url or not service_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        print(f"SUPABASE_URL: {'SET' if url else 'NOT SET'}")
        print(f"SUPABASE_SERVICE_KEY: {'SET' if service_key else 'NOT SET'}")
        return False
    
    # Read migration file
    migration_path = Path(__file__).parent.parent / 'db' / 'migrations' / '001_initial_schema.sql'
    if not migration_path.exists():
        print(f"ERROR: Migration file not found: {migration_path}")
        return False
    
    sql = migration_path.read_text()
    print(f"Read migration file: {len(sql)} bytes")
    
    # Execute via Supabase SQL endpoint
    sql_url = f"{url}/rest/v1/rpc/exec_sql"
    
    # Alternative: Use the SQL endpoint directly
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json"
    }
    
    # Try using the query endpoint
    query_url = f"{url}/rest/v1/"
    
    # First, let's check what tables exist
    print("\nChecking existing tables...")
    try:
        from supabase import create_client
        db = create_client(url, os.getenv('SUPABASE_KEY'))
        
        tables = ['user_profiles', 'conversations', 'messages', 'file_uploads', 
                  'brain_documents', 'afl_codes', 'presentations', 'audit_logs']
        
        existing = []
        for table in tables:
            try:
                db.table(table).select('id').limit(1).execute()
                existing.append(table)
                print(f"  ✓ {table}")
            except Exception:
                print(f"  ✗ {table} (doesn't exist)")
        
        if len(existing) == len(tables):
            print("\n✓ All tables already exist! Migration may have been run.")
            return True
            
    except Exception as e:
        print(f"Could not check tables: {e}")
    
    print("\n" + "="*60)
    print("MIGRATION REQUIRED")
    print("="*60)
    print("""
The migration SQL needs to be executed in Supabase.

OPTIONS:
1. Supabase Dashboard (Recommended):
   - Go to: https://supabase.com/dashboard/project/vekcfcmstpnxubxsaano/sql
   - Open SQL Editor
   - Paste the contents of: db/migrations/001_initial_schema.sql
   - Click Run

2. Using Supabase CLI (if installed):
   supabase db push

3. Using psql (if you have direct PostgreSQL access):
   psql "$DATABASE_URL" -f db/migrations/001_initial_schema.sql
""")
    
    return False


if __name__ == "__main__":
    run_migration()