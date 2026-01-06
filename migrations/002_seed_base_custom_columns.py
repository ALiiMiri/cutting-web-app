import sqlite3

def ensure_base_columns_exist(cursor):
    """
    Ensures that the base custom columns exist in the database.
    This function is intended to be called during migrations.
    """
    base_columns = [
        ("rang", "رنگ پروفیل", "dropdown"),
        ("noe_profile", "نوع پروفیل", "dropdown"),
        ("vaziat", "وضعیت تولید درب", "dropdown"),
        ("lola", "لولا", "dropdown"),
        ("ghofl", "قفل", "dropdown"),
        ("accessory", "اکسسوری", "dropdown"),
        ("kolaft", "کلاف", "dropdown"),
        ("dastgire", "دستگیره", "dropdown"),
        ("tozihat", "توضیحات", "text")
    ]
    
    print("DEBUG (Migration): Checking/Adding base custom columns...")
    for column_key, display_name, col_type in base_columns:
        try:
            cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
            if not cursor.fetchone():
                print(f"DEBUG (Migration): Adding base column '{column_key}'...")
                cursor.execute(
                    "INSERT INTO custom_columns (column_name, display_name, is_active, column_type) VALUES (?, ?, 1, ?)",
                    (column_key, display_name, col_type)
                )
        except sqlite3.Error as e:
            print(f"ERROR (Migration) in ensure_base_columns_exist for column {column_key}: {e}")

def add_default_options_if_needed(cursor):
    """
    Adds default options for the base dropdown custom columns if they don't exist.
    This function is intended to be called during migrations.
    """
    default_options_map = {
        "rang": ["سفید", "آنادایز", "مشکی", "شامپاینی", "طلایی", "نقره‌ای", "قهوه‌ای"],
        # "noe_profile" removed - options should only come from profile_types table in inventory
        "vaziat": ["همزمان با تولید چهارچوب", "تولید درب در آینده", "بدون درب", "درب دار", "نصب شده"],
        "lola": ["OTLAV", "HTH", "NHN", "سه تیکه", "مخفی", "متفرقه"],
        "ghofl": ["STV", "ایزدو", "NHN", "HTN", "یونی", "مگنتی", "بدون قفل"],
        "accessory": ["آلومینیوم آستانه فاق و زبانه", "آرامبند مرونی", "قفل برق سارو با فنر", "آینه", "دستگیره پشت درب"],
        "kolaft": ["دو طرفه", "سه طرفه", "یک طرفه", "بدون کلافت"],
        "dastgire": ["دو تیکه", "ایزدو", "گریف ورک", "گریف تو کار", "متفرقه"]
    }
    
    print("DEBUG (Migration): Checking/Adding default options for dropdown columns...")
    for column_name, options_list in default_options_map.items():
        try:
            cursor.execute("SELECT id FROM custom_columns WHERE column_name = ? AND column_type = 'dropdown'", (column_name,))
            result = cursor.fetchone()
            if result:
                column_id = result[0]
                cursor.execute("SELECT COUNT(*) FROM custom_column_options WHERE column_id = ?", (column_id,))
                if cursor.fetchone()[0] == 0:
                    print(f"DEBUG (Migration): Adding {len(options_list)} default options for column '{column_name}'...")
                    for option_value in options_list:
                        cursor.execute(
                            "INSERT INTO custom_column_options (column_id, option_value) VALUES (?, ?)",
                            (column_id, option_value)
                        )
        except sqlite3.Error as e:
            print(f"ERROR (Migration) in add_default_options_if_needed for column {column_name}: {e}")

def apply(conn):
    """
    Applies this migration to the database.
    """
    print("--- Applying migration: 002_seed_base_custom_columns ---")
    cursor = conn.cursor()
    try:
        ensure_base_columns_exist(cursor)
        add_default_options_if_needed(cursor)
        # Commit is handled by the main migration script, no need to commit here.
        print("--- Migration 002_seed_base_custom_columns applied successfully. ---")
    except Exception as e:
        print(f"!!! FAILED to apply migration 002_seed_base_custom_columns: {e}")
        # Rollback should be handled by the main migration script.
        raise 