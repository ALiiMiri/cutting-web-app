import importlib
import os
import sqlite3
import tempfile
import unittest

import database


class ProjectOwnershipTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(handle)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                order_ref TEXT NOT NULL,
                date_shamsi TEXT DEFAULT '',
                project_code TEXT,
                measurement_unit TEXT DEFAULT 'cm'
            );
            """
        )
        conn.executemany(
            "INSERT INTO users(id,username,role,is_active) VALUES (?,?,?,1)",
            [(1, 'admin', 'admin'), (2, 'manager1', 'manager'),
             (4, 'paniz', 'staff'), (5, 'other_staff', 'staff')],
        )
        conn.executemany(
            "INSERT INTO projects(id,customer_name,order_ref) VALUES (?,?,?)",
            [(16, 'قدیمی', '16'), (17, 'الف', '17'),
             (18, 'ب', '18'), (19, 'پ', '19')],
        )
        importlib.import_module('migrations.022_project_ownership').apply(conn)
        conn.commit()
        conn.close()
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        os.unlink(self.db_path)

    def test_only_requested_projects_are_seeded_for_paniz(self):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT id,created_by_user_id,assigned_to_user_id FROM projects ORDER BY id"
        ).fetchall()
        conn.close()
        self.assertEqual(rows[0], (16, None, None))
        self.assertEqual(rows[1:], [(17, 4, 4), (18, 4, 4), (19, 4, 4)])

    def test_staff_can_edit_only_assigned_projects(self):
        self.assertTrue(database.user_can_edit_project(4, 'staff', 17))
        self.assertFalse(database.user_can_edit_project(5, 'staff', 17))
        self.assertFalse(database.user_can_edit_project(4, 'staff', 16))
        self.assertTrue(database.user_can_edit_project(2, 'manager', 16))
        self.assertTrue(database.user_can_edit_project(1, 'admin', 16))

    def test_new_project_is_owned_by_its_creator(self):
        project_id = database.add_project_db(
            'جدید', '20', '1405/04/24', '20', created_by_user_id=5
        )
        project = database.get_project_details_db(project_id)
        self.assertEqual(project['created_by_user_id'], 5)
        self.assertEqual(project['assigned_to_user_id'], 5)
        self.assertTrue(database.user_can_edit_project(5, 'staff', project_id))

    def test_manager_can_reassign_and_history_is_recorded(self):
        success, _ = database.assign_project_user(17, 5, 2)
        self.assertTrue(success)
        self.assertFalse(database.user_can_edit_project(4, 'staff', 17))
        self.assertTrue(database.user_can_edit_project(5, 'staff', 17))
        latest = database.get_project_assignment_logs(17)[0]
        self.assertEqual(latest['actor_username'], 'manager1')
        self.assertEqual(latest['previous_username'], 'paniz')
        self.assertEqual(latest['new_username'], 'other_staff')


if __name__ == '__main__':
    unittest.main()
