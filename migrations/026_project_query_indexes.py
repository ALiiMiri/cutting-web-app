"""Add the indexes used by the orders dashboard and project detail queries."""


INDEX_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS idx_projects_active_id
    ON projects(id DESC)
    WHERE archived_at IS NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_active_assignee_id
    ON projects(assigned_to_user_id, id DESC)
    WHERE archived_at IS NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_active_customer_id
    ON projects(customer_name, id DESC)
    WHERE archived_at IS NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_active_order_ref_id
    ON projects(order_ref, id DESC)
    WHERE archived_at IS NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_active_date_id
    ON projects(date_shamsi, id DESC)
    WHERE archived_at IS NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_projects_project_code
    ON projects(project_code)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_doors_project_id
    ON doors(project_id, id)
    """,
)


def apply(conn):
    cursor = conn.cursor()
    for statement in INDEX_STATEMENTS:
        cursor.execute(statement)
