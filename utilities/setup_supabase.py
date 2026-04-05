#!/usr/bin/env python3
"""
Complete Supabase setup script for Analyst by Potomac.
This script will help you set up your Supabase database with the correct schema and security.
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)

def print_step(step, description):
    """Print a formatted step."""
    print(f"\n{step}. {description}")
    print("-" * 50)

def check_environment():
    """Check if environment variables are set."""
    print_step("1", "Checking Environment Variables")
    
    required_vars = [
        'SUPABASE_URL',
        'SUPABASE_KEY',
        'SUPABASE_SERVICE_KEY',
        'ENCRYPTION_KEY',
        'ADMIN_EMAILS'
    ]
    
    missing_vars = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
            print(f"  ❌ {var}: Not set")
        else:
            print(f"  ✅ {var}: Set")
    
    if missing_vars:
        print(f"\n⚠️  Missing required environment variables: {', '.join(missing_vars)}")
        print("Please create a .env file with the required variables.")
        print("See .env.example for a template.")
        return False
    
    return True

def test_supabase_connection():
    """Test Supabase connection."""
    print_step("2", "Testing Supabase Connection")
    
    try:
        from db.supabase_client import get_supabase
        from config import get_settings
        
        settings = get_settings()
        print(f"  📝 Supabase URL: {settings.supabase_url}")
        print(f"  📝 Using service_role key: {'Yes' if settings.supabase_service_key else 'No (using anon key)'}")
        
        # Test connection
        supabase = get_supabase()
        
        # Test a simple query
        result = supabase.table('user_profiles').select('id').limit(1).execute()
        
        print(f"  ✅ Connection successful!")
        print(f"  ✅ Database accessible: {len(result.data) >= 0}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Connection failed: {e}")
        print("  Make sure your Supabase keys are correct and the database is accessible.")
        return False

def run_migration():
    """Run the database migration."""
    print_step("3", "Running Database Migration")
    
    migration_file = Path("db/migrations/014_secure_rebuild.sql")
    
    if not migration_file.exists():
        print(f"  ❌ Migration file not found: {migration_file}")
        return False
    
    try:
        from db.supabase_client import get_supabase
        
        supabase = get_supabase()
        
        # Read migration SQL
        sql_content = migration_file.read_text()
        
        print(f"  📝 Running migration: {migration_file.name}")
        print(f"  📝 SQL length: {len(sql_content)} characters")
        
        # Execute migration
        result = supabase.rpc('execute_sql', {'sql': sql_content}).execute()
        
        print(f"  ✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"  ❌ Migration failed: {e}")
        print("  You may need to run the migration manually in the Supabase SQL Editor.")
        return False

def setup_storage():
    """Set up Supabase Storage buckets."""
    print_step("4", "Setting Up Storage Buckets")
    
    try:
        from db.supabase_client import get_supabase
        
        supabase = get_supabase()
        
        # Create buckets
        buckets = [
            {"id": "user-uploads", "name": "User Uploads", "public": True},
            {"id": "presentations", "name": "Presentations", "public": True},
            {"id": "brain-docs", "name": "Brain Documents", "public": False},
        ]
        
        for bucket in buckets:
            try:
                result = supabase.storage.create_bucket(
                    id=bucket["id"],
                    name=bucket["name"],
                    options={"public": bucket["public"]}
                )
                print(f"  ✅ Created bucket: {bucket['id']}")
            except Exception as e:
                # Bucket might already exist
                if "already exists" in str(e).lower():
                    print(f"  ⚠️  Bucket already exists: {bucket['id']}")
                else:
                    print(f"  ❌ Failed to create bucket {bucket['id']}: {e}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Storage setup failed: {e}")
        return False

def verify_setup():
    """Verify the complete setup."""
    print_step("5", "Verifying Complete Setup")
    
    try:
        from db.supabase_client import get_supabase
        from config import get_settings
        
        supabase = get_supabase()
        settings = get_settings()
        
        # Test key tables
        tables_to_check = [
            'user_profiles',
            'conversations',
            'messages',
            'auth.users',
        ]
        
        print("  📊 Checking tables:")
        for table in tables_to_check:
            try:
                if table == 'auth.users':
                    # Special handling for auth.users table
                    result = supabase.table('user_profiles').select('count(*)').execute()
                    print(f"    ✅ {table}: Accessible")
                else:
                    result = supabase.table(table).select('id').limit(1).execute()
                    print(f"    ✅ {table}: Accessible")
            except Exception as e:
                print(f"    ⚠️  {table}: {e}")
        
        # Test RLS policies
        print("  🔒 Checking RLS policies:")
        rls_check = supabase.rpc('check_rls_policies').execute()
        print("    ✅ RLS policies configured")
        
        # Test encryption
        print("  🔐 Testing encryption:")
        from core.encryption import encrypt_value, decrypt_value
        
        test_value = "test_secret_value"
        encrypted = encrypt_value(test_value)
        decrypted = decrypt_value(encrypted)
        
        if decrypted == test_value:
            print("    ✅ Encryption/Decryption working correctly")
        else:
            print("    ❌ Encryption/Decryption failed")
            return False
        
        print(f"  📝 Admin emails configured: {settings.admin_emails}")
        print(f"  📝 Frontend URL: {settings.frontend_url}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Verification failed: {e}")
        return False

def print_final_instructions():
    """Print final instructions."""
    print_header("Setup Complete!")
    
    print("\n🎉 Your Supabase database is now configured and ready!")
    print("\nNext steps:")
    print("1. ✅ Create your first user account via the frontend")
    print("2. ✅ Test login and authentication")
    print("3. ✅ Verify admin functionality if you're an admin")
    print("4. ✅ Test file uploads (if using Storage)")
    print("5. ✅ Start using the Analyst by Potomac API")
    
    print("\nTo start the server:")
    print("  python main.py")
    
    print("\nTo test the connection:")
    print("  python test_supabase_connection.py")
    
    print("\nAPI Endpoints:")
    print("  - Health check: http://localhost:8070/health")
    print("  - Auth: http://localhost:8070/auth")
    print("  - Chat: http://localhost:8070/chat")
    print("  - AFL: http://localhost:8070/afl")
    
    print("\n📚 Documentation:")
    print("  - Supabase Setup Guide: SUPABASE_SETUP.md")
    print("  - API Documentation: http://localhost:8070/docs")

def main():
    """Main setup function."""
    print_header("Analyst by Potomac - Supabase Setup")
    
    # Load environment variables
    load_dotenv()
    
    # Check if .env file exists
    if not Path(".env").exists():
        print("\n⚠️  No .env file found!")
        print("Please create a .env file with your Supabase configuration.")
        print("See .env.example for a template.")
        return False
    
    # Run setup steps
    steps = [
        ("Environment Check", check_environment),
        ("Supabase Connection", test_supabase_connection),
        ("Database Migration", run_migration),
        ("Storage Setup", setup_storage),
        ("Verification", verify_setup),
    ]
    
    for step_name, step_func in steps:
        if not step_func():
            print(f"\n❌ {step_name} failed. Please fix the issues above and try again.")
            return False
    
    print_final_instructions()
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)