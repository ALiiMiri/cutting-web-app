def _column_names(cursor, table_name):
    return {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}


def apply(conn):
    """Create the append-only inventory operation ledger used by admin undo."""
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_type TEXT NOT NULL,
            project_id INTEGER,
            actor_user_id INTEGER,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'applied',
            is_reversible INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            reversed_at TEXT,
            reversed_by_user_id INTEGER,
            reversal_reason TEXT,
            reverses_operation_id INTEGER,
            reversal_operation_id INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL,
            FOREIGN KEY (actor_user_id) REFERENCES users (id) ON DELETE SET NULL,
            FOREIGN KEY (reversed_by_user_id) REFERENCES users (id) ON DELETE SET NULL,
            FOREIGN KEY (reverses_operation_id) REFERENCES inventory_operations (id),
            FOREIGN KEY (reversal_operation_id) REFERENCES inventory_operations (id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_operation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id INTEGER NOT NULL,
            sequence_no INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            profile_type_id INTEGER,
            profile_name TEXT NOT NULL,
            quantity_delta INTEGER,
            before_quantity INTEGER,
            after_quantity INTEGER,
            piece_id INTEGER,
            length REAL,
            FOREIGN KEY (operation_id) REFERENCES inventory_operations (id) ON DELETE CASCADE,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE SET NULL
        )
        """
    )

    log_columns = _column_names(cursor, "inventory_logs")
    if "operation_id" not in log_columns:
        cursor.execute("ALTER TABLE inventory_logs ADD COLUMN operation_id INTEGER")

    application_columns = _column_names(cursor, "inventory_cutting_applications")
    if "operation_id" not in application_columns:
        cursor.execute("ALTER TABLE inventory_cutting_applications ADD COLUMN operation_id INTEGER")

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_operations_latest ON inventory_operations(status, is_reversible, id DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_operation_items_operation ON inventory_operation_items(operation_id, sequence_no)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_logs_operation ON inventory_logs(operation_id)"
    )

