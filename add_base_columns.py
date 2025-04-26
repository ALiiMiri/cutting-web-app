import sqlite3
import traceback

DB_NAME = "cutting_web_data.db"

# Define base columns
base_columns = [
    {"column_name": "rang", "display_name": "رنگ پروفیل", "is_active": 1},
    {"column_name": "noe_profile", "display_name": "نوع پروفیل", "is_active": 1},
    {"column_name": "vaziat", "display_name": "وضعیت تولید", "is_active": 1},
    {"column_name": "lola", "display_name": "لولا", "is_active": 1},
    {"column_name": "ghofl", "display_name": "قفل", "is_active": 1},
    {"column_name": "accessory", "display_name": "اکسسوری", "is_active": 1},
    {"column_name": "kolaft", "display_name": "کلاف", "is_active": 1},
    {"column_name": "dastgire", "display_name": "دستگیره", "is_active": 1},
    {"column_name": "tozihat", "display_name": "توضیحات", "is_active": 1},
]

try:
    print(f"Connecting to database: {DB_NAME}")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # First check if table has records
    cursor.execute("SELECT COUNT(*) FROM custom_columns")
    count = cursor.fetchone()[0]
    print(f"Current record count in custom_columns: {count}")
    
    if count > 0:
        print("Table already has records. Skipping insertion.")
    else:
        print("Adding base columns to custom_columns table...")
        for column in base_columns:
            cursor.execute(
                "INSERT INTO custom_columns (column_name, display_name, is_active) VALUES (?, ?, ?)",
                (column["column_name"], column["display_name"], column["is_active"])
            )
            print(f"Added column: {column['display_name']}")
        
        conn.commit()
        print("Base columns added successfully!")
    
    # Verify the insertion
    cursor.execute("SELECT * FROM custom_columns")
    columns = cursor.fetchall()
    print(f"\nCurrent columns in the table ({len(columns)}):")
    for col in columns:
        print(f" - {col}")
    
    conn.close()
    print("Done!")
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc() 