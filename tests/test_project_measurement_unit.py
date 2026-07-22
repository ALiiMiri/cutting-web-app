import importlib
import sqlite3
import unittest

import db_migrations  # Adds the migrations directory to the import path.


class ProjectMeasurementUnitMigrationTests(unittest.TestCase):
    def test_existing_projects_default_to_centimeters(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            """
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                customer_name TEXT,
                order_ref TEXT,
                date_shamsi TEXT,
                project_code TEXT
            );
            INSERT INTO projects(id,customer_name) VALUES (1,'پروژه قدیمی');
            """
        )

        migration = importlib.import_module("020_project_measurement_unit")
        migration.apply(conn)

        self.assertEqual(
            conn.execute("SELECT measurement_unit FROM projects WHERE id=1").fetchone()[0],
            "cm",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO projects(id,customer_name,measurement_unit) VALUES (2,'نامعتبر','meter')"
            )
        conn.close()


if __name__ == "__main__":
    unittest.main()
