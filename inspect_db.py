import sqlite3
import os
import traceback

print("Available databases:")
for file in os.listdir():
    if file.endswith(".db"):
        print(f" - {file}")

# Try both databases
databases = ["cutting.db", "cutting_web_data.db"]

for db_name in databases:
    print(f"\n\n==== Inspecting database: {db_name} ====")
    
    try:
        if not os.path.exists(db_name):
            print(f"Error: Database file {db_name} does not exist")
            continue
            
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()

        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()

        print(f"\nTables in {db_name}:")
        for table in tables:
            print(f" - {table[0]}")
            
            # Print column info for each table
            try:
                cursor.execute(f"PRAGMA table_info({table[0]})")
                columns = cursor.fetchall()
                print(f"   Columns in {table[0]}:")
                for col in columns:
                    print(f"   - {col}")
            except Exception as e:
                print(f"   Error getting columns: {e}")

        # Check if custom_columns exists
        if ('custom_columns',) in tables:
            cursor.execute("SELECT * FROM custom_columns")
            columns = cursor.fetchall()
            print(f"\nRecords in custom_columns ({len(columns)}):")
            for col in columns:
                print(f" - {col}")
        else:
            print("\nThe 'custom_columns' table does not exist!")

        conn.close()
    except Exception as e:
        print(f"Error inspecting {db_name}: {e}")
        traceback.print_exc() 