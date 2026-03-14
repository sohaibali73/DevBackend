# Quick Start Guide

Get your Analyst by Potomac project connected to Supabase in 5 minutes.

## Prerequisites

- Python 3.8+
- Your Supabase project URL: `https://hqpjagbcfdxcpaoovzwk.supabase.co`
- Access to your Supabase Dashboard

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

## Step 2: Configure Environment

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your Supabase credentials:
```bash
# Get these from: Supabase Dashboard → Settings → API
SUPABASE_URL=https://hqpjagbcfdxcpaoovzwk.supabase.co
SUPABASE_KEY=your_anon_public_key_here
SUPABASE_SERVICE_KEY=your_service_role_key_here

# Generate a secure encryption key
ENCRYPTION_KEY=your_32_byte_encryption_key_here

# Your admin email
ADMIN_EMAILS=your-email@example.com
```

## Step 3: Set Up Database

Run the automated setup script:
```bash
python setup_supabase.py
```

Or manually run the migration in Supabase SQL Editor:
```sql
-- Copy and paste the contents of db/migrations/014_secure_rebuild.sql
-- into Supabase Dashboard → SQL Editor → New query → Run
```

## Step 4: Test Connection

```bash
python test_supabase_connection.py
```

Expected output:
```
✅ All tests passed! Your Supabase connection is ready.
```

## Step 5: Start the Server

```bash
python main.py
```

The server will start on `http://localhost:8070`

## Verify Everything Works

1. **Health Check**: `curl http://localhost:8070/health`
2. **API Docs**: Visit `http://localhost:8070/docs`
3. **Test Registration**: Use the auth endpoints to create a test user

## Key Features Configured

✅ **Supabase Auth**: Full email/password authentication  
✅ **User Profiles**: Automatic profile creation with RLS policies  
✅ **Admin System**: Admin users based on email configuration  
✅ **API Key Management**: Encrypted storage of user API keys  
✅ **Database Security**: Row-level security with proper access controls  
✅ **Storage Buckets**: File upload support (user-uploads, presentations, brain-docs)  

## Next Steps

1. Connect your frontend to `http://localhost:8070`
2. Test user registration and login
3. Verify admin functionality
4. Configure any additional Supabase features you need

## Troubleshooting

**"Invalid credentials"**: Check your Supabase keys in `.env`  
**"Table not found"**: Run the migration script  
**"Connection timeout"**: Check your internet connection and Supabase project status  

## Support

- Detailed setup guide: `SUPABASE_SETUP.md`
- Test script: `test_supabase_connection.py`
- Setup script: `setup_supabase.py`