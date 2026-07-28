import os
import sqlite3
import tempfile
import unittest

import database


class CustomColumnKeyTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.old_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE custom_columns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                column_name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                column_type TEXT DEFAULT 'text'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO custom_columns(column_name,display_name,is_active,column_type)
            VALUES ('rang','رنگ',1,'dropdown')
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_NAME = self.old_db_name
        os.unlink(self.db_path)

    def test_internal_key_is_generated_from_database_id(self):
        column_id = database.add_custom_column(
            display_name="نوع شیشه",
            column_type="dropdown",
        )

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT column_name,display_name,column_type FROM custom_columns WHERE id=?",
            (column_id,),
        ).fetchone()
        conn.close()

        self.assertEqual(row, (f"custom_{column_id}", "نوع شیشه", "dropdown"))

    def test_existing_system_keys_are_not_changed(self):
        database.add_custom_column(display_name="یادداشت", column_type="text")
        conn = sqlite3.connect(self.db_path)
        system_key = conn.execute(
            "SELECT column_name FROM custom_columns WHERE display_name='رنگ'"
        ).fetchone()[0]
        conn.close()

        self.assertEqual(system_key, "rang")

    def test_invalid_column_is_not_partially_created(self):
        self.assertIsNone(database.add_custom_column(display_name="", column_type="text"))
        self.assertIsNone(database.add_custom_column(display_name="ستون", column_type="number"))
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM custom_columns").fetchone()[0]
        conn.close()

        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
