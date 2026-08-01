import importlib
import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import database
from factory_requirements import (
    FactoryRequirementError,
    calculate_factory_requirements,
    default_profile_bracket_label,
    normalize_bracket_mode,
    rubber_meters_per_door,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]


def door(**overrides):
    data = {
        "id": 1,
        "location": "اتاق مدیریت",
        "width": 100,
        "height": 270,
        "quantity": 1,
        "kolaft": "سه طرفه",
        "noe_profile": "فریم لس قالب جدید",
        "installation_bracket_mode": "profile",
    }
    data.update(overrides)
    return data


class FactoryRequirementCalculationTests(unittest.TestCase):
    def test_profile_brackets_are_separated_and_meaty_is_a_replacement(self):
        report = calculate_factory_requirements(
            [
                door(id=1, quantity=2),
                door(
                    id=2,
                    location="اتاق دو",
                    height=180,
                    quantity=1,
                    noe_profile="توچوب دار",
                ),
                door(
                    id=3,
                    location="اتاق سه",
                    height=61,
                    quantity=1,
                    installation_bracket_mode="meaty",
                ),
            ]
        )
        totals = {
            item["label"]: item["quantity"]
            for item in report["bracket_summary"]
        }
        self.assertEqual(totals["براکت نصب پروفیل جدید فریم‌لس"], 20)
        self.assertEqual(totals["براکت نصب پروفیل توچوب‌دار"], 6)
        self.assertEqual(totals["براکت گوشتی"], 4)
        self.assertEqual(report["total_bracket_count"], 30)
        self.assertNotIn("براکت نصب پروفیل جدید فریم‌لس", {
            report["details"][2]["bracket_label"]
        })

    def test_explicit_profile_label_overrides_the_default(self):
        report = calculate_factory_requirements(
            [door()], {"فریم لس قالب جدید": "براکت مخصوص خط یک"}
        )
        self.assertEqual(
            report["bracket_summary"],
            [{"label": "براکت مخصوص خط یک", "quantity": 10}],
        )

    def test_rubber_respects_two_and_three_sided_frames(self):
        self.assertEqual(rubber_meters_per_door(100, 200, "سه طرفه"), 5)
        self.assertEqual(rubber_meters_per_door(100, 200, "دو طرفه"), 4)
        report = calculate_factory_requirements(
            [door(width=100, height=200, quantity=2, kolaft="دو طرفه")]
        )
        self.assertEqual(report["total_rubber_meters"], 8)

    def test_missing_profile_warns_but_meaty_does_not_need_profile(self):
        automatic = calculate_factory_requirements([door(noe_profile="")])
        self.assertEqual(automatic["total_bracket_count"], 0)
        self.assertEqual(len(automatic["warnings"]), 1)

        meaty = calculate_factory_requirements(
            [door(noe_profile="", installation_bracket_mode="meaty")]
        )
        self.assertEqual(meaty["warnings"], [])
        self.assertEqual(meaty["total_bracket_count"], 10)

    def test_default_names_and_mode_validation(self):
        self.assertEqual(
            default_profile_bracket_label("فریم_لس_قالب_جدید"),
            "براکت نصب پروفیل جدید فریم‌لس",
        )
        self.assertEqual(normalize_bracket_mode(None), "profile")
        with self.assertRaises(FactoryRequirementError):
            normalize_bracket_mode("both")


class FactoryRequirementDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = pathlib.Path(self.directory.name) / "factory.db"
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE doors(id INTEGER PRIMARY KEY);
            CREATE TABLE profile_types(
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            );
            INSERT INTO doors(id) VALUES(1);
            INSERT INTO profile_types(id,name) VALUES(10,'فریم لس قالب جدید');
            """
        )
        importlib.import_module(
            "migrations.029_factory_installation_requirements"
        ).apply(connection)
        connection.commit()
        connection.close()

    def tearDown(self):
        self.directory.cleanup()

    def test_migration_defaults_old_doors_to_profile_mode(self):
        connection = sqlite3.connect(self.db_path)
        mode = connection.execute(
            "SELECT installation_bracket_mode FROM doors WHERE id=1"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(mode, "profile")

    def test_profile_bracket_title_can_be_managed(self):
        with mock.patch.object(database, "DB_NAME", str(self.db_path)):
            initial = database.get_profile_bracket_settings()
            updated = database.update_profile_bracket_setting(
                10, "براکت خط تولید جدید"
            )
            current = database.get_profile_bracket_settings()
        self.assertEqual(
            initial[0]["bracket_name"], "براکت نصب پروفیل جدید فریم‌لس"
        )
        self.assertTrue(updated)
        self.assertEqual(current[0]["bracket_name"], "براکت خط تولید جدید")


class FactoryRequirementUiContractTests(unittest.TestCase):
    def test_factory_report_and_entry_points_are_present(self):
        report = (ROOT / "templates" / "factory_requirements.html").read_text(
            encoding="utf-8"
        )
        tree = (ROOT / "templates" / "project_treeview.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("متراژ کل لاستیک", report)
        self.assertIn("تفکیک براکت‌های نصب", report)
        self.assertIn("factory_requirements_report", tree)

    def test_single_repeat_and_batch_bracket_controls_are_present(self):
        project = (ROOT / "templates" / "project_details.html").read_text(
            encoding="utf-8"
        )
        batch = (ROOT / "templates" / "batch_edit.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="meaty-bracket"', project)
        self.assertIn("bracket_mode", project)
        self.assertIn('name="update_bracket_mode"', batch)
        self.assertIn('value="meaty"', batch)


if __name__ == "__main__":
    unittest.main()
