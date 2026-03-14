# Supabase Setup Guide

This guide will help you connect your Analyst by Potomac project to your Supabase database with default Supabase Auth.

## Prerequisites

1. Your Supabase project URL: `https://hqpjagbcfdxcpaoovzwk.supabase.co`
2. Access to your Supabase Dashboard
3. Python environment with the project dependencies installed

## Step 1: Get Your Supabase API Keys

1. Go to your Supabase Dashboard: https://app.supabase.com/project/hqpjagbcfdxcpaoovzwk
2. Navigate to **Settings** → **API**
3. Copy the following keys:
   - **Project URL**: `https://hqpjagbcfdxcpaoovzwk.supabase.co`
   - **anon/public key**: (starts with `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`)
   - **service_role key**: (starts with `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`)

## Step 2: Create Environment Variables

Create a `.env` file in your project root directory with the following content:

```bash
# Supabase Configuration
SUPABASE_URL=https://hqpjagbcfdxcpaoovzwk.supabase.co
SUPABASE_KEY=your_anon_public_key_here
SUPABASE_SERVICE_KEY=your_service_role_key_here

# Admin Configuration (comma-separated list of admin emails)
ADMIN_EMAILS=your-email@example.com,admin2@example.com

# Data Encryption Key (generate a secure 32-byte key)
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
ENCRYPTION_KEY=your_32_byte_encryption_key_here

# Optional: Server-side API keys (if you want to provide fallback keys)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here

# SMTP Settings for Password Reset (optional)
SMTP_SENDER_EMAIL=your-email@gmail.com
SMTP_PASSWORD=your_app_password_here

# Frontend URL for Password Reset Links
FRONTEND_URL=https://analystbypotomac.vercel.app

# Optional: Researcher API keys
FINNHUB_API_KEY=your_finnhub_api_key_here
FRED_API_KEY=your_fred_api_key_here
NEWSAPI_KEY=your_newsapi_key_here
```

## Step 3: Database Setup

### Option A: Use Existing Database Schema (Recommended)

Your project already includes migration files in `db/migrations/`. The latest migration is `014_secure_rebuild.sql` which includes:

- Supabase Auth integration
- User profiles table with RLS policies
- All necessary tables for the application
- Security hardening

### Option B: Manual Database Setup

If you need to set up the database manually:

1. Go to your Supabase Dashboard
2. Navigate to **Database** → **SQL Editor**
3. Run the migration scripts from `db/migrations/014_secure_rebuild.sql`

## Step 4: Configure Supabase Auth

1. Go to **Authentication** → **Settings** in your Supabase Dashboard
2. Configure the following settings:

### Email Configuration (Optional but Recommended)
- Enable email signups
- Configure SMTP settings for email delivery
- Set up email templates for confirmation and password reset

### Security Settings
- **Rate limiting**: Keep default settings
- **Email templates**: Customize if needed
- **Redirect URLs**: Add your frontend URL: `https://analystbypotomac.vercel.app`

### Providers
- **Email**: Enable (default)
- **Social providers**: Optional (Google, GitHub, etc.)

## Step 5: Set Up Storage (Optional)

If you need file upload functionality:

1. Go to **Storage** → **Buckets** in your Supabase Dashboard
2. Create a bucket named `user-uploads`
3. Set the bucket to **Public** access
4. Configure RLS policies for file access

## Step 6: Test the Connection

Run the following Python script to test your Supabase connection:

```python
import os
from dotenv import load_dotenv
from db.supabase_client import get_supabase

# Load environment variables
load_dotenv()

try:
    # Test connection
    supabase = get_supabase()
    
    # Test a simple query
    result = supabase.table('user_profiles').select('id').limit(1).execute()
    
    print("✅ Supabase connection successful!")
    print(f"Database accessible: {len(result.data) >= 0}")
    
except Exception as e:
    print(f"❌ Supabase connection failed: {e}")
```

## Step 7: Run Migrations

Execute the migration script to set up your database schema:

```bash
python scripts/migrate_via_mcp.py
```

Or run the migration directly:

```python
from scripts.execute_migration import execute_migration

# Execute the latest migration
execute_migration("014_secure_rebuild.sql")
```

## Step 8: Start Your Application

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python main.py
```

## Troubleshooting

### Common Issues

1. **"Invalid credentials" errors**: Check that your `SUPABASE_KEY` and `SUPABASE_SERVICE_KEY` are correct
2. **"Table not found" errors**: Run the migration script to create the database schema
3. **"Permission denied" errors**: Ensure RLS policies are properly configured
4. **"Connection timeout" errors**: Check your internet connection and Supabase project status

### Environment Variable Verification

Verify your environment variables are loaded correctly:

```python
from config import get_settings

settings = get_settings()
print(f"Supabase URL: {settings.supabase_url}")
print(f"Supabase Key: {settings.supabase_key[:20]}...")
print(f"Service Key: {settings.supabase_service_key[:20]}...")
print(f"Admin Emails: {settings.admin_emails}")
```

### Database Health Check

Use the built-in health endpoint:

```bash
curl http://localhost:8070/health
```

## Security Notes

1. **Never commit your `.env` file** to version control
2. **Use strong encryption keys** for `ENCRYPTION_KEY`
3. **Restrict API key access** - only provide necessary permissions
4. **Monitor your Supabase usage** in the dashboard
5. **Enable RLS policies** for all tables (included in migration)

## Next Steps

1. Test user registration and login
2. Verify admin functionality
3. Test file uploads (if using Storage)
4. Configure any additional Supabase features you need
5. Deploy to production with proper environment variables

## Support

If you encounter issues:

1. Check the Supabase Dashboard for error logs
2. Review the application logs for detailed error messages
3. Verify all environment variables are correctly set
4. Ensure your Supabase project has sufficient quota