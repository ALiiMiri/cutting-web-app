import pathlib
import sqlite3
import tempfile
import unittest
from unittest import mock

import database


ROOT = pathlib.Path(__file__).resolve().parents[1]


class BatchEditSafetyTests(unittest.TestCase):
    def test_database_update_is_scoped_to_project(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = pathlib.Path(directory) / "batch.db"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE doors(
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    location TEXT,
                    width REAL,
                    height REAL,
                    quantity INTEGER,
                    direction TEXT
                );
                CREATE TABLE custom_columns(
                    id INTEGER PRIMARY KEY,
                    column_name TEXT UNIQUE,
                    display_name TEXT
                );
                CREATE TABLE door_custom_values(
                    door_id INTEGER,
                    column_id INTEGER,
                    value TEXT
                );
                INSERT INTO doors VALUES(1,10,'درب اول',100,200,1,'راست');
                INSERT INTO doors VALUES(2,20,'درب سفارش دیگر',100,200,1,'راست');
                INSERT INTO custom_columns VALUES(1,'rang','رنگ پروفیل');
                """
            )
            connection.commit()
            connection.close()

            with mock.patch.object(database, "DB_NAME", str(db_path)):
                success, failed, _, _ = database.batch_update_doors_db(
                    [1, 2], {}, {"rang": "سفید"}, project_id=10
                )

            self.assertEqual((success, failed), (1, 1))
            connection = sqlite3.connect(db_path)
            values = connection.execute(
                "SELECT door_id,value FROM door_custom_values ORDER BY door_id"
            ).fetchall()
            connection.close()
            self.assertEqual(values, [(1, "سفید")])

    def test_template_requires_explicit_mixed_value_acknowledgement(self):
        template = (ROOT / "templates" / "batch_edit.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="mixed-warning"', template)
        self.assertIn('id="acknowledge-check"', template)
        self.assertIn('name="acknowledge_mixed"', template)
        self.assertIn("مقادیر متفاوت قبلی از بین می‌روند", template)
        self.assertNotIn("انتخاب همه", template)

    def test_routes_validate_scope_and_csrf(self):
        source = (ROOT / "cutting_web_app.py").read_text(encoding="utf-8")
        self.assertIn("def _load_project_batch_doors", source)
        self.assertIn("project_id=project_id", source)
        self.assertIn('@csrf_protected\n@staff_or_admin_required\ndef apply_batch_edit', source)


if __name__ == "__main__":
    unittest.main()
