#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
اسکریپت برای باز کردن قفل حساب admin و reset کردن failed_login_attempts
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

def unlock_admin():
    """باز کردن قفل حساب admin"""
    print("=" * 60)
    print("Unlocking admin account and resetting failed login attempts")
    print("=" * 60)
    print()
    
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Reset failed login attempts and unlock account
        cursor.execute("""
            UPDATE users 
            SET failed_login_attempts = 0,
                locked_until = NULL,
                is_active = 1,
                must_change_password = 0
            WHERE username = 'admin'
        """)
        
        # Also reset password to 'admin' to be sure
        password_hash = generate_password_hash('admin')
        cursor.execute("""
            UPDATE users 
            SET password_hash = ?
            WHERE username = 'admin'
        """, (password_hash,))
        
        conn.commit()
        
        # Verify
        cursor.execute("""
            SELECT id, username, is_active, failed_login_attempts, locked_until, must_change_password
            FROM users 
            WHERE username = 'admin'
        """)
        user_row = cursor.fetchone()
        
        if user_row:
            user_id, username, is_active, failed_attempts, locked_until, must_change = user_row
            print("SUCCESS: Admin account unlocked and reset!")
            print()
            print("Account status:")
            print(f"  ID: {user_id}")
            print(f"  Username: {username}")
            print(f"  Active: {bool(is_active)}")
            print(f"  Failed login attempts: {failed_attempts or 0}")
            print(f"  Locked until: {locked_until or 'Not locked'}")
            print(f"  Must change password: {bool(must_change)}")
            print()
            print("Login credentials:")
            print("  Username: admin")
            print("  Password: admin")
        else:
            print("ERROR: Admin user not found!")
            # Create admin user
            password_hash = generate_password_hash('admin')
            cursor.execute("""
                INSERT INTO users (username, password_hash, role, is_active, must_change_password, failed_login_attempts, locked_until)
                VALUES (?, ?, 'admin', 1, 0, 0, NULL)
            """, ('admin', password_hash))
            conn.commit()
            print("SUCCESS: Admin user created!")
            print()
            print("Login credentials:")
            print("  Username: admin")
            print("  Password: admin")
        
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
    unlock_admin()
