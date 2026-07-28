def _columns(cursor, table):
    return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}


def apply(conn):
    """Add safe archive metadata to profile definitions."""
    cursor = conn.cursor()
    columns = _columns(cursor, "profile_types")
    additions = (
        ("is_active", "INTEGER NOT NULL DEFAULT 1"),
        ("archived_at", "TEXT"),
        ("archived_by_user_id", "INTEGER"),
        ("archive_reason", "TEXT"),
    )
    for name, definition in additions:
        if name not in columns:
            cursor.execute(f"ALTER TABLE profile_types ADD COLUMN {name} {definition}")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_profile_types_active ON profile_types(is_active, name)"
    )
