import os
import sqlite3
import tempfile
import unittest

import database
from test_inventory_application import SCHEMA


class InventoryCorrectionTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.old_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO profile_types (id,name) VALUES (1,'پروفیل')")
        conn.execute(
            "INSERT INTO custom_column_options (column_id,option_value) VALUES (1,'پروفیل')"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_NAME = self.old_db_name
        os.unlink(self.db_path)

    def value(self, query, params=()):
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(query, params).fetchone()
        conn.close()
        return row[0] if row else None

    def test_stock_correction_requires_reason_and_is_reversible(self):
        blocked = database.correct_inventory_stock(1, 2, 5, "", actor_user_id=None)
        self.assertEqual(blocked["status"], "validation_error")
        self.assertEqual(self.value("SELECT COUNT(*) FROM inventory_operations"), 0)

        result = database.correct_inventory_stock(1, 2, 5, "شمارش اصلاح شد")
        self.assertEqual(result["status"], "success")
        self.assertEqual(
            self.value("SELECT quantity FROM inventory_items WHERE profile_type_id=1 AND color_id=2"),
            5,
        )
        latest = database.get_latest_reversible_inventory_operation()
        undo = database.undo_latest_inventory_operation(latest["id"], None, "ثبت اشتباه بود")
        self.assertEqual(undo["status"], "success")
        self.assertEqual(
            self.value("SELECT quantity FROM inventory_items WHERE profile_type_id=1 AND color_id=2"),
            0,
        )

    def test_stock_correction_cannot_make_inventory_negative(self):
        result = database.correct_inventory_stock(1, 2, -1, "اصلاح تعداد")
        self.assertEqual(result["status"], "validation_error")
        self.assertEqual(self.value("SELECT COUNT(*) FROM inventory_operations"), 0)

    def test_unused_profile_is_deleted(self):
        result = database.delete_profile_type(1, reason="ثبت اشتباه")
        self.assertEqual(result["status"], "deleted")
        self.assertIsNone(self.value("SELECT id FROM profile_types WHERE id=1"))

    def test_used_profile_is_archived_and_can_be_reactivated(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO projects (id,customer_name,project_code) VALUES (1,'مشتری','1001')")
        conn.execute("INSERT INTO doors (id,project_id) VALUES (1,1)")
        conn.execute(
            "INSERT INTO door_custom_values (door_id,column_id,value) VALUES (1,1,'پروفیل')"
        )
        conn.commit()
        conn.close()

        result = database.delete_profile_type(1, reason="تعریف اشتباه")
        self.assertEqual(result["status"], "archived")
        self.assertEqual(self.value("SELECT is_active FROM profile_types WHERE id=1"), 0)
        self.assertEqual(
            self.value("SELECT COUNT(*) FROM custom_column_options WHERE option_value='پروفیل'"),
            0,
        )
        self.assertTrue(database.reactivate_profile_type(1))
        self.assertEqual(self.value("SELECT is_active FROM profile_types WHERE id=1"), 1)


if __name__ == "__main__":
    unittest.main()
