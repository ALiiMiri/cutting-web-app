#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
اسکریپت برای بررسی و بازنشانی رمز عبور admin
"""
import sys
import os
import io

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

DB_NAME = Config.DB_NAME

def check_and_fix_admin():
    """بررسی و بازنشانی رمز عبور admin"""
    print("=" * 60)
    print("Checking and resetting admin password")
    print("=" * 60)
    print()
    
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # بررسی وجود کاربر admin
        cursor.execute("SELECT id, username, password_hash, is_active FROM users WHERE username = 'admin'")
        user_row = cursor.fetchone()
        
        if not user_row:
            print("ERROR: Admin user not found in database!")
            print("Creating admin user...")
            
            password_hash = generate_password_hash('admin')
            cursor.execute("""
                INSERT INTO users (username, password_hash, role, is_active, must_change_password)
                VALUES (?, ?, 'admin', 1, 0)
            """, ('admin', password_hash))
            conn.commit()
            print("SUCCESS: Admin user created!")
            print()
            print("Login credentials:")
            print("  Username: admin")
            print("  Password: admin")
            return
        
        user_id, username, password_hash, is_active = user_row
        print(f"SUCCESS: Admin user found (ID: {user_id})")
        print(f"  Active status: {'Yes' if is_active else 'No'}")
        print()
        
        # Test different passwords
        test_passwords = ['admin', 'admin123']
        matched = False
        matched_password = None
        
        print("Testing different passwords...")
        for test_pass in test_passwords:
            if check_password_hash(password_hash, test_pass):
                matched = True
                matched_password = test_pass
                print(f"SUCCESS: Password '{test_pass}' is correct!")
                break
        
        if not matched:
            print("ERROR: None of the tested passwords are correct!")
            print("Resetting password to 'admin'...")
            
            # Reset password to admin
            new_password_hash = generate_password_hash('admin')
            cursor.execute("""
                UPDATE users 
                SET password_hash = ?, is_active = 1, must_change_password = 0
                WHERE username = 'admin'
            """, (new_password_hash,))
            conn.commit()
            
            print("SUCCESS: Password reset!")
            print()
            print("Login credentials:")
            print("  Username: admin")
            print("  Password: admin")
        else:
            print()
            print("Login credentials:")
            print(f"  Username: admin")
            print(f"  Password: {matched_password}")
            
            # Ensure account is active
            if not is_active:
                print()
                print("WARNING: Account is inactive. Activating...")
                cursor.execute("UPDATE users SET is_active = 1 WHERE username = 'admin'")
                conn.commit()
                print("SUCCESS: Account activated!")
        
        print()
        print("=" * 60)
        print("SUCCESS: Operation completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_and_fix_admin()
