"""Create persistent, multi-project cutting orders and inventory reservations."""


def _columns(cursor, table_name):
    return {
        row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def apply(conn):
    cursor = conn.cursor()

    if "archived_at" not in _columns(cursor, "projects"):
        cursor.execute("ALTER TABLE projects ADD COLUMN archived_at TEXT")
    if "source_cutting_order_id" not in _columns(cursor, "inventory_pieces"):
        cursor.execute(
            "ALTER TABLE inventory_pieces ADD COLUMN source_cutting_order_id INTEGER"
        )
    if "source_cutting_bar_id" not in _columns(cursor, "inventory_pieces"):
        cursor.execute(
            "ALTER TABLE inventory_pieces ADD COLUMN source_cutting_bar_id INTEGER"
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cutting_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE,
            version INTEGER NOT NULL DEFAULT 1,
            parent_order_id INTEGER,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN (
                    'draft','reserved','sent_to_factory','partially_cut',
                    'completed','cancelled'
                )),
            fingerprint TEXT NOT NULL,
            settings_snapshot_json TEXT NOT NULL,
            created_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            reserved_at TEXT,
            reserved_by_user_id INTEGER,
            sent_at TEXT,
            sent_by_user_id INTEGER,
            locked_at TEXT,
            completed_at TEXT,
            cancelled_at TEXT,
            cancelled_by_user_id INTEGER,
            cancellation_reason TEXT,
            FOREIGN KEY(parent_order_id) REFERENCES cutting_orders(id),
            FOREIGN KEY(created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(reserved_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(sent_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(cancelled_by_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cutting_order_projects (
            order_id INTEGER NOT NULL,
            project_id INTEGER,
            project_name_snapshot TEXT NOT NULL,
            project_order_ref_snapshot TEXT,
            project_code_snapshot TEXT,
            measurement_unit_snapshot TEXT NOT NULL DEFAULT 'cm',
            PRIMARY KEY(order_id, project_id),
            FOREIGN KEY(order_id) REFERENCES cutting_orders(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE RESTRICT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cutting_order_bars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            sequence_no INTEGER NOT NULL,
            profile_type_id INTEGER NOT NULL,
            color_id INTEGER NOT NULL,
            profile_name_snapshot TEXT NOT NULL,
            color_name_snapshot TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK(source_type IN ('new_stock','inventory_piece')),
            source_inventory_piece_id INTEGER,
            initial_length REAL NOT NULL CHECK(initial_length > 0),
            planned_remaining REAL NOT NULL CHECK(planned_remaining >= 0),
            min_waste_snapshot REAL NOT NULL CHECK(min_waste_snapshot >= 0),
            weight_per_meter_snapshot REAL NOT NULL CHECK(weight_per_meter_snapshot > 0),
            blade_width REAL NOT NULL CHECK(blade_width >= 0),
            kerf_loss REAL NOT NULL CHECK(kerf_loss >= 0),
            status TEXT NOT NULL DEFAULT 'planned'
                CHECK(status IN ('planned','reserved','cut','cancelled')),
            reserved_at TEXT,
            cut_at TEXT,
            cut_by_user_id INTEGER,
            actual_remaining REAL,
            inventory_operation_id INTEGER,
            returned_piece_id INTEGER,
            waste_item_id INTEGER,
            UNIQUE(order_id, sequence_no),
            FOREIGN KEY(order_id) REFERENCES cutting_orders(id) ON DELETE CASCADE,
            FOREIGN KEY(profile_type_id) REFERENCES profile_types(id) ON DELETE RESTRICT,
            FOREIGN KEY(color_id) REFERENCES profile_colors(id) ON DELETE RESTRICT,
            FOREIGN KEY(cut_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(inventory_operation_id) REFERENCES inventory_operations(id),
            FOREIGN KEY(returned_piece_id) REFERENCES inventory_pieces(id),
            FOREIGN KEY(waste_item_id) REFERENCES inventory_waste_items(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cutting_order_pieces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bar_id INTEGER NOT NULL,
            sequence_no INTEGER NOT NULL,
            project_id INTEGER,
            project_name_snapshot TEXT,
            project_order_ref_snapshot TEXT,
            project_code_snapshot TEXT,
            door_id INTEGER,
            door_row_number INTEGER,
            door_location_snapshot TEXT,
            door_quantity_index INTEGER,
            member_type TEXT NOT NULL,
            member_label TEXT NOT NULL,
            cut_instruction TEXT NOT NULL,
            length REAL NOT NULL CHECK(length > 0),
            UNIQUE(bar_id, sequence_no),
            FOREIGN KEY(bar_id) REFERENCES cutting_order_bars(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY(door_id) REFERENCES doors(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            bar_id INTEGER NOT NULL UNIQUE,
            profile_type_id INTEGER NOT NULL,
            color_id INTEGER NOT NULL,
            resource_type TEXT NOT NULL CHECK(resource_type IN ('stock','piece')),
            inventory_piece_id INTEGER,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity = 1),
            status TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('active','released','consumed')),
            reserved_at TEXT NOT NULL,
            reserved_by_user_id INTEGER,
            released_at TEXT,
            released_by_user_id INTEGER,
            release_reason TEXT,
            consumed_at TEXT,
            consumed_by_user_id INTEGER,
            FOREIGN KEY(order_id) REFERENCES cutting_orders(id) ON DELETE CASCADE,
            FOREIGN KEY(bar_id) REFERENCES cutting_order_bars(id) ON DELETE CASCADE,
            FOREIGN KEY(profile_type_id) REFERENCES profile_types(id) ON DELETE RESTRICT,
            FOREIGN KEY(color_id) REFERENCES profile_colors(id) ON DELETE RESTRICT,
            FOREIGN KEY(reserved_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(released_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY(consumed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cutting_order_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            bar_id INTEGER,
            event_type TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            actor_user_id INTEGER,
            details_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES cutting_orders(id) ON DELETE CASCADE,
            FOREIGN KEY(bar_id) REFERENCES cutting_order_bars(id) ON DELETE SET NULL,
            FOREIGN KEY(actor_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cutting_orders_status ON cutting_orders(status, id DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cutting_order_projects_project ON cutting_order_projects(project_id, order_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cutting_order_bars_order ON cutting_order_bars(order_id, sequence_no)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cutting_order_pieces_project ON cutting_order_pieces(project_id, door_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_reservations_variant ON inventory_reservations(profile_type_id, color_id, resource_type, status)"
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_reservations_active_piece
        ON inventory_reservations(inventory_piece_id)
        WHERE status='active' AND resource_type='piece'
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cutting_order_events_order ON cutting_order_events(order_id, id)"
    )
