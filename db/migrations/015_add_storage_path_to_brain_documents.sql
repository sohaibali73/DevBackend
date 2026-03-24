-- Migration 015: Add storage_path column to brain_documents
-- Fixes: Upload endpoint inserts storage_path but the column was never created
-- Date: 2026-03-24

-- Add the missing storage_path column
ALTER TABLE brain_documents
ADD COLUMN IF NOT EXISTS storage_path TEXT;

-- Add index for looking up documents by storage path
CREATE INDEX IF NOT EXISTS idx_brain_documents_storage_path
ON brain_documents(storage_path)
WHERE storage_path IS NOT NULL;
