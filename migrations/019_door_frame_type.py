THREE_SIDED = "سه طرفه"
TWO_SIDED = "دو طرفه"


def _table_exists(cursor, table_name):
    return cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone() is not None


def apply(conn):
    """Rename the legacy kolaft field and make frame geometry unambiguous."""
    cursor = conn.cursor()
    required_tables = {
        "custom_columns",
        "custom_column_options",
        "door_custom_values",
        "doors",
    }
    if not all(_table_exists(cursor, table) for table in required_tables):
        return

    row = cursor.execute(
        "SELECT id FROM custom_columns WHERE column_name = 'kolaft'"
    ).fetchone()
    if not row:
        cursor.execute(
            """
            INSERT INTO custom_columns(column_name,display_name,column_type,is_active)
            VALUES ('kolaft','نوع چارچوب','dropdown',1)
            """
        )
        column_id = cursor.lastrowid
    else:
        column_id = row[0]
        cursor.execute(
            """
            UPDATE custom_columns
            SET display_name='نوع چارچوب', column_type='dropdown', is_active=1
            WHERE id=?
            """,
            (column_id,),
        )

    # Option IDs are not referenced by door values, so replacing this list is
    # safe and prevents the invalid one-sided choices from returning.
    cursor.execute("DELETE FROM custom_column_options WHERE column_id=?", (column_id,))
    cursor.executemany(
        "INSERT INTO custom_column_options(column_id,option_value) VALUES (?,?)",
        ((column_id, THREE_SIDED), (column_id, TWO_SIDED)),
    )

    # Preserve the calculation that was historically used for every existing
    # door: only an explicit two-sided value removes the upper frame member.
    cursor.execute(
        """
        UPDATE door_custom_values
        SET value=?
        WHERE column_id=? AND TRIM(COALESCE(value,'')) = ?
        """,
        (TWO_SIDED, column_id, TWO_SIDED),
    )
    cursor.execute(
        """
        UPDATE door_custom_values
        SET value=?
        WHERE column_id=? AND TRIM(COALESCE(value,'')) != ?
        """,
        (THREE_SIDED, column_id, TWO_SIDED),
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO door_custom_values(door_id,column_id,value)
        SELECT id, ?, ? FROM doors
        """,
        (column_id, THREE_SIDED),
    )
