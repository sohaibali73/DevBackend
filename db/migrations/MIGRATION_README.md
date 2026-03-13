# Database Migrations

## Migration Strategy

This project uses Supabase PostgreSQL with a clean migration strategy.

### ⚠️ IMPORTANT: Clean Slate Migration

**For fresh installations:** Run ONLY `001_initial_schema.sql`.

**For existing projects:** Do NOT run `001_initial_schema.sql` on a database with existing user data. Use the incremental migrations (002-014) instead.

---

## Migration Files

### Primary Migration

| File | Description |
|------|-------------|
| `001_initial_schema.sql` | **Complete schema for fresh installations.** Contains all tables, indexes, RLS policies, triggers, and storage bucket definitions. |

### Legacy Migrations (Incremental)

These files are preserved for existing deployments that need to migrate incrementally:

| File | Description |
|------|-------------|
| `002_feedback_analytics.sql` | Feedback and analytics tables |
| `003-008` | (Reserved for future use) |
| `009_brain_tables_and_embeddings.sql` | Knowledge base tables |
| `010_supabase_auth_migration.sql` | Auth system migration |
| `011_fix_foreign_keys.sql` | Foreign key fixes |
| `012_clean_slate_auth_fix.sql` | Auth fixes |
| `014_secure_rebuild.sql` | RLS policy rebuild |

---

## Fresh Installation

### Prerequisites

1. A Supabase project (create at https://supabase.com)
2. Access to the SQL Editor in Supabase Dashboard

### Steps

1. **Open Supabase SQL Editor**
   - Go to your Supabase project dashboard
   - Navigate to SQL Editor

2. **Run the Migration**
   ```sql
   -- Copy and paste the contents of 001_initial_schema.sql
   -- Execute the entire script
   ```

3. **Verify Installation**
   ```sql
   -- Check tables exist
   SELECT table_name FROM information_schema.tables 
   WHERE table_schema = 'public' 
   ORDER BY table_name;
   
   -- Check RLS is enabled
   SELECT tablename, rowsecurity FROM pg_tables 
   WHERE schemaname = 'public';
   
   -- Check storage buckets
   SELECT * FROM storage.buckets;
   ```

4. **Configure Environment Variables**
   
   Update your `.env` file:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-anon-key
   SUPABASE_SERVICE_KEY=your-service-role-key
   ENCRYPTION_KEY=your-32-byte-encryption-key
   ```

---

## Schema Overview

### Core Tables

| Table | Purpose |
|-------|---------|
| `user_profiles` | Extended user data (links to auth.users) |
| `conversations` | Chat conversations |
| `messages` | Chat messages |
| `file_uploads` | File metadata (files stored in Supabase Storage) |
| `conversation_files` | Links files to conversations |
| `brain_documents` | Knowledge base documents |
| `afl_codes` | AFL code storage |
| `afl_history` | AFL generation history |
| `presentations` | Generated presentations |
| `user_feedback` | User feedback |
| `usage_events` | Usage tracking |
| `audit_logs` | Audit trail |

### Storage Buckets

| Bucket | Purpose | Max Size |
|--------|---------|----------|
| `user-uploads` | User file uploads | 50MB |
| `presentations` | Generated PPTX files | 100MB |
| `brain-docs` | Knowledge base documents | 50MB |

### Security

- **Row Level Security (RLS)** enabled on all tables
- **anon role** denied access to sensitive tables
- **authenticated users** can only access their own data
- **service_role** bypasses RLS (used by backend)
- **Audit logging** on user_profiles table

---

## Troubleshooting

### Common Errors

**"relation already exists"**
- You're running `001_initial_schema.sql` on an existing database
- Use incremental migrations instead

**"permission denied"**
- Ensure you're using the service_role key for migrations
- Check Supabase project settings

**"RLS policy violation"**
- Backend must use service_role key
- Check that policies are correctly scoped to `auth.uid()`

### Reset Database (Development Only)

```sql
-- ⚠️ WARNING: This deletes all data
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;

-- Then run 001_initial_schema.sql
```

---

## Migration Best Practices

1. **Always backup** before running migrations in production
2. **Test migrations** in a staging environment first
3. **Use transactions** when possible (not supported for all DDL)
4. **Monitor RLS policies** after deployment
5. **Keep the service_role key secure** - it bypasses all security

---

## Need Help?

- [Supabase Documentation](https://supabase.com/docs)
- [PostgreSQL Row Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- Create an issue in the project repository