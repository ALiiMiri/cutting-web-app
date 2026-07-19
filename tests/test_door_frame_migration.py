import importlib
import sqlite3
import unittest

import db_migrations  # Adds the migrations directory to the import path.


class DoorFrameMigrationTests(unittest.TestCase):
    def test_legacy_frame_values_and_options_are_normalized(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            """
            CREATE TABLE doors (id INTEGER PRIMARY KEY);
            CREATE TABLE custom_columns (
                id INTEGER PRIMARY KEY,
                column_name TEXT UNIQUE,
                display_name TEXT,
                column_type TEXT,
                is_active INTEGER
            );
            CREATE TABLE custom_column_options (
                id INTEGER PRIMARY KEY,
                column_id INTEGER,
                option_value TEXT
            );
            CREATE TABLE door_custom_values (
                door_id INTEGER,
                column_id INTEGER,
                value TEXT,
                PRIMARY KEY (door_id, column_id)
            );
            INSERT INTO custom_columns
                (id,column_name,display_name,column_type,is_active)
            VALUES (7,'kolaft','کلاف','dropdown',1);
            INSERT INTO custom_column_options(column_id,option_value)
            VALUES (7,'دو طرفه'),(7,'سه طرفه'),(7,'یک طرفه'),(7,'بدون کلافت');
            INSERT INTO doors(id) VALUES (1),(2),(3);
            INSERT INTO door_custom_values(door_id,column_id,value)
            VALUES (1,7,'دو طرفه'),(2,7,'یک طرفه');
            """
        )

        migration = importlib.import_module("019_door_frame_type")
        migration.apply(conn)

        column = conn.execute(
            "SELECT display_name,column_type FROM custom_columns WHERE id=7"
        ).fetchone()
        options = [
            row[0]
            for row in conn.execute(
                "SELECT option_value FROM custom_column_options WHERE column_id=7 ORDER BY id"
            )
        ]
        values = dict(
            conn.execute(
                "SELECT door_id,value FROM door_custom_values WHERE column_id=7 ORDER BY door_id"
            )
        )
        conn.close()

        self.assertEqual(column, ("نوع چارچوب", "dropdown"))
        self.assertEqual(options, ["سه طرفه", "دو طرفه"])
        self.assertEqual(values, {1: "دو طرفه", 2: "سه طرفه", 3: "سه طرفه"})


if __name__ == "__main__":
    unittest.main()
