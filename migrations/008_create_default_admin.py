import sqlite3
import os
import secrets
from werkzeug.security import generate_password_hash

def apply(conn):
    """
    Creates default admin user if it doesn't exist.
    Default credentials: admin / admin
    """
    print("--- Applying migration: 008_create_default_admin ---")
    cursor = conn.cursor()
    try:
        # Check if admin user exists
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if cursor.fetchone():
            print("   Admin user already exists, skipping...")
            return
        
        initial_password = os.getenv("INITIAL_ADMIN_PASSWORD") or secrets.token_urlsafe(18)
        password_hash = generate_password_hash(initial_password)
        cursor.execute("""
            INSERT INTO users (username, password_hash, role, is_active, must_change_password)
            VALUES (?, ?, 'admin', 1, 1)
        """, ('admin', password_hash))
        
        print(f"   Initial admin created. One-time password: {initial_password}")
        print("--- Migration 008_create_default_admin applied successfully. ---")
    except Exception as e:
        print(f"!!! FAILED to apply migration 008_create_default_admin: {e}")
        raise
