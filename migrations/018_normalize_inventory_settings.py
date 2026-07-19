DEFAULTS = {
    "default_wastage": "20",
    "min_remaining_length": "20",
    "use_inventory_for_cutting": "true",
    "prefer_inventory_pieces": "true",
    "inventory_optimization_strategy": "minimize_waste",
    "show_inventory_warnings": "true",
    "low_inventory_threshold": "5",
}

ALIASES = {
    "use_inventory_for_cutting": "use_inventory",
    "prefer_inventory_pieces": "prefer_pieces",
}


def apply(conn):
    """Add canonical setting rows without overwriting an existing user choice."""
    cursor = conn.cursor()
    if not cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cutting_settings'"
    ).fetchone():
        return

    for canonical_name, legacy_name in ALIASES.items():
        legacy_row = cursor.execute(
            "SELECT value FROM cutting_settings WHERE name = ?", (legacy_name,)
        ).fetchone()
        if legacy_row:
            cursor.execute(
                """
                INSERT OR IGNORE INTO cutting_settings(name,value,description)
                VALUES (?,?,?)
                """,
                (canonical_name, legacy_row[0], f"نام استاندارد جایگزین {legacy_name}"),
            )

    for name, value in DEFAULTS.items():
        cursor.execute(
            """
            INSERT OR IGNORE INTO cutting_settings(name,value,description)
            VALUES (?,?,?)
            """,
            (name, value, "تنظیم استاندارد محاسبه برش"),
        )
