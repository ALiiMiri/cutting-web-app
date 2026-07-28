def apply(conn):
    """Persist the exact applied cutting plan for later reports and exports."""
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(inventory_cutting_applications)")
    }
    if "plan_snapshot_json" not in columns:
        conn.execute(
            "ALTER TABLE inventory_cutting_applications ADD COLUMN plan_snapshot_json TEXT"
        )
