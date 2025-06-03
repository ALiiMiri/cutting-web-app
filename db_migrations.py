import sqlite3

def apply_migrations(conn):
    """
    Applies database migrations to the given SQLite connection,
    with versioning.

    Args:
        conn: SQLite connection object.
    """
    cursor = conn.cursor()
    print("شروع اعمال مایگریشن‌های دیتابیس با نسخه‌بندی...")

    # 0. ایجاد جدول schema_migrations اگر وجود نداشته باشد
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY
            )
        """)
        conn.commit()
        print("جدول 'schema_migrations' بررسی/ایجاد شد.")
    except sqlite3.Error as e:
        print(f"خطا در ایجاد جدول 'schema_migrations': {e}")
        return # اگر جدول مایگریشن ایجاد نشود، ادامه نمی‌دهیم

    sql_apply_000 = """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            order_ref TEXT NOT NULL,
            date_shamsi TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS doors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            location TEXT,
            width REAL,
            height REAL,
            quantity INTEGER,
            direction TEXT DEFAULT 'چپ',
            row_color_tag TEXT DEFAULT 'white',
            FOREIGN KEY (project_id) REFERENCES projects (id)
        );
        CREATE TABLE IF NOT EXISTS custom_columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            column_name TEXT UNIQUE,
            display_name TEXT,
            column_type TEXT DEFAULT 'text',
            is_active BOOLEAN DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS custom_column_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            column_id INTEGER,
            option_value TEXT,
            FOREIGN KEY (column_id) REFERENCES custom_columns (id)
        );
        CREATE TABLE IF NOT EXISTS door_custom_values (
            door_id INTEGER,
            column_id INTEGER,
            value TEXT,
            PRIMARY KEY (door_id, column_id),
            FOREIGN KEY (door_id) REFERENCES doors (id),
            FOREIGN KEY (column_id) REFERENCES custom_columns (id)
        );
        CREATE TABLE IF NOT EXISTS project_visible_columns (
            project_id INTEGER,
            column_key TEXT,
            is_visible BOOLEAN DEFAULT 1,
            PRIMARY KEY (project_id, column_key),
            FOREIGN KEY (project_id) REFERENCES projects (id)
        );
        CREATE TABLE IF NOT EXISTS batch_edit_checkbox_state (
            project_id INTEGER,
            column_key TEXT,
            is_checked BOOLEAN DEFAULT 0,
            PRIMARY KEY (project_id, column_key),
            FOREIGN KEY (project_id) REFERENCES projects (id)
        );
        CREATE TABLE IF NOT EXISTS saved_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT,
            customer_mobile TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            input_width REAL,
            input_height REAL,
            profile_type TEXT,
            aluminum_color TEXT,
            door_material TEXT,
            paint_condition TEXT,
            paint_brand TEXT,
            selections_details TEXT,
            final_calculated_price REAL,
            notes TEXT DEFAULT '',
            shamsi_order_date TEXT DEFAULT ''
        );
    """

    sql_apply_003_price_settings = """
        CREATE TABLE IF NOT EXISTS price_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """

    migrations = [
        {
            "name": "000_create_initial_tables",
            "description": "ایجاد تمام جدول‌های پایه برای شروع برنامه",
            "check_logic": lambda c: not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'").fetchone(),
            "sql_apply": sql_apply_000,
            "execution_type": "script",
        },
        {
            "name": "001_add_row_color_tag_to_doors",
            "description": "اضافه کردن ستون row_color_tag به جدول doors",
            "check_logic": lambda c: 'row_color_tag' not in [col[1] for col in c.execute("PRAGMA table_info(doors)").fetchall()],
            "sql_apply": "ALTER TABLE doors ADD COLUMN row_color_tag TEXT DEFAULT 'white'",
            "execution_type": "single",
        },
        {
            "name": "002_create_inventory_logs_table",
            "description": "ایجاد جدول inventory_logs",
            "check_logic": lambda c: not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_logs'").fetchone(),
            "sql_apply": '''
                CREATE TABLE inventory_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    profile_id INTEGER,
                    action TEXT,
                    description TEXT
                )
            ''',
            "execution_type": "single",
        },
        {
            "name": "003_create_price_settings_table",
            "description": "ایجاد جدول price_settings برای تنظیمات محاسبه قیمت",
            "check_logic": lambda c: not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_settings'").fetchone(),
            "sql_apply": sql_apply_003_price_settings,
            "execution_type": "single",
        },
        {
            "name": "004_add_installation_notes_to_doors",
            "description": "افزودن ستون installation_notes به جدول doors برای یادداشت‌های نصب",
            "check_logic": lambda c: not any(col[1] == 'installation_notes' for col in c.execute("PRAGMA table_info(doors)").fetchall()),
            "sql_apply": "ALTER TABLE doors ADD COLUMN installation_notes TEXT DEFAULT '';",
            "execution_type": "single"
        }
    ]

    for migration in migrations:
        migration_name = migration["name"]
        migration_desc = migration["description"]
        print(f"\nبررسی مایگریشن: {migration_name} ({migration_desc})...")

        try:
            cursor.execute("SELECT name FROM schema_migrations WHERE name = ?", (migration_name,))
            is_already_applied_and_recorded = cursor.fetchone()

            if is_already_applied_and_recorded:
                print(f"مایگریشن '{migration_name}' قبلاً اعمال و ثبت شده است. رد می‌شویم.")
                continue

            print(f"مایگریشن '{migration_name}' هنوز در schema_migrations ثبت نشده است.")
            
            needs_sql_execution = migration["check_logic"](cursor)

            if needs_sql_execution:
                print(f"شرایط مایگریشن '{migration_name}' نشان می‌دهد که SQL باید اجرا شود. در حال اجرای SQL...")
                execution_type = migration.get("execution_type", "single")
                if execution_type == "script":
                    cursor.executescript(migration["sql_apply"])
                else:
                    cursor.execute(migration["sql_apply"])
                conn.commit()
                print(f"SQL برای مایگریشن '{migration_name}' با موفقیت اجرا شد.")
            else:
                print(f"شرایط مایگریشن '{migration_name}' نشان می‌دهد که SQL نیازی به اجرا ندارد (وضعیت دیتابیس از قبل مطابق است).")

            cursor.execute("INSERT INTO schema_migrations (name) VALUES (?)", (migration_name,))
            conn.commit()
            print(f"مایگریشن '{migration_name}' با موفقیت در schema_migrations ثبت شد.")

        except sqlite3.Error as e:
            print(f"خطا در اعمال مایگریشن '{migration_name}': {e}")
            try:
                conn.rollback()
                print(f"تغییرات مربوط به مایگریشن '{migration_name}' بازگردانده شد (rollback).")
            except sqlite3.Error as rb_err:
                print(f"خطا در هنگام rollback برای مایگریشن '{migration_name}': {rb_err}")
        except Exception as ex:
            print(f"خطای پیش‌بینی نشده در اعمال مایگریشن '{migration_name}': {ex}")
            try:
                conn.rollback()
                print(f"تغییرات مربوط به مایگریشن '{migration_name}' بازگردانده شد (rollback).")
            except sqlite3.Error as rb_err:
                print(f"خطا در هنگام rollback برای مایگریشن '{migration_name}': {rb_err}")
                
    print("\nپایان اعمال مایگریشن‌های دیتابیس.")

if __name__ == '__main__':
    db_name = 'your_database_file.db' 
    # For a clean test, you might want to delete the db file before running.
    # import os
    # if os.path.exists(db_name):
    #     os.remove(db_name)
    #     print(f"فایل دیتابیس تست '{db_name}' برای اجرای تمیز حذف شد.")

    print(f"اتصال به دیتابیس {db_name} برای تست مایگریشن‌ها...")
    
    conn = None
    try:
        conn = sqlite3.connect(db_name)
        print("اتصال به دیتابیس موفقیت آمیز بود.")
        
        cursor = conn.cursor()
        # Optional: Drop schema_migrations for a full re-run during testing
        # cursor.execute("DROP TABLE IF EXISTS schema_migrations")
        # cursor.execute("DROP TABLE IF EXISTS projects") # Example for testing migration 000
        # cursor.execute("DROP TABLE IF EXISTS doors")
        # cursor.execute("DROP TABLE IF EXISTS custom_columns")
        # cursor.execute("DROP TABLE IF EXISTS custom_column_options")
        # cursor.execute("DROP TABLE IF EXISTS door_custom_values")
        # cursor.execute("DROP TABLE IF EXISTS project_visible_columns")
        # cursor.execute("DROP TABLE IF EXISTS batch_edit_checkbox_state")
        # cursor.execute("DROP TABLE IF EXISTS saved_quotes")
        # cursor.execute("DROP TABLE IF EXISTS inventory_logs")
        # conn.commit()
        # print("جداول تست (در صورت وجود) برای اجرای کامل مایگریشن‌ها پاک شدند.")

        apply_migrations(conn)
        
        print("\nمحتوای جدول schema_migrations پس از اعمال:")
        try:
            cursor.execute("SELECT name FROM schema_migrations ORDER BY name")
            applied_migrations = cursor.fetchall()
            if applied_migrations:
                for row in applied_migrations:
                    print(f"- {row[0]}")
            else:
                print("جدول schema_migrations خالی است یا وجود ندارد.")
        except sqlite3.Error as e:
            print(f"خطا در خواندن جدول schema_migrations: {e}")

        # Verify table creation (optional check for testing)
        print("\nبررسی وجود جداول اصلی:")
        tables_to_check = ["projects", "doors", "custom_columns", "custom_column_options", "door_custom_values", "project_visible_columns", "batch_edit_checkbox_state", "saved_quotes", "inventory_logs"]
        for table_name in tables_to_check:
            try:
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
                if cursor.fetchone():
                    print(f"- جدول '{table_name}' وجود دارد.")
                else:
                    print(f"- جدول '{table_name}' وجود ندارد. (خطا!)")
            except sqlite3.Error as e:
                print(f"- خطا در بررسی جدول '{table_name}': {e}")


    except sqlite3.Error as e:
        print(f"خطا در اتصال به دیتابیس {db_name} یا اجرای مایگریشن‌ها: {e}")
    finally:
        if conn:
            conn.close()
            print("اتصال به دیتابیس بسته شد.")
    
    print("\nبرای استفاده واقعی، تابع apply_migrations را با اتصال دیتابیس خود فراخوانی کنید.")

    print("مثال: ")
    print("import sqlite3")
    print("from db_migrations import apply_migrations")
    print("conn = sqlite3.connect('your_actual_database.db')")
    print("apply_migrations(conn)")
    print("conn.close()") 