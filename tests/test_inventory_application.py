import os
import sqlite3
import tempfile
import unittest

import database


SCHEMA = """
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    customer_name TEXT,
    project_code TEXT
);
CREATE TABLE doors (id INTEGER PRIMARY KEY, project_id INTEGER);
CREATE TABLE custom_columns (
    id INTEGER PRIMARY KEY, column_name TEXT UNIQUE, display_name TEXT, column_type TEXT
);
CREATE TABLE custom_column_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT, column_id INTEGER, option_value TEXT,
    UNIQUE(column_id, option_value)
);
CREATE TABLE door_custom_values (
    door_id INTEGER, column_id INTEGER, value TEXT, PRIMARY KEY(door_id,column_id)
);
INSERT INTO custom_columns (id,column_name,display_name,column_type)
VALUES (1,'noe_profile','نوع پروفیل','dropdown'),(2,'rang','رنگ','dropdown');
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    role TEXT
);
CREATE TABLE profile_types (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    min_waste REAL DEFAULT 70,
    weight_per_meter REAL DEFAULT 1.9
    ,is_active INTEGER NOT NULL DEFAULT 1
    ,archived_at TEXT
    ,archived_by_user_id INTEGER
    ,archive_reason TEXT
);
CREATE TABLE profile_colors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    hex_code TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
INSERT INTO profile_colors (id, name, hex_code) VALUES
    (1, 'تعیین‌نشده', '#9ca3af'), (2, 'مشکی', '#111827'), (3, 'سفید', '#ffffff');
CREATE TABLE inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_type_id INTEGER NOT NULL,
    color_id INTEGER NOT NULL DEFAULT 1,
    quantity INTEGER DEFAULT 0,
    last_updated TEXT,
    UNIQUE(profile_type_id, color_id)
);
CREATE TABLE inventory_pieces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_type_id INTEGER NOT NULL,
    color_id INTEGER NOT NULL DEFAULT 1,
    length REAL NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE inventory_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_type_id INTEGER NOT NULL,
    change_type TEXT NOT NULL,
    quantity INTEGER,
    length REAL,
    piece_id INTEGER,
    project_id INTEGER,
    description TEXT,
    timestamp TEXT,
    operation_id INTEGER
    ,color_id INTEGER DEFAULT 1
    ,color_name_snapshot TEXT DEFAULT 'تعیین‌نشده'
);
CREATE TABLE inventory_deductions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    profile_type_id INTEGER NOT NULL,
    color_id INTEGER NOT NULL DEFAULT 1,
    color_name_snapshot TEXT NOT NULL DEFAULT 'تعیین‌نشده',
    quantity_deducted INTEGER NOT NULL,
    deduction_date TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, profile_type_id, color_id)
);
CREATE TABLE inventory_cutting_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL UNIQUE,
    applied_at TEXT NOT NULL,
    profile_count INTEGER NOT NULL DEFAULT 0,
    total_stock_deducted INTEGER NOT NULL DEFAULT 0,
    pieces_consumed INTEGER NOT NULL DEFAULT 0,
    pieces_returned INTEGER NOT NULL DEFAULT 0,
    operation_id INTEGER
);
CREATE TABLE inventory_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL,
    project_id INTEGER,
    actor_user_id INTEGER,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'applied',
    is_reversible INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    reversed_at TEXT,
    reversed_by_user_id INTEGER,
    reversal_reason TEXT,
    reverses_operation_id INTEGER,
    reversal_operation_id INTEGER
);
CREATE TABLE inventory_operation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL,
    sequence_no INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    profile_type_id INTEGER,
    profile_name TEXT NOT NULL,
    quantity_delta INTEGER,
    before_quantity INTEGER,
    after_quantity INTEGER,
    piece_id INTEGER,
    length REAL
    ,color_id INTEGER DEFAULT 1
    ,color_name_snapshot TEXT DEFAULT 'تعیین‌نشده'
);
CREATE TABLE inventory_waste_items (
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
    updated_at TEXT NOT NULL
    ,color_id INTEGER DEFAULT 1
    ,color_name_snapshot TEXT DEFAULT 'تعیین‌نشده'
);
CREATE TABLE inventory_waste_movements (
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
    created_at TEXT NOT NULL
);
"""


class InventoryApplicationTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.old_db_name = database.DB_NAME
        database.DB_NAME = self.db_path

        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO projects (id, customer_name, project_code) VALUES (1, 'مشتری', '1001')"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_NAME = self.old_db_name
        os.unlink(self.db_path)

    def add_profile(self, profile_id, name, stock, min_waste=70):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO profile_types (id, name, min_waste) VALUES (?, ?, ?)",
            (profile_id, name, min_waste),
        )
        conn.execute(
            "INSERT INTO inventory_items (profile_type_id, color_id, quantity) VALUES (?, 1, ?)",
            (profile_id, stock),
        )
        conn.commit()
        conn.close()

    def fetch_value(self, query, params=()):
        conn = sqlite3.connect(self.db_path)
        value = conn.execute(query, params).fetchone()[0]
        conn.close()
        return value

    def apply(self, requirements, used_pieces=None):
        return database.apply_cutting_plan_inventory_transaction(
            1,
            {"customer_name": "مشتری", "project_code": "1001"},
            requirements,
            used_pieces or {},
        )

    def test_insufficient_one_profile_changes_nothing(self):
        self.add_profile(1, "موجود", 5)
        self.add_profile(2, "ناموجود", 0)

        result = self.apply(
            {
                "موجود": {"bins": [{"remaining": 80, "from_inventory_piece": False}]},
                "ناموجود": {"bins": [{"remaining": 20, "from_inventory_piece": False}]},
            }
        )

        self.assertEqual(result["status"], "validation_error")
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"), 5)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_logs"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_deductions"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_cutting_applications"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_operations"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_waste_items"), 0)

    def test_deduction_uses_only_the_requested_color(self):
        self.add_profile(1, "پروفیل", 0)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO inventory_items (profile_type_id, color_id, quantity) VALUES (1, 2, 1)"
        )
        conn.execute(
            "INSERT INTO inventory_items (profile_type_id, color_id, quantity) VALUES (1, 3, 10)"
        )
        conn.commit()
        conn.close()

        result = self.apply(
            {
                "پروفیل ⟡ مشکی": {
                    "profile_name": "پروفیل",
                    "color_name": "مشکی",
                    "bins": [
                        {"remaining": 80, "from_inventory_piece": False},
                        {"remaining": 80, "from_inventory_piece": False},
                    ],
                }
            }
        )

        self.assertEqual(result["status"], "validation_error")
        self.assertEqual(
            self.fetch_value(
                "SELECT quantity FROM inventory_items WHERE profile_type_id=1 AND color_id=2"
            ),
            1,
        )
        self.assertEqual(
            self.fetch_value(
                "SELECT quantity FROM inventory_items WHERE profile_type_id=1 AND color_id=3"
            ),
            10,
        )

    def test_success_is_complete_and_idempotent(self):
        self.add_profile(1, "اول", 3)
        self.add_profile(2, "دوم", 2)
        requirements = {
            "اول": {"bins": [{"remaining": 80, "from_inventory_piece": False}]},
            "دوم": {"bins": [{"remaining": 10, "from_inventory_piece": False}]},
        }

        result = self.apply(requirements)

        self.assertEqual(result["status"], "success")
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"), 2)
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 2"), 1)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_deductions"), 2)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_cutting_applications"), 1)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_operations"), 1)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_pieces"), 1)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_waste_items"), 1)

        second_result = self.apply(requirements)
        self.assertEqual(second_result["status"], "already_applied")
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"), 2)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_logs"), 3)

    def test_trailing_space_in_stored_profile_name_does_not_block_application(self):
        self.add_profile(1, "پروفیل جدید فریم لس ", 5)

        result = self.apply(
            {
                "پروفیل جدید فریم لس": {
                    "bins": [{"remaining": 20, "from_inventory_piece": False}]
                }
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"),
            4,
        )

    def test_remaining_from_consumed_piece_returns_to_inventory(self):
        self.add_profile(1, "پروفیل", 0, min_waste=70)
        conn = sqlite3.connect(self.db_path)
        piece_id = conn.execute(
            "INSERT INTO inventory_pieces (profile_type_id, length) VALUES (1, 300)"
        ).lastrowid
        conn.commit()
        conn.close()

        result = self.apply(
            {
                "پروفیل": {
                    "bins": [
                        {
                            "remaining": 100,
                            "from_inventory_piece": True,
                            "inventory_piece_id": piece_id,
                        }
                    ]
                }
            },
            {"پروفیل": [piece_id]},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_pieces WHERE id = ?", (piece_id,)), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_pieces"), 1)
        self.assertAlmostEqual(self.fetch_value("SELECT length FROM inventory_pieces"), 100)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_deductions"), 0)
        self.assertEqual(self.fetch_value("SELECT pieces_consumed FROM inventory_cutting_applications"), 1)
        self.assertEqual(self.fetch_value("SELECT pieces_returned FROM inventory_cutting_applications"), 1)

    def test_legacy_deduction_is_blocked_without_more_changes(self):
        self.add_profile(1, "پروفیل", 4)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO inventory_deductions (project_id, profile_type_id, quantity_deducted) VALUES (1, 1, 1)"
        )
        conn.commit()
        conn.close()

        result = self.apply(
            {"پروفیل": {"bins": [{"remaining": 50, "from_inventory_piece": False}]}}
        )

        self.assertEqual(result["status"], "legacy_unverified")
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"), 4)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_logs"), 0)

    def test_database_failure_rolls_back_every_inventory_change(self):
        self.add_profile(1, "پروفیل", 3)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TRIGGER fail_application_insert
            BEFORE INSERT ON inventory_cutting_applications
            BEGIN
                SELECT RAISE(ABORT, 'forced failure');
            END
            """
        )
        conn.commit()
        conn.close()

        result = self.apply(
            {"پروفیل": {"bins": [{"remaining": 90, "from_inventory_piece": False}]}}
        )

        self.assertEqual(result["status"], "database_error")
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"), 3)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_logs"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_deductions"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_pieces"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_operations"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_waste_items"), 0)


if __name__ == "__main__":
    unittest.main()
