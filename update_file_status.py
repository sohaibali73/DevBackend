#!/usr/bin/env python3
"""
Script to update file upload status for files that don't have extracted_text
"""

from db.supabase_client import get_supabase

def update_file_status():
    """Update status for files without extracted_text"""
    print("Connecting to Supabase...")
    db = get_supabase()
    
    print("Fetching files without extracted_text...")
    rows = db.table("file_uploads").select("id, original_filename, status").is_("extracted_text", "null").execute()
    
    updated_count = 0
    
    print(f"Found {len(rows.data or [])} files without extracted_text")
    
    for r in rows.data or []:
        print(f"Updating status for: {r['original_filename']}")
        try:
            db.table("file_uploads").update({"status": "error", "extracted_text": ""}).eq("id", r["id"]).execute()
            updated_count += 1
            print(f"Updated: {r['original_filename']}")
        except Exception as e:
            print(f"Error updating {r['original_filename']}: {e}")
            continue
    
    print(f"\nSummary:")
    print(f"Updated: {updated_count} files")

if __name__ == "__main__":
    update_file_status()