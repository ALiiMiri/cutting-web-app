import sqlite3

def apply_migrations(conn):
    """
    Applies database migrations to the given SQLite connection,
    with versioning to ensure schema consistency.
    """
    cursor = conn.cursor()
    print("Starting database migrations...")

    # 0. Ensure schema_migrations table exists
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY
            )
        """)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error creating 'schema_migrations' table: {e}")
        return

    # --- SQL Definitions ---

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

    sql_apply_002_seed = """
        INSERT OR IGNORE INTO custom_columns (column_name, display_name, is_active) VALUES 
        ('rang', 'رنگ پروفیل', 1),
        ('noe_profile', 'نوع پروفیل', 1),
        ('vaziat', 'وضعیت تولید درب', 1),
        ('lola', 'لولا', 1),
        ('ghofl', 'قفل', 1),
        ('accessory', 'اکسسوری', 1),
        ('kolaft', 'کلافت', 1),
        ('dastgire', 'دستگیره', 1),
        ('tozihat', 'توضیحات', 1);
    """

    sql_apply_003_price_settings = """
        CREATE TABLE IF NOT EXISTS price_settings (
            key TEXT PRIMARY KEY,
            value REAL
        );
    """

    # --- Migrations List ---

    migrations = [
        {
            "name": "000_create_initial_tables",
            "description": "Create base tables",
            "check_logic": lambda c: not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'").fetchone(),
            "sql_apply": sql_apply_000,
            "execution_type": "script",
        },
        {
            "name": "001_add_row_color_tag_to_doors",
            "description": "Add row_color_tag column",
            "check_logic": lambda c: 'row_color_tag' not in [col[1] for col in c.execute("PRAGMA table_info(doors)").fetchall()],
            "sql_apply": "ALTER TABLE doors ADD COLUMN row_color_tag TEXT DEFAULT 'white'",
            "execution_type": "single",
        },
        {
            "name": "002_seed_base_custom_columns",
            "description": "Seed default custom columns",
            "check_logic": lambda c: c.execute("SELECT COUNT(*) FROM custom_columns").fetchone()[0] == 0,
            "sql_apply": sql_apply_002_seed,
            "execution_type": "script",
        },
        {
            "name": "003_create_price_settings",
            "description": "Create price settings table",
            "check_logic": lambda c: not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_settings'").fetchone(),
            "sql_apply": sql_apply_003_price_settings,
            "execution_type": "script",
        }
    ]

    # --- Execution Loop ---

    for migration in migrations:
        migration_name = migration["name"]
        
        try:
            cursor.execute("SELECT name FROM schema_migrations WHERE name = ?", (migration_name,))
            if cursor.fetchone():
                continue # Already applied

            needs_execution = migration["check_logic"](cursor)

            if needs_execution:
                print(f"-> Applying '{migration_name}'...")
                exec_type = migration.get("execution_type", "single")
                
                if exec_type == "script":
                    cursor.executescript(migration["sql_apply"])
                elif exec_type == "single":
                    cursor.execute(migration["sql_apply"])
                
                conn.commit()
                print(f"   Success.")
            
            # Record migration
            cursor.execute("INSERT INTO schema_migrations (name) VALUES (?)", (migration_name,))
            conn.commit()

        except Exception as e:
            print(f"!!! Error applying '{migration_name}': {e}")
            conn.rollback()
            break 

    print("Database migrations completed.\n")
