import importlib
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import database
from door_hardware import HARDWARE_CATALOG_CATEGORIES


ROOT = pathlib.Path(__file__).resolve().parents[1]


class HardwareCatalogDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.directory.name) / "catalog.db"
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
            CREATE TABLE projects(id INTEGER PRIMARY KEY);
            CREATE TABLE doors(
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id)
            );
            INSERT INTO projects(id) VALUES(1);
            INSERT INTO doors(id,project_id) VALUES(1,1);
            """
        )
        importlib.import_module("migrations.027_door_hardware").apply(connection)
        connection.execute(
            """
            INSERT INTO door_hardware(
                door_id,hinge_brand,hinge_color,hinge_count,has_handle,
                handle_type,handle_brand,handle_model,handle_color,
                lock_source,lock_brand,lock_model,cylinder_brand,cylinder_model
            ) VALUES(1,'کاله','مشکی',3,1,'two_piece','ایران','R210',
                     'مشکی مات','separate','داف','B45','یال','70')
            """
        )
        importlib.import_module("migrations.028_hardware_catalog_options").apply(
            connection
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.directory.cleanup()

    def test_migration_seeds_existing_hardware_values(self):
        with mock.patch.object(database, "DB_NAME", str(self.db_path)):
            options = database.get_hardware_catalog_options()

        self.assertEqual(set(options), set(HARDWARE_CATALOG_CATEGORIES))
        self.assertEqual(options["hinge_brand"][0]["value"], "کاله")
        self.assertEqual(options["lock_model"][0]["value"], "B45")

    def test_add_archive_reactivate_and_duplicate_rules(self):
        with mock.patch.object(database, "DB_NAME", str(self.db_path)):
            added, _ = database.add_hardware_catalog_option(
                "hinge_brand", " هافله "
            )
            duplicate, duplicate_message = database.add_hardware_catalog_option(
                "hinge_brand", "هافله"
            )
            option_id = next(
                item["id"]
                for item in database.get_hardware_catalog_options()["hinge_brand"]
                if item["value"] == "هافله"
            )
            archived = database.archive_hardware_catalog_option(option_id)
            active_values = [
                item["value"]
                for item in database.get_hardware_catalog_options()["hinge_brand"]
            ]
            reactivated, _ = database.add_hardware_catalog_option(
                "hinge_brand", "هافله"
            )

        self.assertTrue(added)
        self.assertFalse(duplicate)
        self.assertIn("از قبل", duplicate_message)
        self.assertTrue(archived)
        self.assertNotIn("هافله", active_values)
        self.assertTrue(reactivated)

    def test_move_changes_only_category_order(self):
        with mock.patch.object(database, "DB_NAME", str(self.db_path)):
            database.add_hardware_catalog_option("handle_color", "طلایی")
            database.add_hardware_catalog_option("handle_color", "نقره‌ای")
            before = database.get_hardware_catalog_options()["handle_color"]
            moved = database.move_hardware_catalog_option(before[2]["id"], "up")
            after = database.get_hardware_catalog_options()["handle_color"]

        self.assertTrue(moved)
        self.assertEqual(
            [item["value"] for item in after],
            ["مشکی مات", "نقره‌ای", "طلایی"],
        )

    def test_unknown_category_is_rejected(self):
        with mock.patch.object(database, "DB_NAME", str(self.db_path)):
            success, _ = database.add_hardware_catalog_option("other", "ناشناخته")
        self.assertFalse(success)


class HardwareCatalogUiContractTests(unittest.TestCase):
    def test_settings_page_supports_add_remove_and_order(self):
        template = (ROOT / "templates" / "hardware_catalog_settings.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("hardware_catalog_add", template)
        self.assertIn("hardware_catalog_archive", template)
        self.assertIn("hardware_catalog_move", template)
        self.assertIn("سفارش‌های قبلی را تغییر نمی‌دهد", template)

    def test_single_and_batch_forms_use_managed_dropdowns(self):
        project = (ROOT / "templates" / "project_details.html").read_text(
            encoding="utf-8"
        )
        batch = (ROOT / "templates" / "batch_edit.html").read_text(
            encoding="utf-8"
        )
        for category in HARDWARE_CATALOG_CATEGORIES:
            self.assertIn(f"hardware_options.{category}", project)
            self.assertIn(f"hardware_options.{category}", batch)
        self.assertIn("hardware_catalog_settings", project)
        self.assertIn("hardware_catalog_settings", batch)

    def test_main_navigation_links_to_hardware_settings(self):
        header = (ROOT / "templates" / "_app_header.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("تنظیمات یراق", header)
        self.assertIn("hardware_catalog_settings", header)


if __name__ == "__main__":
    unittest.main()
