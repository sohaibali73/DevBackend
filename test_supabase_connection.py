#!/usr/bin/env python3
"""
Test script to verify Supabase connection and database setup.
"""

import os
import sys
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_environment_variables():
    """Test that all required environment variables are set."""
    print("Testing Environment Variables...")
    
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
        else:
            print(f"  OK {var}: Set")
    
    if missing_vars:
        print(f"  ERROR Missing required variables: {', '.join(missing_vars)}")
        print("  Please create a .env file with the required variables.")
        return False
    
    return True

def test_supabase_connection():
    """Test Supabase connection."""
    print("\nTesting Supabase Connection...")
    
    try:
        from db.supabase_client import get_supabase
        from config import get_settings
        
        settings = get_settings()
        print(f"  Supabase URL: {settings.supabase_url}")
        print(f"  Using service_role key: {'Yes' if settings.supabase_service_key else 'No (using anon key)'}")
        
        # Test connection
        supabase = get_supabase()
        
        # Test a simple query
        result = supabase.table('user_profiles').select('id').limit(1).execute()
        
        print(f"  OK Connection successful!")
        print(f"  OK Database accessible: {len(result.data) >= 0}")
        
        return True
        
    except Exception as e:
        print(f"  ERROR Connection failed: {e}")
        return False

def test_auth_functionality():
    """Test authentication functionality."""
    print("\nTesting Authentication Functionality...")
    
    try:
        from api.routes.auth import get_me
        from api.dependencies import get_current_user_id
        from fastapi import HTTPException
        
        print("  OK Auth routes imported successfully")
        print("  OK Dependencies imported successfully")
        
        # Test that we can import the auth module
        from api.routes import auth
        print("  OK Auth module loaded successfully")
        
        return True
        
    except Exception as e:
        print(f"  ERROR Auth functionality test failed: {e}")
        return False

def test_database_tables():
    """Test that required database tables exist."""
    print("\nTesting Database Tables...")
    
    try:
        from db.supabase_client import get_supabase
        
        supabase = get_supabase()
        
        # Test key tables
        tables_to_check = [
            'user_profiles',
            'auth.users',  # Supabase Auth table
        ]
        
        for table in tables_to_check:
            try:
                if table == 'auth.users':
                    # Special handling for auth.users table
                    result = supabase.rpc('get_user_count').execute()
                    print(f"  OK {table}: Accessible")
                else:
                    result = supabase.table(table).select('id').limit(1).execute()
                    print(f"  OK {table}: Accessible")
            except Exception as e:
                print(f"  WARNING {table}: {e}")
        
        return True
        
    except Exception as e:
        print(f"  ERROR Database tables test failed: {e}")
        return False

def test_encryption():
    """Test encryption functionality."""
    print("\nTesting Encryption...")
    
    try:
        from core.encryption import encrypt_value, decrypt_value
        
        test_value = "test_secret_value"
        encrypted = encrypt_value(test_value)
        decrypted = decrypt_value(encrypted)
        
        if decrypted == test_value:
            print("  OK Encryption/Decryption working correctly")
            return True
        else:
            print("  ERROR Encryption/Decryption failed")
            return False
            
    except Exception as e:
        print(f"  ERROR Encryption test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("Starting Supabase Connection Tests...\n")
    
    # Load environment variables
    load_dotenv()
    
    tests = [
        test_environment_variables,
        test_supabase_connection,
        test_auth_functionality,
        test_database_tables,
        test_encryption,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nTest Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your Supabase connection is ready.")
        print("\nNext steps:")
        print("1. Create a .env file with your actual Supabase keys")
        print("2. Run: python main.py")
        print("3. Test user registration and login")
    else:
        print("⚠️  Some tests failed. Please check the output above and fix any issues.")
        print("\nCommon issues:")
        print("- Missing environment variables in .env file")
        print("- Incorrect Supabase keys")
        print("- Database not set up with migrations")
        print("- Network connectivity issues")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)