import sqlite3


DEFAULT_COLORS = (
    ("تعیین‌نشده", "#9ca3af"),
    ("سفید", "#ffffff"),
    ("مشکی", "#111827"),
    ("آنادایز", "#b8b8b8"),
    ("آنادایز نقره‌ای", "#c0c0c0"),
    ("نقره‌ای", "#c0c0c0"),
    ("شامپاینی", "#d6b98c"),
    ("طلایی", "#d4af37"),
    ("قهوه‌ای", "#795548"),
)


def _columns(cursor, table):
    return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}


def _table_exists(cursor, table):
    return cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def apply(conn):
    """Make inventory stock, reusable pieces and audit records color-aware."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS profile_colors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            hex_code TEXT NOT NULL DEFAULT '#9ca3af',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for name, hex_code in DEFAULT_COLORS:
        cursor.execute(
            "INSERT OR IGNORE INTO profile_colors (name, hex_code) VALUES (?, ?)",
            (name, hex_code),
        )

    if _table_exists(cursor, "custom_columns") and _table_exists(cursor, "custom_column_options"):
        cursor.execute(
            """
            INSERT OR IGNORE INTO profile_colors (name, hex_code)
            SELECT TRIM(cco.option_value), '#9ca3af'
            FROM custom_column_options cco
            JOIN custom_columns cc ON cc.id = cco.column_id
            WHERE cc.column_name = 'rang' AND TRIM(COALESCE(cco.option_value, '')) != ''
            """
        )

    unknown_id = cursor.execute(
        "SELECT id FROM profile_colors WHERE name = 'تعیین‌نشده'"
    ).fetchone()[0]

    if "color_id" not in _columns(cursor, "inventory_items"):
        cursor.execute(
            """
            CREATE TABLE inventory_items_color_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_type_id INTEGER NOT NULL,
                color_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(profile_type_id, color_id),
                FOREIGN KEY (profile_type_id) REFERENCES profile_types(id) ON DELETE CASCADE,
                FOREIGN KEY (color_id) REFERENCES profile_colors(id)
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO inventory_items_color_new
                (id, profile_type_id, color_id, quantity, last_updated)
            SELECT id, profile_type_id, ?, quantity, last_updated FROM inventory_items
            """,
            (unknown_id,),
        )
        old_stats = cursor.execute(
            "SELECT COUNT(*), COALESCE(SUM(quantity),0) FROM inventory_items"
        ).fetchone()
        new_stats = cursor.execute(
            "SELECT COUNT(*), COALESCE(SUM(quantity),0) FROM inventory_items_color_new"
        ).fetchone()
        if old_stats != new_stats:
            raise sqlite3.IntegrityError(
                f"inventory_items copy verification failed: {old_stats} != {new_stats}"
            )
        cursor.execute("DROP TABLE inventory_items")
        cursor.execute("ALTER TABLE inventory_items_color_new RENAME TO inventory_items")

    column_targets = (
        ("inventory_pieces", "color_id", "INTEGER"),
        ("inventory_logs", "color_id", "INTEGER"),
        ("inventory_logs", "color_name_snapshot", "TEXT"),
        ("inventory_operation_items", "color_id", "INTEGER"),
        ("inventory_operation_items", "color_name_snapshot", "TEXT"),
        ("inventory_waste_items", "color_id", "INTEGER"),
        ("inventory_waste_items", "color_name_snapshot", "TEXT"),
    )
    for table, column, column_type in column_targets:
        if _table_exists(cursor, table) and column not in _columns(cursor, table):
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    for table in ("inventory_pieces", "inventory_logs", "inventory_operation_items", "inventory_waste_items"):
        if _table_exists(cursor, table) and "color_id" in _columns(cursor, table):
            cursor.execute(f"UPDATE {table} SET color_id = ? WHERE color_id IS NULL", (unknown_id,))
        if _table_exists(cursor, table) and "color_name_snapshot" in _columns(cursor, table):
            cursor.execute(
                f"UPDATE {table} SET color_name_snapshot = 'تعیین‌نشده' "
                "WHERE color_name_snapshot IS NULL OR TRIM(color_name_snapshot) = ''"
            )

    if _table_exists(cursor, "inventory_deductions") and "color_id" not in _columns(cursor, "inventory_deductions"):
        cursor.execute(
            """
            CREATE TABLE inventory_deductions_color_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                profile_type_id INTEGER NOT NULL,
                color_id INTEGER NOT NULL,
                color_name_snapshot TEXT NOT NULL,
                quantity_deducted INTEGER NOT NULL,
                deduction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, profile_type_id, color_id),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (profile_type_id) REFERENCES profile_types(id) ON DELETE CASCADE,
                FOREIGN KEY (color_id) REFERENCES profile_colors(id)
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO inventory_deductions_color_new
                (id, project_id, profile_type_id, color_id, color_name_snapshot,
                 quantity_deducted, deduction_date)
            SELECT id, project_id, profile_type_id, ?, 'تعیین‌نشده',
                   quantity_deducted, deduction_date
            FROM inventory_deductions
            """,
            (unknown_id,),
        )
        old_stats = cursor.execute(
            "SELECT COUNT(*), COALESCE(SUM(quantity_deducted),0) FROM inventory_deductions"
        ).fetchone()
        new_stats = cursor.execute(
            "SELECT COUNT(*), COALESCE(SUM(quantity_deducted),0) FROM inventory_deductions_color_new"
        ).fetchone()
        if old_stats != new_stats:
            raise sqlite3.IntegrityError(
                f"inventory_deductions copy verification failed: {old_stats} != {new_stats}"
            )
        cursor.execute("DROP TABLE inventory_deductions")
        cursor.execute("ALTER TABLE inventory_deductions_color_new RENAME TO inventory_deductions")

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_items_variant ON inventory_items(profile_type_id, color_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_pieces_variant ON inventory_pieces(profile_type_id, color_id, length DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_deductions_project ON inventory_deductions(project_id)"
    )
