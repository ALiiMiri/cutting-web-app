def apply(conn):
    """Store each user's preferred orders dashboard layout."""
    cursor = conn.cursor()
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(users)")}
    if "orders_view_preference" not in columns:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN orders_view_preference TEXT NOT NULL DEFAULT 'table'
            CHECK (orders_view_preference IN ('table', 'cards'))
            """
        )
