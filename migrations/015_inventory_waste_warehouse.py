def apply(conn):
    """Create the traceable waste warehouse and its append-only movement history."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_waste_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cutting_operation_id INTEGER NOT NULL,
            project_id INTEGER,
            profile_type_id INTEGER,
            profile_name_snapshot TEXT NOT NULL,
            length_cm REAL NOT NULL,
            weight_per_meter_snapshot REAL NOT NULL,
            calculated_weight_kg REAL NOT NULL,
            actual_weight_kg REAL,
            source_type TEXT NOT NULL,
            source_piece_id INTEGER,
            status TEXT NOT NULL DEFAULT 'available',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (cutting_operation_id) REFERENCES inventory_operations (id),
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_waste_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            waste_item_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            previous_status TEXT NOT NULL,
            new_status TEXT NOT NULL,
            actual_weight_kg REAL,
            price_per_kg REAL,
            total_amount REAL,
            counterparty TEXT,
            note TEXT,
            actor_user_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (waste_item_id) REFERENCES inventory_waste_items (id) ON DELETE CASCADE,
            FOREIGN KEY (actor_user_id) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_waste_items_status ON inventory_waste_items(status, id DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_waste_items_profile ON inventory_waste_items(profile_type_id, status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_waste_items_project ON inventory_waste_items(project_id, status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_waste_items_operation ON inventory_waste_items(cutting_operation_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_waste_movements_item ON inventory_waste_movements(waste_item_id, id DESC)"
    )
