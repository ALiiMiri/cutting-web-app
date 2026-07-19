"""Setup script to run migrations and create admin user"""
import sqlite3
from werkzeug.security import generate_password_hash
from db_migrations import apply_migrations

print("="*60)
print("Authentication System Setup")
print("="*60)

# Step 1: Run migrations
print("\n[1/3] Running database migrations...")
try:
    conn = sqlite3.connect('cutting.db')
    apply_migrations(conn)
    conn.close()
    print("SUCCESS: Migrations completed!")
except Exception as e:
    print(f"ERROR: Migration failed - {e}")
    exit(1)

# Step 2: Check if users table exists
print("\n[2/3] Verifying users table...")
conn = sqlite3.connect('cutting.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
if not cursor.fetchone():
    print("ERROR: Users table was not created!")
    conn.close()
    exit(1)

print("SUCCESS: Users table exists!")

# Step 3: Create admin user
print("\n[3/3] Creating admin user...")

# Check if admin already exists
cursor.execute("SELECT id FROM users WHERE username = 'admin'")
if cursor.fetchone():
    print("INFO: Admin user already exists")
    # Update password just in case
    password_hash = generate_password_hash('admin123')
    cursor.execute("""
        UPDATE users 
        SET password_hash = ?, must_change_password = 0, is_active = 1, role = 'admin'
        WHERE username = 'admin'
    """, (password_hash,))
    conn.commit()
    print("SUCCESS: Admin password reset to 'admin123'")
else:
    # Create new admin user
    password_hash = generate_password_hash('admin123')
    cursor.execute("""
        INSERT INTO users (username, password_hash, role, is_active, must_change_password)
        VALUES (?, ?, 'admin', 1, 0)
    """, ('admin', password_hash))
    conn.commit()
    print("SUCCESS: Admin user created!")

conn.close()

print("\n" + "="*60)
print("Setup completed successfully!")
print("="*60)
print("\nAdmin credentials:")
print("  Username: admin")
print("  Password: admin123")
print("\nYou can now login at: http://127.0.0.1:5000/auth/login")
print("="*60)
