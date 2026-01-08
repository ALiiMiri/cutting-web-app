import sqlite3
import sys
import os

# Add migrations directory to path
migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
if migrations_dir not in sys.path:
    sys.path.insert(0, migrations_dir)

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

    # sql_apply_002_seed removed - now using Python module migrations/002_seed_base_custom_columns.py

    sql_apply_003_price_settings = """
        CREATE TABLE IF NOT EXISTS price_settings (
            key TEXT PRIMARY KEY,
            value REAL
        );
    """

    sql_apply_004_inventory_deductions = """
        CREATE TABLE IF NOT EXISTS inventory_deductions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            profile_type_id INTEGER NOT NULL,
            quantity_deducted INTEGER NOT NULL,
            deduction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, profile_type_id),
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_deductions_project_id
            ON inventory_deductions(project_id);
        CREATE INDEX IF NOT EXISTS idx_inventory_deductions_profile_type_id
            ON inventory_deductions(profile_type_id);
    """

    sql_apply_005_users_table = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            is_active INTEGER NOT NULL DEFAULT 1,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP,
            failed_login_attempts INTEGER DEFAULT 0,
            locked_until TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
    """

    sql_apply_006_fix_inventory_items_unique = """
        -- Merge any duplicate rows first
        CREATE TEMPORARY TABLE temp_inventory_items AS
        SELECT profile_type_id, SUM(quantity) as quantity, MAX(last_updated) as last_updated
        FROM inventory_items
        GROUP BY profile_type_id;
        
        -- Drop old table
        DROP TABLE inventory_items;
        
        -- Recreate with UNIQUE constraint
        CREATE TABLE inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_type_id INTEGER NOT NULL UNIQUE,
            quantity INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE
        );
        
        -- Restore data
        INSERT INTO inventory_items (profile_type_id, quantity, last_updated)
        SELECT profile_type_id, quantity, last_updated FROM temp_inventory_items;
        
        -- Drop temp table
        DROP TABLE temp_inventory_items;
    """

    sql_apply_007_remove_noe_profile_defaults = """
        -- Remove default options from noe_profile column
        -- These options should only come from profile_types table
        DELETE FROM custom_column_options
        WHERE column_id IN (
            SELECT id FROM custom_columns WHERE column_name = 'noe_profile'
        )
        AND option_value IN (
            'فریم لس آلومینیومی', 'فریم قدیمی', 'داخل چوب دار', 'فریم دار', 'ساده'
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
            "check_logic": lambda c: (
                # Check if all required base columns exist
                c.execute("SELECT COUNT(*) FROM custom_columns WHERE column_name IN ('rang', 'noe_profile', 'vaziat', 'lola', 'ghofl', 'accessory', 'kolaft', 'dastgire', 'tozihat')").fetchone()[0] < 9
            ),
            "execution_type": "python_module",
            "module_name": "002_seed_base_custom_columns",
        },
        {
            "name": "003_create_price_settings",
            "description": "Create price settings table",
            "check_logic": lambda c: not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_settings'").fetchone(),
            "sql_apply": sql_apply_003_price_settings,
            "execution_type": "script",
        },
        {
            "name": "004_create_inventory_deductions",
            "description": "Create inventory_deductions table for preventing duplicate inventory deduction per project",
            "check_logic": lambda c: not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_deductions'").fetchone(),
            "sql_apply": sql_apply_004_inventory_deductions,
            "execution_type": "script",
        },
        {
            "name": "005_create_users_table",
            "description": "Create users table for authentication and role-based access control",
            "check_logic": lambda c: not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone(),
            "sql_apply": sql_apply_005_users_table,
            "execution_type": "script",
        },
        {
            "name": "006_fix_inventory_items_unique",
            "description": "Add UNIQUE constraint to inventory_items.profile_type_id to prevent duplicates",
            "check_logic": lambda c: (
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_items'").fetchone() and
                'UNIQUE' not in str(c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='inventory_items'").fetchone()[0] or '')
            ),
            "sql_apply": sql_apply_006_fix_inventory_items_unique,
            "execution_type": "script",
        },
        {
            "name": "007_remove_noe_profile_defaults",
            "description": "Remove default options from noe_profile - options should only come from profile_types",
            "check_logic": lambda c: (
                c.execute("SELECT COUNT(*) FROM custom_column_options WHERE column_id IN (SELECT id FROM custom_columns WHERE column_name='noe_profile') AND option_value IN ('فریم لس آلومینیومی', 'فریم قدیمی', 'داخل چوب دار', 'فریم دار', 'ساده')").fetchone()[0] > 0
            ),
            "sql_apply": sql_apply_007_remove_noe_profile_defaults,
            "execution_type": "script",
        },
        {
            "name": "008_create_default_admin",
            "description": "Create default admin user (username: admin, password: admin)",
            "check_logic": lambda c: not c.execute("SELECT id FROM users WHERE username = 'admin'").fetchone(),
            "execution_type": "python_module",
            "module_name": "008_create_default_admin",
        },
        {
            "name": "009_add_project_code",
            "description": "Add project_code column to projects table for unique 4-digit codes",
            "check_logic": lambda c: 'project_code' not in [col[1] for col in c.execute("PRAGMA table_info(projects)").fetchall()],
            "sql_apply": "ALTER TABLE projects ADD COLUMN project_code TEXT",
            "execution_type": "single",
        },
        {
            "name": "010_create_inventory_tables",
            "description": "Create inventory system tables (profile_types, inventory_items, inventory_pieces, inventory_logs, cutting_settings)",
            "check_logic": lambda c: not c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='profile_types'").fetchone(),
            "execution_type": "python_module",
            "module_name": "010_create_inventory_tables",
        },
        {
            "name": "011_add_min_waste_to_profile_types",
            "description": "Add min_waste column to profile_types table",
            "check_logic": lambda c: 'min_waste' not in [col[1] for col in c.execute("PRAGMA table_info(profile_types)").fetchall()] if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='profile_types'").fetchone() else False,
            "execution_type": "python_module",
            "module_name": "011_add_min_waste_to_profile_types",
        }
    ]

    # --- Execution Loop ---

    for migration in migrations:
        migration_name = migration["name"]

        try:
            # Check if migration was already recorded
            cursor.execute("SELECT name FROM schema_migrations WHERE name = ?", (migration_name,))
            already_recorded = cursor.fetchone() is not None
            
            # Check if migration actually needs to run
            needs_execution = migration["check_logic"](cursor)
            
            # Skip if already recorded AND data exists (migration was successful)
            if already_recorded and not needs_execution:
                continue # Already applied and data exists
            
            # If migration was recorded but data is missing, we need to re-run it
            # (This handles cases where database was cleared but schema_migrations wasn't)
            if already_recorded and needs_execution:
                print(f"-> Re-running '{migration_name}' (data missing but migration was recorded)...")
                # Don't skip - let it run below

            if needs_execution:
                print(f"-> Applying '{migration_name}'...")
                exec_type = migration.get("execution_type", "single")
                
                if exec_type == "script":
                    cursor.executescript(migration["sql_apply"])
                elif exec_type == "single":
                    cursor.execute(migration["sql_apply"])
                    conn.commit()
                elif exec_type == "python_module":
                    # Import and execute Python migration module
                    module_name = migration.get("module_name", migration_name)
                    try:
                        module = __import__(module_name, fromlist=['apply'])
                        module.apply(conn)
                        conn.commit()
                    except ImportError as e:
                        print(f"   ERROR: Could not import migration module '{module_name}': {e}")
                        raise
                    except Exception as e:
                        print(f"   ERROR: Migration module '{module_name}' failed: {e}")
                        raise
                
                print(f"   Success.")
                
                # Record migration (only if not already recorded)
                if not already_recorded:
                    cursor.execute("INSERT INTO schema_migrations (name) VALUES (?)", (migration_name,))
                    conn.commit()
                else:
                    # Migration was re-run, commit the changes
                    conn.commit()

        except Exception as e:
            print(f"!!! Error applying '{migration_name}': {e}")
            conn.rollback()
            break 

    print("Database migrations completed.\n")
