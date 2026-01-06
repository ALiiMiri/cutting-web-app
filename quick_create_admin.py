# Quick admin creator
import sys
sys.path.insert(0, '.')
from werkzeug.security import generate_password_hash
import sqlite3
from config import Config

DB_NAME = Config.DB_NAME

# Create admin user
username = "admin"
password = "admin123"  # Change this!
role = "admin"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# Check if user exists
cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
if cursor.fetchone():
    print(f"User '{username}' already exists!")
    conn.close()
    sys.exit(0)

# Create user
password_hash = generate_password_hash(password)
cursor.execute(
    "INSERT INTO users (username, password_hash, role, is_active, must_change_password) VALUES (?, ?, ?, 1, 0)",
    (username, password_hash, role)
)

conn.commit()
conn.close()

print(f"Admin user created successfully!")
print(f"Username: {username}")
print(f"Password: {password}")
print(f"Role: {role}")
