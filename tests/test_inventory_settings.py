import os
import sqlite3
import tempfile
import unittest

import database


class InventorySettingsCompatibilityTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.old_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE cutting_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                value TEXT,
                description TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_NAME = self.old_db_name
        os.unlink(self.db_path)

    def test_legacy_names_are_exposed_under_canonical_names(self):
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            "INSERT INTO cutting_settings(name,value) VALUES (?,?)",
            [("use_inventory", "true"), ("prefer_pieces", "false")],
        )
        conn.commit()
        conn.close()

        settings = database.get_inventory_settings()
        self.assertTrue(settings["use_inventory_for_cutting"])
        self.assertFalse(settings["prefer_inventory_pieces"])
        self.assertEqual(settings["inventory_optimization_strategy"], "minimize_waste")

    def test_canonical_values_take_precedence_and_updates_sync_legacy_names(self):
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            "INSERT INTO cutting_settings(name,value) VALUES (?,?)",
            [("use_inventory", "false"), ("use_inventory_for_cutting", "true")],
        )
        conn.commit()
        conn.close()

        self.assertTrue(database.get_inventory_settings()["use_inventory_for_cutting"])
        self.assertTrue(
            database.update_inventory_settings(
                {"use_inventory_for_cutting": False, "prefer_inventory_pieces": True}
            )
        )

        conn = sqlite3.connect(self.db_path)
        stored = dict(conn.execute("SELECT name,value FROM cutting_settings").fetchall())
        conn.close()
        self.assertEqual(stored["use_inventory_for_cutting"], "False")
        self.assertEqual(stored["use_inventory"], "False")
        self.assertEqual(stored["prefer_inventory_pieces"], "True")
        self.assertEqual(stored["prefer_pieces"], "True")


if __name__ == "__main__":
    unittest.main()
