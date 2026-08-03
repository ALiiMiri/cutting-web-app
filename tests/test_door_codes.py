import importlib
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import database
from door_hardware import normalize_door_hardware


ROOT = pathlib.Path(__file__).resolve().parents[1]


def hardware():
    return normalize_door_hardware(
        {
            "hinge_brand": "کاله", "hinge_color": "مشکی", "hinge_count": 3,
            "has_handle": False,
        }
    )


class DoorCodeMigrationTests(unittest.TestCase):
    def test_existing_door_is_backfilled_without_losing_location_or_quantity(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(
            """
            CREATE TABLE projects(id INTEGER PRIMARY KEY);
            CREATE TABLE doors(id INTEGER PRIMARY KEY,project_id INTEGER,location TEXT,quantity INTEGER);
            INSERT INTO projects VALUES(1);
            INSERT INTO doors VALUES(7,1,'اتاق مدیر',3);
            """
        )
        importlib.import_module("migrations.031_door_codes_and_locations").apply(conn)
        self.assertEqual(
            conn.execute("SELECT door_code,location,quantity FROM doors").fetchone(),
            ("D-01", "اتاق مدیر", 3),
        )
        self.assertEqual(
            conn.execute(
                "SELECT door_id,location,quantity FROM door_installation_locations"
            ).fetchone(),
            (7, "اتاق مدیر", 3),
        )
        self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        conn.close()


class DoorCodeDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.temp.name) / "door-code.db"
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(
            """
            CREATE TABLE projects(id INTEGER PRIMARY KEY);
            CREATE TABLE doors(
                id INTEGER PRIMARY KEY AUTOINCREMENT,project_id INTEGER,location TEXT,
                width REAL,height REAL,quantity INTEGER,direction TEXT,row_color_tag TEXT,
                installation_bracket_mode TEXT DEFAULT 'profile'
            );
            CREATE TABLE custom_columns(id INTEGER PRIMARY KEY,column_name TEXT UNIQUE);
            CREATE TABLE door_custom_values(
                door_id INTEGER,column_id INTEGER,value TEXT,PRIMARY KEY(door_id,column_id)
            );
            INSERT INTO projects VALUES(1);
            """
        )
        importlib.import_module("migrations.027_door_hardware").apply(conn)
        importlib.import_module("migrations.030_optional_handle_model").apply(conn)
        importlib.import_module("migrations.031_door_codes_and_locations").apply(conn)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_create_and_update_aggregate_location_quantities(self):
        with mock.patch.object(database, "DB_NAME", str(self.path)):
            door_id = database.add_door_code_with_hardware_db(
                1, "D-01", 90, 210, "راست",
                [{"location": "اتاق یک", "quantity": 2}, {"location": "اتاق دو", "quantity": 1}],
                hardware(),
            )
            loaded = database.get_doors_for_project_db(1)[0]
            updated = database.update_door_code_with_hardware_db(
                1, door_id, "D-01", 90, 210, "راست",
                [{"location": "طبقه اول", "quantity": 4}], hardware(),
            )
            reloaded = database.get_doors_for_project_db(1)[0]
        self.assertEqual(loaded["quantity"], 3)
        self.assertEqual(len(loaded["installation_locations"]), 2)
        self.assertTrue(updated)
        self.assertEqual(reloaded["quantity"], 4)
        self.assertEqual(reloaded["installation_locations"][0]["location"], "طبقه اول")

    def test_door_code_is_unique_inside_project_case_insensitively(self):
        with mock.patch.object(database, "DB_NAME", str(self.path)):
            first = database.add_door_code_with_hardware_db(
                1, "D-01", 90, 210, "راست", [{"location": "الف", "quantity": 1}], hardware()
            )
            duplicate = database.add_door_code_with_hardware_db(
                1, "d-01", 90, 210, "راست", [{"location": "ب", "quantity": 1}], hardware()
            )
        self.assertIsInstance(first, int)
        self.assertEqual(duplicate, "duplicate_code")


class InstallerUiTests(unittest.TestCase):
    def test_installer_output_has_code_location_and_quantity(self):
        template = (ROOT / "templates" / "installer_report.html").read_text(encoding="utf-8")
        self.assertIn("کد درب", template)
        self.assertIn("محل نصب", template)
        self.assertIn("row.quantity", template)
        self.assertIn("export_installer_report_excel", template)


if __name__ == "__main__":
    unittest.main()
