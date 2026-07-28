import os
import sqlite3
import tempfile
import unittest

from flask import Blueprint, Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash

import auth_utils
from security_utils import access_denial_message
from routes.admin import admin_bp


class UserManagementTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(handle)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'staff',
                is_active INTEGER NOT NULL DEFAULT 1,
                must_change_password INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP,
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TIMESTAMP
            )
            """
        )
        from importlib import import_module
        import_module('migrations.021_user_management_security').apply(conn)
        for username, role in (
            ('sysadmin', 'admin'), ('manager1', 'manager'),
            ('staff1', 'staff'), ('factory1', 'factory'), ('viewer1', 'read_only'),
        ):
            conn.execute(
                "INSERT INTO users(username,password_hash,role) VALUES (?,?,?)",
                (username, generate_password_hash('Secure123'), role),
            )
        conn.commit()
        conn.close()

        self.original_db_name = auth_utils.DB_NAME
        auth_utils.DB_NAME = self.db_path
        self.app = Flask(__name__, template_folder='../templates')
        self.app.secret_key = 'test-only-secret'
        auth_stub = Blueprint('auth', __name__, url_prefix='/auth')

        @auth_stub.route('/logout')
        def logout():
            return 'logout'

        self.app.register_blueprint(auth_stub)
        self.app.register_blueprint(admin_bp)

        @self.app.route('/')
        def index():
            return 'home'

        login_manager = LoginManager(self.app)
        login_manager.user_loader(auth_utils.get_user_by_id)
        self.client = self.app.test_client()

    def tearDown(self):
        auth_utils.DB_NAME = self.original_db_name
        os.unlink(self.db_path)

    def _user_id(self, username):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                'SELECT id FROM users WHERE username=?', (username,)
            ).fetchone()[0]
        finally:
            conn.close()

    def _login(self, username):
        user = auth_utils.get_user_by_username(username)
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user['id'])
            session['_fresh'] = True
            session['csrf_token'] = 'valid-test-token'

    def _post(self, url, data=None):
        payload = {'csrf_token': 'valid-test-token'}
        payload.update(data or {})
        return self.client.post(url, data=payload)

    def test_manager_can_create_staff_but_not_manager(self):
        self._login('manager1')
        response = self._post('/admin/users/create', {
            'username': 'staff2', 'password': 'GoodPass123', 'role': 'staff',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(auth_utils.get_user_by_username('staff2'))

        response = self._post('/admin/users/create', {
            'username': 'manager2', 'password': 'GoodPass123', 'role': 'manager',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(auth_utils.get_user_by_username('manager2'))

    def test_manager_cannot_change_system_admin(self):
        self._login('manager1')
        admin_id = self._user_id('sysadmin')
        response = self._post(
            f'/admin/users/{admin_id}/toggle_active'
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(auth_utils.get_user_by_id(admin_id).is_active)

    def test_last_active_system_admin_is_protected(self):
        self._login('sysadmin')
        admin_id = self._user_id('sysadmin')
        response = self._post(
            f'/admin/users/{admin_id}/toggle_active'
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(auth_utils.get_user_by_id(admin_id).is_active)

    def test_password_reset_invalidates_old_sessions_and_is_audited(self):
        self._login('manager1')
        staff_id = self._user_id('staff1')
        before = auth_utils.get_user_by_id(staff_id).session_version
        response = self._post(
            f'/admin/users/{staff_id}/reset_password',
            {'new_password': 'Changed123'},
        )
        self.assertEqual(response.status_code, 200)
        updated = auth_utils.get_user_by_id(staff_id)
        self.assertEqual(updated.session_version, before + 1)
        self.assertTrue(updated.must_change_password)
        self.assertEqual(auth_utils.get_user_activity_logs()[0]['action'], 'reset_password')

    def test_management_posts_reject_missing_security_token(self):
        self._login('manager1')
        response = self.client.post('/admin/users/create', data={
            'username': 'unsafe', 'password': 'GoodPass123', 'role': 'staff',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(auth_utils.get_user_by_username('unsafe'))

    def test_weak_passwords_are_rejected(self):
        self.assertIsNotNone(auth_utils.validate_password_strength('12345678', 'user'))
        self.assertIsNotNone(auth_utils.validate_password_strength('onlyletters', 'user'))
        self.assertIsNone(auth_utils.validate_password_strength('SafePass123', 'user'))

    def test_read_only_cannot_change_any_data(self):
        self.assertIsNotNone(access_denial_message('read_only', 'POST', 'save_quote'))
        self.assertIsNotNone(access_denial_message('read_only', 'DELETE', 'anything'))
        self.assertIsNone(access_denial_message('read_only', 'GET', 'index'))
        self.assertIsNone(
            access_denial_message(
                'read_only', 'POST', 'save_orders_view_preference'
            )
        )

    def test_staff_cannot_open_manager_settings(self):
        self.assertIsNotNone(
            access_denial_message('staff', 'GET', 'price_calculator_settings')
        )
        self.assertIsNone(
            access_denial_message('manager', 'GET', 'price_calculator_settings')
        )

    def test_staff_and_read_only_cannot_open_inventory(self):
        for role in ('staff', 'factory', 'read_only'):
            self.assertIsNotNone(
                access_denial_message(role, 'GET', 'inventory.dashboard', '/inventory')
            )
            self.assertIsNotNone(
                access_denial_message(role, 'GET', 'inventory.logs', '/inventory/logs')
            )
        self.assertIsNone(
            access_denial_message('manager', 'GET', 'inventory.dashboard', '/inventory')
        )

    def test_staff_may_apply_cutting_for_an_owned_project(self):
        self.assertIsNone(
            access_denial_message(
                'staff', 'POST', 'apply_cutting_plan',
                '/project/17/apply_cutting_plan',
            )
        )


if __name__ == '__main__':
    unittest.main()
