import sqlite3
import sys
import os
import hashlib
from datetime import datetime, timezone

# Add migrations directory to path
migrations_dir = os.path.join(os.path.dirname(__file__), 'migrations')
if migrations_dir not in sys.path:
    sys.path.insert(0, migrations_dir)

class MigrationError(RuntimeError):
    pass


class PendingMigrationError(MigrationError):
    pass


class MigrationDriftError(MigrationError):
    pass


def _migration_checksum(migration):
    if migration.get("execution_type") == "python_module":
        module_path = os.path.join(migrations_dir, f"{migration['module_name']}.py")
        with open(module_path, "rb") as handle:
            payload = handle.read()
    else:
        payload = str(migration.get("sql_apply", "")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _execute_sql_script(cursor, script):
    statement = ""
    for line in script.splitlines(True):
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                cursor.execute(statement)
            statement = ""
    if statement.strip():
        cursor.execute(statement)


def apply_migrations(conn, allow_changes=False):
    """
    Applies database migrations to the given SQLite connection,
    with versioning to ensure schema consistency.
    """
    cursor = conn.cursor()
    print("Starting database migrations...")

    # 0. The normal web startup is check-only. Schema creation is allowed only
    # through the guarded upgrade command.
    migration_table_exists = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not migration_table_exists and not allow_changes:
        raise PendingMigrationError("دیتابیس هنوز مقداردهی نشده است؛ ارتقای امن را اجرا کنید.")
    try:
        if allow_changes:
            cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name TEXT PRIMARY KEY,
                checksum TEXT,
                applied_at TEXT
            )
        """)
        if allow_changes:
            columns = {row[1] for row in cursor.execute("PRAGMA table_info(schema_migrations)")}
            if "checksum" not in columns:
                cursor.execute("ALTER TABLE schema_migrations ADD COLUMN checksum TEXT")
            if "applied_at" not in columns:
                cursor.execute("ALTER TABLE schema_migrations ADD COLUMN applied_at TEXT")
            conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Error creating 'schema_migrations' table: {e}")
        raise MigrationError(str(e)) from e

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

    sql_apply_012_create_inventory_cutting_applications = """
        CREATE TABLE IF NOT EXISTS inventory_cutting_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL UNIQUE,
            applied_at TEXT NOT NULL,
            profile_count INTEGER NOT NULL DEFAULT 0,
            total_stock_deducted INTEGER NOT NULL DEFAULT 0,
            pieces_consumed INTEGER NOT NULL DEFAULT 0,
            pieces_returned INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_cutting_applications_project_id
            ON inventory_cutting_applications(project_id);
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
        },
        {
            "name": "012_create_inventory_cutting_applications",
            "description": "Track fully committed cutting-plan inventory applications",
            "check_logic": lambda c: not c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_cutting_applications'"
            ).fetchone(),
            "sql_apply": sql_apply_012_create_inventory_cutting_applications,
            "execution_type": "script",
        },
        {
            "name": "013_inventory_operation_undo",
            "description": "Add an auditable inventory operation ledger and admin undo support",
            "check_logic": lambda c: (
                not c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_operations'"
                ).fetchone()
                or "operation_id" not in [
                    col[1] for col in c.execute("PRAGMA table_info(inventory_logs)").fetchall()
                ]
                or "operation_id" not in [
                    col[1]
                    for col in c.execute(
                        "PRAGMA table_info(inventory_cutting_applications)"
                    ).fetchall()
                ]
            ),
            "execution_type": "python_module",
            "module_name": "013_inventory_operation_undo",
        },
        {
            "name": "014_normalize_profile_names",
            "description": "Normalize whitespace in profile names and project profile values",
            "check_logic": lambda c: not c.execute(
                "SELECT 1 FROM schema_migrations WHERE name = '014_normalize_profile_names'"
            ).fetchone(),
            "execution_type": "python_module",
            "module_name": "014_normalize_profile_names",
        },
        {
            "name": "015_inventory_waste_warehouse",
            "description": "Create a project- and profile-traceable waste warehouse",
            "check_logic": lambda c: not c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_waste_items'"
            ).fetchone(),
            "execution_type": "python_module",
            "module_name": "015_inventory_waste_warehouse",
        },
        {
            "name": "016_color_aware_inventory",
            "description": "Track full stock, reusable pieces and cutting deductions by profile color",
            "check_logic": lambda c: (
                not c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='profile_colors'"
                ).fetchone()
                or "color_id" not in [
                    col[1] for col in c.execute("PRAGMA table_info(inventory_items)").fetchall()
                ]
            ),
            "execution_type": "python_module",
            "module_name": "016_color_aware_inventory",
        },
        {
            "name": "017_profile_archiving",
            "description": "Archive used profile definitions instead of deleting their history",
            "check_logic": lambda c: "is_active" not in [
                col[1] for col in c.execute("PRAGMA table_info(profile_types)").fetchall()
            ],
            "execution_type": "python_module",
            "module_name": "017_profile_archiving",
        },
        {
            "name": "018_normalize_inventory_settings",
            "description": "Persist canonical cutting-setting names while retaining legacy compatibility",
            "check_logic": lambda c: not c.execute(
                "SELECT 1 FROM schema_migrations WHERE name = '018_normalize_inventory_settings'"
            ).fetchone(),
            "execution_type": "python_module",
            "module_name": "018_normalize_inventory_settings",
        },
        {
            "name": "019_door_frame_type",
            "description": "Rename kolaft to door frame type and retain only two- and three-sided geometry",
            "check_logic": lambda c: not c.execute(
                "SELECT 1 FROM schema_migrations WHERE name = '019_door_frame_type'"
            ).fetchone(),
            "execution_type": "python_module",
            "module_name": "019_door_frame_type",
        },
        {
            "name": "020_project_measurement_unit",
            "description": "Store a centimeter or millimeter input unit for each project",
            "check_logic": lambda c: "measurement_unit" not in [
                col[1] for col in c.execute("PRAGMA table_info(projects)").fetchall()
            ],
            "execution_type": "python_module",
            "module_name": "020_project_measurement_unit",
        },
        {
            "name": "021_user_management_security",
            "description": "Add secure session invalidation and user activity history",
            "check_logic": lambda c: (
                "session_version" not in [
                    col[1] for col in c.execute("PRAGMA table_info(users)").fetchall()
                ]
                or not c.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_activity_logs'"
                ).fetchone()
            ),
            "execution_type": "python_module",
            "module_name": "021_user_management_security",
        },
        {
            "name": "022_project_ownership",
            "description": "Track project creators, assignees and assignment history",
            "check_logic": lambda c: (
                "created_by_user_id" not in [
                    col[1] for col in c.execute("PRAGMA table_info(projects)").fetchall()
                ]
                or "assigned_to_user_id" not in [
                    col[1] for col in c.execute("PRAGMA table_info(projects)").fetchall()
                ]
                or not c.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_assignment_logs'"
                ).fetchone()
            ),
            "execution_type": "python_module",
            "module_name": "022_project_ownership",
        },
        {
            "name": "023_user_orders_view_preference",
            "description": "Store each user's preferred orders dashboard view",
            "check_logic": lambda c: "orders_view_preference" not in [
                col[1] for col in c.execute("PRAGMA table_info(users)").fetchall()
            ],
            "execution_type": "python_module",
            "module_name": "023_user_orders_view_preference",
        },
        {
            "name": "024_cutting_plan_snapshot",
            "description": "Persist the exact applied cutting plan for later exports",
            "check_logic": lambda c: "plan_snapshot_json" not in [
                col[1]
                for col in c.execute(
                    "PRAGMA table_info(inventory_cutting_applications)"
                ).fetchall()
            ],
            "execution_type": "python_module",
            "module_name": "024_cutting_plan_snapshot",
        },
        {
            "name": "025_cutting_orders",
            "description": "Create persistent grouped cutting orders and atomic inventory reservations",
            "check_logic": lambda c: (
                not c.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cutting_orders'"
                ).fetchone()
                or not c.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_reservations'"
                ).fetchone()
                or "archived_at" not in [
                    col[1] for col in c.execute("PRAGMA table_info(projects)").fetchall()
                ]
            ),
            "execution_type": "python_module",
            "module_name": "025_cutting_orders",
        },
        {
            "name": "026_project_query_indexes",
            "description": "Keep project lists, customer filters and door lookups fast as data grows",
            "check_logic": lambda c: not {
                "idx_projects_active_id",
                "idx_projects_active_assignee_id",
                "idx_projects_active_customer_id",
                "idx_projects_active_order_ref_id",
                "idx_projects_active_date_id",
                "idx_projects_project_code",
                "idx_doors_project_id",
            }.issubset(
                {
                    row[0]
                    for row in c.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    ).fetchall()
                }
            ),
            "execution_type": "python_module",
            "module_name": "026_project_query_indexes",
        },
        {
            "name": "027_door_hardware",
            "description": "Store validated hinge, handle, lock and cylinder choices per door",
            "check_logic": lambda c: not c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='door_hardware'"
            ).fetchone(),
            "execution_type": "python_module",
            "module_name": "027_door_hardware",
        }
    ]

    # --- Execution Loop ---

    for migration in migrations:
        migration_name = migration["name"]

        try:
            # Check if migration was already recorded
            columns = {row[1] for row in cursor.execute("PRAGMA table_info(schema_migrations)")}
            select_columns = "name, checksum" if "checksum" in columns else "name, NULL"
            cursor.execute(
                f"SELECT {select_columns} FROM schema_migrations WHERE name = ?",
                (migration_name,),
            )
            recorded_row = cursor.fetchone()
            already_recorded = recorded_row is not None
            checksum = _migration_checksum(migration)
            
            # Check if migration actually needs to run
            needs_execution = migration["check_logic"](cursor)
            
            # Skip if already recorded AND data exists (migration was successful)
            if already_recorded and not needs_execution:
                stored_checksum = recorded_row[1]
                if stored_checksum and stored_checksum != checksum:
                    raise MigrationDriftError(
                        f"فایل مهاجرت اجراشده «{migration_name}» پس از اجرا تغییر کرده است."
                    )
                if allow_changes and not stored_checksum:
                    cursor.execute("BEGIN IMMEDIATE")
                    cursor.execute(
                        "UPDATE schema_migrations SET checksum=?, applied_at=COALESCE(applied_at,?) WHERE name=?",
                        (checksum, datetime.now(timezone.utc).isoformat(), migration_name),
                    )
                    conn.commit()
                continue
            
            # If migration was recorded but data is missing, we need to re-run it
            # (This handles cases where database was cleared but schema_migrations wasn't)
            if already_recorded and needs_execution:
                raise MigrationDriftError(
                    f"مهاجرت «{migration_name}» ثبت شده ولی ساختار مورد انتظار آن وجود ندارد."
                )

            if not allow_changes:
                raise PendingMigrationError(
                    f"مهاجرت اجرا نشده «{migration_name}» وجود دارد؛ برنامه در حالت امن متوقف شد."
                )

            if needs_execution:
                print(f"-> Applying '{migration_name}'...")
                exec_type = migration.get("execution_type", "single")
                cursor.execute("BEGIN IMMEDIATE")
                try:
                    if exec_type == "script":
                        _execute_sql_script(cursor, migration["sql_apply"])
                    elif exec_type == "single":
                        cursor.execute(migration["sql_apply"])
                    elif exec_type == "python_module":
                        module_name = migration.get("module_name", migration_name)
                        module = __import__(module_name, fromlist=['apply'])
                        module.apply(conn)
                    cursor.execute(
                        "INSERT INTO schema_migrations(name,checksum,applied_at) VALUES (?,?,?)",
                        (migration_name, checksum, datetime.now(timezone.utc).isoformat()),
                    )
                    conn.commit()
                    print(f"   Success.")
                except Exception:
                    conn.rollback()
                    raise
            else:
                cursor.execute("BEGIN IMMEDIATE")
                cursor.execute(
                    "INSERT INTO schema_migrations(name,checksum,applied_at) VALUES (?,?,?)",
                    (migration_name, checksum, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                print(f"-> Adopted already-present migration '{migration_name}'.")

        except Exception as e:
            print(f"!!! Error applying '{migration_name}': {e}")
            conn.rollback()
            raise

    print("Database migrations completed.\n")
