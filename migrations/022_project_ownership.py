def apply(conn):
    """Track project creator/assignee and seed only projects 17-19 for paniz."""
    cursor = conn.cursor()
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(projects)")}
    if "created_by_user_id" not in columns:
        cursor.execute(
            "ALTER TABLE projects ADD COLUMN created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        )
    if "assigned_to_user_id" not in columns:
        cursor.execute(
            "ALTER TABLE projects ADD COLUMN assigned_to_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL"
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS project_assignment_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            actor_user_id INTEGER,
            previous_assignee_user_id INTEGER,
            new_assignee_user_id INTEGER,
            action TEXT NOT NULL DEFAULT 'assign',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (previous_assignee_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (new_assignee_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_assignment_project ON project_assignment_logs(project_id, id DESC)"
    )

    paniz_row = cursor.execute(
        "SELECT id FROM users WHERE username='paniz' AND is_active=1"
    ).fetchone()
    if paniz_row:
        paniz_id = paniz_row[0]
        project_ids = (17, 18, 19)
        cursor.execute(
            """
            UPDATE projects
            SET created_by_user_id=?, assigned_to_user_id=?
            WHERE id IN (17,18,19)
              AND created_by_user_id IS NULL
              AND assigned_to_user_id IS NULL
            """,
            (paniz_id, paniz_id),
        )
        for project_id in project_ids:
            exists = cursor.execute(
                "SELECT 1 FROM projects WHERE id=? AND assigned_to_user_id=?",
                (project_id, paniz_id),
            ).fetchone()
            if exists:
                cursor.execute(
                    """
                    INSERT INTO project_assignment_logs(
                        project_id, previous_assignee_user_id,
                        new_assignee_user_id, action
                    ) VALUES (?, NULL, ?, 'initial_assignment')
                    """,
                    (project_id, paniz_id),
                )
