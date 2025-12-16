import os
import shutil
import sqlite3
from datetime import datetime

from config import Config
from database import init_db


def main():
    db_path = Config.DB_NAME
    print(f"Using database file: {db_path}")

    # 1. Backup existing DB if it exists
    if os.path.exists(db_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base, ext = os.path.splitext(db_path)
        backup_path = f"{base}_backup_{timestamp}{ext or '.db'}"
        try:
            shutil.copy2(db_path, backup_path)
            print(f"Backup created successfully at: {backup_path}")
        except Exception as e:
            print(f"ERROR: Failed to create backup: {e}")
            return
    else:
        print("No existing database file found. Skipping backup.")

    # 2. Apply migrations and initialize inventory via init_db
    try:
        print("Running init_db() to apply migrations and initialize inventory tables...")
        init_db()
        print("init_db() completed.")
    except Exception as e:
        print(f"ERROR: init_db() failed: {e}")
        return

    # 3. Verify that price_settings table exists
    print("Verifying that 'price_settings' table exists...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_settings'")
        row = cursor.fetchone()
        if row:
            print("Verification OK: 'price_settings' table exists in the database.")
        else:
            print("WARNING: 'price_settings' table does NOT exist after migrations.")
    except Exception as e:
        print(f"ERROR: Failed to verify 'price_settings' table: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
