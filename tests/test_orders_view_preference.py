import importlib
import os
import sqlite3
import tempfile
import unittest

import auth_utils
import database


class OrdersViewPreferenceTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
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
                id INTEGER PRIMARY KEY,
                customer_name TEXT NOT NULL,
                order_ref TEXT NOT NULL,
                date_shamsi TEXT,
                project_code TEXT,
                assigned_to_user_id INTEGER,
                created_by_user_id INTEGER
            );
            INSERT INTO users(id,username,role) VALUES (1,'one','staff'),(2,'two','staff');
            INSERT INTO projects VALUES
                (1,'الف','100','1405/04/01','100',1,1),
                (2,'ب','200','1405/04/02','200',2,1),
                (3,'پ','300','1405/04/03','300',NULL,1);
            """
        )
        importlib.import_module("023_user_orders_view_preference").apply(conn)
        conn.commit()
        conn.close()
        self.original_auth_db = auth_utils.DB_NAME
        self.original_database_db = database.DB_NAME
        auth_utils.DB_NAME = self.db_path
        database.DB_NAME = self.db_path

    def tearDown(self):
        auth_utils.DB_NAME = self.original_auth_db
        database.DB_NAME = self.original_database_db
        os.unlink(self.db_path)

    def test_preference_is_personal_and_validated(self):
        self.assertEqual(auth_utils.get_orders_view_preference(1), "table")
        self.assertTrue(auth_utils.set_orders_view_preference(1, "cards"))
        self.assertEqual(auth_utils.get_orders_view_preference(1), "cards")
        self.assertEqual(auth_utils.get_orders_view_preference(2), "table")
        self.assertFalse(auth_utils.set_orders_view_preference(1, "tiles"))

    def test_database_constraint_rejects_unknown_view(self):
        conn = sqlite3.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE users SET orders_view_preference='tiles' WHERE id=1"
                )
        finally:
            conn.close()

    def test_dashboard_scopes_use_real_assignments(self):
        mine = database.get_projects_paginated(
            scope="mine", current_user_id=1, per_page=15
        )
        unassigned = database.get_projects_paginated(
            scope="unassigned", current_user_id=1, per_page=15
        )
        self.assertEqual([project["id"] for project in mine["projects"]], [1])
        self.assertEqual([project["id"] for project in unassigned["projects"]], [3])
        self.assertEqual(
            database.get_project_dashboard_counts(1),
            {"total": 3, "mine": 1, "unassigned": 1},
        )


if __name__ == "__main__":
    unittest.main()
