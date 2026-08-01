import importlib
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import database
from door_hardware import HardwareValidationError, normalize_door_hardware


ROOT = pathlib.Path(__file__).resolve().parents[1]


def payload(**overrides):
    data = {
        "hinge_brand": "کاله",
        "hinge_color": "مشکی",
        "hinge_count": 3,
        "has_handle": True,
        "handle_type": "two_piece",
        "handle_brand": "ایران",
        "handle_model": "R210",
        "handle_color": "مشکی مات",
        "lock_source": "separate",
        "lock_brand": "داف",
        "lock_model": "B45",
        "cylinder_brand": "یال",
        "cylinder_model": "70",
    }
    data.update(overrides)
    return data


class DoorHardwareValidationTests(unittest.TestCase):
    def test_two_piece_requires_separate_lock_and_cylinder(self):
        with self.assertRaises(HardwareValidationError):
            normalize_door_hardware(payload(cylinder_model=""))

    def test_single_rosette_never_keeps_a_cylinder(self):
        result = normalize_door_hardware(
            payload(
                handle_type="single_rosette",
                lock_source="own_brand",
                lock_brand="نباید ذخیره شود",
                lock_model="نباید ذخیره شود",
            )
        )
        self.assertEqual(result["lock_source"], "own_brand")
        self.assertIsNone(result["lock_brand"])
        self.assertIsNone(result["lock_model"])
        self.assertIsNone(result["cylinder_brand"])
        self.assertIsNone(result["cylinder_model"])

    def test_without_handle_clears_all_handle_parts(self):
        result = normalize_door_hardware(payload(has_handle=False))
        self.assertEqual(result["has_handle"], 0)
        for key in (
            "handle_type",
            "handle_brand",
            "handle_model",
            "handle_color",
            "lock_source",
            "lock_brand",
            "lock_model",
            "cylinder_brand",
            "cylinder_model",
        ):
            self.assertIsNone(result[key])


class DoorHardwareDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.directory.name) / "hardware.db"
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
            CREATE TABLE projects(id INTEGER PRIMARY KEY);
            CREATE TABLE doors(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                location TEXT,
                width REAL,
                height REAL,
                quantity INTEGER,
                direction TEXT,
                row_color_tag TEXT
            );
            CREATE TABLE custom_columns(
                id INTEGER PRIMARY KEY,
                column_name TEXT UNIQUE,
                display_name TEXT
            );
            CREATE TABLE door_custom_values(
                door_id INTEGER,
                column_id INTEGER,
                value TEXT,
                PRIMARY KEY(door_id,column_id)
            );
            INSERT INTO projects(id) VALUES(10),(20);
            INSERT INTO custom_columns(id,column_name,display_name)
            VALUES(1,'kolaft','نوع چارچوب');
            """
        )
        importlib.import_module("migrations.027_door_hardware").apply(connection)
        connection.commit()
        connection.close()

    def tearDown(self):
        self.directory.cleanup()

    def test_create_and_update_keep_door_and_hardware_atomic(self):
        hardware = normalize_door_hardware(payload())
        with mock.patch.object(database, "DB_NAME", str(self.db_path)):
            door_id = database.add_door_with_hardware_db(
                10, "اتاق مدیریت", 90, 210, 1, "راست", hardware
            )
            updated = database.update_door_with_hardware_db(
                10,
                door_id,
                "اتاق مدیریت",
                95,
                210,
                1,
                "چپ",
                normalize_door_hardware(
                    payload(handle_type="single_rosette", lock_source="own_brand")
                ),
            )
            loaded = database.get_doors_for_project_db(10)

        self.assertTrue(updated)
        connection = sqlite3.connect(self.db_path)
        door = connection.execute(
            "SELECT width,direction FROM doors WHERE id=?", (door_id,)
        ).fetchone()
        saved = connection.execute(
            "SELECT handle_type,lock_source,cylinder_brand FROM door_hardware WHERE door_id=?",
            (door_id,),
        ).fetchone()
        frame = connection.execute(
            "SELECT value FROM door_custom_values WHERE door_id=? AND column_id=1",
            (door_id,),
        ).fetchone()
        connection.close()
        self.assertEqual(door, (95.0, "چپ"))
        self.assertEqual(saved, ("single_rosette", "own_brand", None))
        self.assertEqual(frame, ("سه طرفه",))
        self.assertTrue(loaded[0]["hardware_configured"])
        self.assertEqual(loaded[0]["handle_type"], "single_rosette")

    def test_batch_hardware_update_stays_inside_project(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "INSERT INTO doors(id,project_id,location,width,height,quantity,direction) VALUES(1,10,'الف',90,210,1,'راست')"
        )
        connection.execute(
            "INSERT INTO doors(id,project_id,location,width,height,quantity,direction) VALUES(2,20,'ب',90,210,1,'راست')"
        )
        connection.commit()
        connection.close()
        with mock.patch.object(database, "DB_NAME", str(self.db_path)):
            success, failed, _, _ = database.batch_update_doors_db(
                [1, 2], {}, {}, project_id=10,
                hardware_to_update=normalize_door_hardware(payload())
            )
        self.assertEqual((success, failed), (1, 1))
        connection = sqlite3.connect(self.db_path)
        saved_ids = connection.execute(
            "SELECT door_id FROM door_hardware ORDER BY door_id"
        ).fetchall()
        connection.close()
        self.assertEqual(saved_ids, [(1,)])

    def test_database_constraint_rejects_incomplete_two_piece_hardware(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "INSERT INTO doors(id,project_id,location,width,height,quantity,direction) VALUES(1,10,'الف',90,210,1,'راست')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO door_hardware(
                    door_id,hinge_brand,hinge_color,hinge_count,has_handle,
                    handle_type,handle_brand,handle_model,handle_color,
                    lock_source,lock_brand,lock_model
                ) VALUES(1,'کاله','مشکی',3,1,'two_piece','ایران','R210',
                         'مشکی','separate','داف','B45')
                """
            )
        connection.close()


class DoorHardwareUiContractTests(unittest.TestCase):
    def test_single_and_repeating_flow_is_present(self):
        template = (ROOT / "templates" / "project_details.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="hardware-details-step"', template)
        self.assertIn('id="repeat-hardware"', template)
        self.assertIn('id="stop-repeat"', template)
        self.assertIn("projectDoorHardwareRepeat", template)

    def test_batch_flow_requires_explicit_hardware_activation(self):
        template = (ROOT / "templates" / "batch_edit.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('name="update_hardware"', template)
        self.assertIn("تنظیمات کامل یراق", template)
        self.assertIn("همه درب‌های انتخاب‌شده جایگزین می‌شود", template)


if __name__ == "__main__":
    unittest.main()
