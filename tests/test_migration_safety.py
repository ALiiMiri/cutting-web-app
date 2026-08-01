import os
import sqlite3
import tempfile
import unittest

from db_migrations import PendingMigrationError, apply_migrations


class MigrationSafetyTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)

    def tearDown(self):
        os.unlink(self.db_path)

    def test_normal_startup_refuses_pending_migrations(self):
        conn = sqlite3.connect(self.db_path)
        with self.assertRaises(PendingMigrationError):
            apply_migrations(conn, allow_changes=False)
        conn.close()

    def test_guarded_upgrade_is_complete_and_idempotent(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        apply_migrations(conn, allow_changes=True)
        first_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        checksummed = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE checksum IS NOT NULL AND applied_at IS NOT NULL"
        ).fetchone()[0]
        self.assertEqual(checksummed, first_count)
        apply_migrations(conn, allow_changes=False)
        second_count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        self.assertEqual(second_count, first_count)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertIsNotNone(
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='door_hardware'"
            ).fetchone()
        )
        self.assertIsNotNone(
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='hardware_catalog_options'"
            ).fetchone()
        )
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        self.assertTrue(
            {
                "idx_projects_active_id",
                "idx_projects_active_assignee_id",
                "idx_projects_active_customer_id",
                "idx_projects_active_order_ref_id",
                "idx_projects_active_date_id",
                "idx_projects_project_code",
                "idx_doors_project_id",
            }.issubset(indexes)
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
