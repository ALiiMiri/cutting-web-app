import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import backup_manager


class BackupListingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.backup_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def _empty_database(self, filename):
        path = os.path.join(self.backup_dir, filename)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        return path

    def test_backup_without_metadata_has_display_datetime(self):
        self._empty_database("backup_14050423_124143_f216bdcf.db")

        with mock.patch.object(backup_manager, "BACKUP_DIR", self.backup_dir):
            backups = backup_manager.list_backups()

        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0]["datetime"])
        self.assertEqual(backups[0]["reason"], "نامشخص")

    def test_create_backup_writes_metadata_next_to_unique_database_name(self):
        source_path = self._empty_database("source.db")

        with (
            mock.patch.object(backup_manager, "BACKUP_DIR", self.backup_dir),
            mock.patch.object(backup_manager.Config, "DB_NAME", source_path),
        ):
            success, backup_path = backup_manager.create_backup(reason="test")

        self.assertTrue(success)
        metadata_path = os.path.splitext(backup_path)[0] + ".json"
        self.assertTrue(os.path.exists(metadata_path))
        with open(metadata_path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["reason"], "test")


if __name__ == "__main__":
    unittest.main()
