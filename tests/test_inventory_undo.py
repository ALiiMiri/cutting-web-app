import os
import sqlite3
import tempfile
import unittest

from test_inventory_application import SCHEMA
import database


class InventoryUndoTests(unittest.TestCase):
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
        requirements = {
            name: {
                **profile_data,
                "default_length": profile_data.get("default_length", 600),
            }
            for name, profile_data in requirements.items()
        }
        return database.apply_cutting_plan_inventory_transaction(
            1,
            {"customer_name": "مشتری", "project_code": "1001"},
            requirements,
            used_pieces or {},
        )

    def test_manual_stock_add_can_be_undone_with_audit_trail(self):
        self.add_profile(1, "پروفیل", 10)

        self.assertTrue(database.add_inventory_stock(1, 5, "ورود اشتباه", actor_user_id=None))
        latest = database.get_latest_reversible_inventory_operation()

        self.assertEqual(latest["operation_type"], "manual_add_stock")
        self.assertTrue(latest["can_undo"])
        result = database.undo_latest_inventory_operation(latest["id"], None, "ثبت اشتباه")

        self.assertEqual(result["status"], "success")
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"), 10)
        self.assertEqual(self.fetch_value("SELECT status FROM inventory_operations WHERE id = ?", (latest["id"],)), "reversed")
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_operations"), 2)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_logs"), 2)

    def test_only_latest_operation_can_be_undone(self):
        self.add_profile(1, "پروفیل", 10)
        database.add_inventory_stock(1, 1, "اول")
        first_id = database.get_latest_reversible_inventory_operation()["id"]
        database.add_inventory_stock(1, 2, "دوم")

        result = database.undo_latest_inventory_operation(first_id, None, "عملیات اشتباه")

        self.assertEqual(result["status"], "not_latest")
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"), 13)

    def test_external_stock_change_blocks_undo(self):
        self.add_profile(1, "پروفیل", 10)
        database.add_inventory_stock(1, 5, "افزایش")
        latest = database.get_latest_reversible_inventory_operation()
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE inventory_items SET quantity = 14 WHERE profile_type_id = 1")
        conn.commit()
        conn.close()

        preview = database.get_latest_reversible_inventory_operation()
        result = database.undo_latest_inventory_operation(latest["id"], None, "تلاش بازگشت")

        self.assertFalse(preview["can_undo"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"), 14)

    def test_cutting_plan_undo_restores_stock_and_project_state(self):
        self.add_profile(1, "پروفیل", 3)
        result = self.apply(
            {
                "پروفیل": {
                    "min_waste": 70,
                    "bins": [
                        {
                            "remaining": 10,
                            "initial_length": 600,
                            "from_inventory_piece": False,
                        }
                    ],
                }
            }
        )
        self.assertEqual(result["status"], "success")
        latest = database.get_latest_reversible_inventory_operation()

        undo = database.undo_latest_inventory_operation(latest["id"], None, "محاسبه مجدد")

        self.assertEqual(undo["status"], "success")
        self.assertEqual(self.fetch_value("SELECT quantity FROM inventory_items WHERE profile_type_id = 1"), 3)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_pieces"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_deductions"), 0)
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_cutting_applications"), 0)
        self.assertEqual(
            self.fetch_value("SELECT status FROM inventory_waste_items LIMIT 1"),
            "reversed",
        )

    def test_cutting_undo_restores_consumed_piece_and_removes_its_remainder(self):
        self.add_profile(1, "پروفیل", 0)
        conn = sqlite3.connect(self.db_path)
        original_piece_id = conn.execute(
            "INSERT INTO inventory_pieces (profile_type_id, length) VALUES (1, 300)"
        ).lastrowid
        conn.commit()
        conn.close()

        result = self.apply(
            {
                "پروفیل": {
                    "min_waste": 70,
                    "bins": [
                        {
                            "remaining": 100,
                            "initial_length": 300,
                            "from_inventory_piece": True,
                            "inventory_piece_id": original_piece_id,
                        }
                    ],
                }
            },
            {"پروفیل": [original_piece_id]},
        )
        self.assertEqual(result["status"], "success")
        latest = database.get_latest_reversible_inventory_operation()

        undo = database.undo_latest_inventory_operation(latest["id"], None, "محاسبه مجدد")

        self.assertEqual(undo["status"], "success")
        conn = sqlite3.connect(self.db_path)
        pieces = conn.execute(
            "SELECT id, profile_type_id, length FROM inventory_pieces ORDER BY id"
        ).fetchall()
        conn.close()
        self.assertEqual(pieces, [(original_piece_id, 1, 300.0)])
        self.assertEqual(self.fetch_value("SELECT COUNT(*) FROM inventory_cutting_applications"), 0)

    def test_processed_waste_blocks_cutting_undo(self):
        self.add_profile(1, "پروفیل", 3)
        result = self.apply(
            {
                "پروفیل": {
                    "min_waste": 70,
                    "bins": [
                        {
                            "remaining": 10,
                            "initial_length": 600,
                            "from_inventory_piece": False,
                        }
                    ],
                }
            }
        )
        self.assertEqual(result["status"], "success")
        waste_id = self.fetch_value("SELECT id FROM inventory_waste_items LIMIT 1")
        movement = database.update_waste_item(
            waste_id,
            "sold",
            actor_user_id=None,
            actual_weight="0.2",
            price_per_kg="1000",
            counterparty="خریدار",
            note="فروش آزمایشی",
        )
        self.assertEqual(movement["status"], "success")
        latest = database.get_latest_reversible_inventory_operation()

        undo = database.undo_latest_inventory_operation(latest["id"], None, "محاسبه مجدد")

        self.assertEqual(undo["status"], "blocked")
        self.assertEqual(self.fetch_value("SELECT status FROM inventory_waste_items"), "sold")
