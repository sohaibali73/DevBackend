#!/usr/bin/env python3
"""
Script to process file uploads and extract text for files that don't have extracted_text
"""

from db.supabase_client import get_supabase
from api.routes.upload import _extract_text, _read_file
import os

def process_file_uploads():
    """Process file uploads that don't have extracted_text"""
    print("Connecting to Supabase...")
    db = get_supabase()
    
    print("Fetching files without extracted_text...")
    rows = db.table("file_uploads").select("id, original_filename, content_type, storage_path").is_("extracted_text", "null").execute()
    
    processed_count = 0
    skipped_count = 0
    
    print(f"Found {len(rows.data or [])} files to process")
    
    for r in rows.data or []:
        storage_path = r.get("storage_path", "")
        if not storage_path:
            skipped_count += 1
            print(f"Skipped (no storage path): {r['original_filename']}")
            continue
            
        print(f"Processing: {r['original_filename']} (storage_path: {storage_path})")
        
        # Files are stored locally in Railway, use the storage_path directly
        try:
            # Check if the file exists locally
            if not os.path.exists(storage_path):
                skipped_count += 1
                print(f"Skipped (file not found locally): {r['original_filename']}")
                continue
                
            print(f"Reading file: {storage_path}")
            raw = _read_file(storage_path)
            
            if not raw:
                skipped_count += 1
                print(f"Skipped (empty file): {r['original_filename']}")
                continue
                
            text = _extract_text(raw, r.get("content_type",""), r.get("original_filename",""))
            text = text.replace("\x00","").strip()
            
            if text:
                db.table("file_uploads").update({"extracted_text": text, "status": "ready"}).eq("id", r["id"]).execute()
                processed_count += 1
                print(f"Done: {r['original_filename']}")
            else:
                skipped_count += 1
                print(f"Skipped (no text extracted): {r['original_filename']}")
                
        except Exception as e:
            skipped_count += 1
            print(f"Skipped (error: {e}): {r['original_filename']}")
            continue
    
    print(f"\nSummary:")
    print(f"Processed: {processed_count} files")
    print(f"Skipped: {skipped_count} files")

if __name__ == "__main__":
    process_file_uploads()
