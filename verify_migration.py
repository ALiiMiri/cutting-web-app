import sqlite3
import os
from database import init_db, DB_NAME

# Ensure we are testing on a clean state or existing one
print(f"Testing database initialization on: {DB_NAME}")

try:
    # Run initialization
    init_db()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Check tables
    tables_to_check = [
        "projects", "doors", "custom_columns", "inventory_logs", 
        "profile_types", "inventory_items", "inventory_pieces", "cutting_settings"
    ]
    
    print("\nChecking tables:")
    all_exist = True
    for table in tables_to_check:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if cursor.fetchone():
            print(f"[OK] Table '{table}' exists.")
        else:
            print(f"[FAIL] Table '{table}' MISSING!")
            all_exist = False
            
    # Check inventory_logs schema
    print("\nChecking inventory_logs schema:")
    cursor.execute("PRAGMA table_info(inventory_logs)")
    columns = [row[1] for row in cursor.fetchall()]
    required_columns = ["profile_type_id", "change_type", "quantity", "length", "piece_id", "project_id"]
    
    schema_ok = True
    for col in required_columns:
        if col in columns:
            print(f"[OK] Column '{col}' exists.")
        else:
            print(f"[FAIL] Column '{col}' MISSING in inventory_logs!")
            schema_ok = False
            
    if all_exist and schema_ok:
        print("\nSUCCESS: Database migration system is working correctly!")
    else:
        print("\nFAILURE: Some checks failed.")
        
    conn.close()

except Exception as e:
    print(f"\nEXCEPTION: {e}")
    import traceback
    traceback.print_exc()
