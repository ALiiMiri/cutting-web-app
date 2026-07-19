import sqlite3

def apply(conn):
    """
    Adds min_waste column to profile_types table.
    This column specifies the minimum waste threshold for each profile type.
    """
    print("--- Applying migration: 011_add_min_waste_to_profile_types ---")
    cursor = conn.cursor()
    try:
        # بررسی وجود ستون min_waste
        cursor.execute("PRAGMA table_info(profile_types)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'min_waste' not in columns:
            print("   Adding min_waste column to profile_types table...")
            cursor.execute("ALTER TABLE profile_types ADD COLUMN min_waste REAL DEFAULT 20")
            print("   min_waste column added successfully.")
        else:
            print("   min_waste column already exists, skipping...")
        
        print("--- Migration 011_add_min_waste_to_profile_types applied successfully. ---")
    except Exception as e:
        print(f"!!! FAILED to apply migration 011_add_min_waste_to_profile_types: {e}")
        raise
