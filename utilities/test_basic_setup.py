#!/usr/bin/env python3
"""
Basic setup test - verifies imports and basic functionality without requiring environment variables.
"""

import os
import sys

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    try:
        # Test core modules
        from config import get_settings
        print("  OK config module")
        
        from db.supabase_client import get_supabase
        print("  OK supabase_client module")
        
        from core.encryption import encrypt_value, decrypt_value
        print("  OK encryption module")
        
        # Test API modules
        from api.routes import auth
        print("  OK auth routes")
        
        from api.routes import chat
        print("  OK chat routes")
        
        from api.routes import afl
        print("  OK afl routes")
        
        from api.dependencies import get_current_user
        print("  OK dependencies")
        
        return True
        
    except Exception as e:
        print(f"  ERROR Import failed: {e}")
        return False

def test_encryption_without_key():
    """Test encryption functionality without a key."""
    print("\nTesting encryption (without key)...")
    
    try:
        from core.encryption import encrypt_value, decrypt_value
        
        # This should fail gracefully
        try:
            encrypted = encrypt_value("test")
            print("  WARNING Encryption worked without key (unexpected)")
        except Exception as e:
            if "ENCRYPTION_KEY is not set" in str(e):
                print("  OK Encryption correctly requires key")
                return True
            else:
                print(f"  ERROR Unexpected encryption error: {e}")
                return False
        
    except Exception as e:
        print(f"  ERROR Encryption test failed: {e}")
        return False

def test_config_without_env():
    """Test config loading without environment variables."""
    print("\nTesting config (without env vars)...")
    
    try:
        from config import get_settings
        settings = get_settings()
        
        # Should have default empty values
        if not settings.supabase_url:
            print("  OK Config loads with empty defaults")
            return True
        else:
            print("  WARNING Config has non-empty defaults")
            return True
            
    except Exception as e:
        print(f"  ERROR Config test failed: {e}")
        return False

def main():
    """Run basic setup tests."""
    print("Basic Setup Test - No environment variables required\n")
    
    tests = [
        ("Imports", test_imports),
        ("Encryption", test_encryption_without_key),
        ("Config", test_config_without_env),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"Running {test_name} test...")
        if test_func():
            passed += 1
        print()
    
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("Basic setup is working! Now create your .env file with Supabase credentials.")
        print("\nTo proceed:")
        print("1. Create .env file with your Supabase keys")
        print("2. Run: python test_supabase_connection.py")
        print("3. Run: python setup_supabase.py")
        print("4. Start server: python main.py")
    else:
        print("Some basic tests failed. Check the errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)