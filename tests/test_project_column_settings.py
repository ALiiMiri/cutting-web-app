import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import database


SCHEMA = """
CREATE TABLE projects (id INTEGER PRIMARY KEY, customer_name TEXT);
CREATE TABLE doors (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    location TEXT
);
CREATE TABLE custom_columns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    column_name TEXT UNIQUE,
    display_name TEXT,
    column_type TEXT DEFAULT 'text',
    is_active BOOLEAN DEFAULT 1
);
CREATE TABLE door_custom_values (
    door_id INTEGER,
    column_id INTEGER,
    value TEXT,
    PRIMARY KEY (door_id, column_id)
);
CREATE TABLE project_visible_columns (
    project_id INTEGER,
    column_key TEXT,
    is_visible BOOLEAN DEFAULT 1,
    PRIMARY KEY (project_id, column_key)
);
"""


class ProjectColumnSettingsTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db_patch = patch.object(database, "DB_NAME", self.db_path)
        self.db_patch.start()
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO projects(id, customer_name) VALUES (?, ?)",
            [(1, "اول"), (2, "دوم")],
        )
        conn.executemany(
            """
            INSERT INTO custom_columns(id, column_name, display_name, column_type, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            [
                (1, "rang", "رنگ", "dropdown"),
                (2, "custom_2", "نوع شیشه", "dropdown"),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.db_patch.stop()
        os.unlink(self.db_path)

    def test_built_in_field_starts_selected_and_reusable_field_starts_in_library(self):
        columns = database.get_project_custom_columns(1)
        states = {column["key"]: column for column in columns}
        self.assertTrue(states["rang"]["is_selected"])
        self.assertTrue(states["rang"]["is_visible"])
        self.assertFalse(states["custom_2"]["is_selected"])

    def test_selecting_field_changes_only_one_project(self):
        self.assertTrue(database.set_project_column_visibility(1, 2, True))
        first = {c["key"]: c for c in database.get_project_custom_columns(1)}
        second = {c["key"]: c for c in database.get_project_custom_columns(2)}
        self.assertTrue(first["custom_2"]["is_selected"])
        self.assertTrue(first["custom_2"]["is_visible"])
        self.assertFalse(second["custom_2"]["is_selected"])

    def test_hiding_field_does_not_delete_existing_door_value(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO doors(id, project_id, location) VALUES (10, 1, 'اتاق')")
        conn.execute(
            "INSERT INTO door_custom_values(door_id, column_id, value) VALUES (10, 2, 'سکوریت')"
        )
        conn.commit()
        conn.close()

        database.get_project_custom_columns(1)
        self.assertTrue(database.set_project_column_visibility(1, 2, False))
        columns = {c["key"]: c for c in database.get_project_custom_columns(1)}
        self.assertTrue(columns["custom_2"]["is_selected"])
        self.assertFalse(columns["custom_2"]["is_visible"])

        conn = sqlite3.connect(self.db_path)
        value = conn.execute(
            "SELECT value FROM door_custom_values WHERE door_id = 10 AND column_id = 2"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(value, "سکوریت")

    def test_removing_field_moves_it_to_library_even_when_it_has_data(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO doors(id, project_id, location) VALUES (10, 1, 'اتاق')")
        conn.execute(
            "INSERT INTO door_custom_values(door_id, column_id, value) VALUES (10, 2, 'سکوریت')"
        )
        conn.commit()
        conn.close()

        database.get_project_custom_columns(1)
        self.assertTrue(database.remove_project_column(1, 2))
        columns = {c["key"]: c for c in database.get_project_custom_columns(1)}
        self.assertFalse(columns["custom_2"]["is_selected"])

        conn = sqlite3.connect(self.db_path)
        value = conn.execute(
            "SELECT value FROM door_custom_values WHERE door_id = 10 AND column_id = 2"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(value, "سکوریت")


if __name__ == "__main__":
    unittest.main()
