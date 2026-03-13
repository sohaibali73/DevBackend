# PostgreSQL Policy Syntax Fix

## Issue Summary

**Problem**: PostgreSQL (and Supabase) does not support `CREATE POLICY IF NOT EXISTS` syntax.

**Error**: SQL parser flags the word `NOT` as a syntax error when using `CREATE POLICY IF NOT EXISTS`.

**Root Cause**: The `IF NOT EXISTS` clause is not part of the PostgreSQL `CREATE POLICY` statement syntax. It's only available for certain DDL statements like `CREATE TABLE` or `CREATE INDEX`.

## What Was Fixed

All instances of `CREATE POLICY IF NOT EXISTS` have been changed to `CREATE POLICY` in the following files:

### 1. db/migrations/001_training_data.sql
- ✅ Fixed: "Anyone can read active training data" policy
- ✅ Fixed: "Admins can manage all training data" policy

### 2. db/migrations/002_feedback_analytics.sql
- ✅ Fixed: "Users can read own feedback" policy
- ✅ Fixed: "Users can create feedback" policy
- ✅ Fixed: "Admins can read all feedback" policy
- ✅ Fixed: "Admins can update feedback" policy
- ✅ Fixed: "Users can read own suggestions" policy
- ✅ Fixed: "Users can create suggestions" policy
- ✅ Fixed: "Admins can manage suggestions" policy
- ✅ Fixed: "Users can create events" policy
- ✅ Fixed: "Admins can read events" policy
- ✅ Fixed: "Admins can manage metrics" policy

**Total**: 12 policies fixed across 2 migration files

## How to Use the Fixed Migrations

### First-Time Setup
Run the migrations in order:
```sql
-- 1. Run in Supabase SQL Editor
\i db/migrations/001_training_data.sql

-- 2. Then run
\i db/migrations/002_feedback_analytics.sql
```

### If Policies Already Exist
If you've already run these migrations and policies exist, you have two options:

#### Option 1: Drop and Recreate (Recommended)
```sql
-- Drop existing policies first
DROP POLICY IF EXISTS "Anyone can read active training data" ON training_data;
DROP POLICY IF EXISTS "Admins can manage all training data" ON training_data;
-- ... (drop all other policies)

-- Then run the migration files again
```

#### Option 2: Skip Policies During Re-run
Comment out the policy creation sections if you only need to update other parts of the migration.

## Best Practices for PostgreSQL Policies

### ✅ DO
```sql
-- Correct: Plain CREATE POLICY
CREATE POLICY "policy_name"
    ON table_name FOR SELECT
    USING (condition);
```

### ❌ DON'T
```sql
-- Wrong: IF NOT EXISTS is not supported
CREATE POLICY IF NOT EXISTS "policy_name"
    ON table_name FOR SELECT
    USING (condition);
```

### Idempotent Policy Creation Pattern
If you need idempotent migrations, use this pattern:

```sql
-- Drop if exists, then create
DROP POLICY IF EXISTS "policy_name" ON table_name;
CREATE POLICY "policy_name"
    ON table_name FOR SELECT
    USING (condition);
```

Or use a PL/pgSQL block:

```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'table_name' 
        AND policyname = 'policy_name'
    ) THEN
        CREATE POLICY "policy_name"
            ON table_name FOR SELECT
            USING (condition);
    END IF;
END $$;
```

## Migration Status

- ✅ All syntax errors fixed
- ✅ Policies use correct PostgreSQL syntax
- ✅ Migrations ready to run on Supabase
- ✅ No `IF NOT EXISTS` clauses on policy creation

## Next Steps

1. **If policies don't exist yet**: Run the migration files as-is
2. **If policies already exist**: Use `DROP POLICY IF EXISTS` before running migrations
3. **For future migrations**: Never use `IF NOT EXISTS` with `CREATE POLICY`

## Reference Documentation

- PostgreSQL CREATE POLICY: https://www.postgresql.org/docs/current/sql-createpolicy.html
- Supabase RLS Policies: https://supabase.com/docs/guides/auth/row-level-security
- PostgreSQL pg_policies catalog: https://www.postgresql.org/docs/current/view-pg-policies.html

---
**Fixed**: January 22, 2026
**Files Modified**: 2 migration files, 12 policies corrected