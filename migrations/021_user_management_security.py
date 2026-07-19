def apply(conn):
    """Add session invalidation and an auditable user-management history."""
    cursor = conn.cursor()
    user_columns = {row[1] for row in cursor.execute("PRAGMA table_info(users)")}
    if "session_version" not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            target_user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (target_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_activity_created
            ON user_activity_logs(created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_activity_actor
            ON user_activity_logs(actor_user_id)
        """
    )
