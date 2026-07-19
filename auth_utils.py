# Authentication utilities and User model
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import sqlite3
from config import Config
import jdatetime
from date_utils import get_shamsi_datetime_iso, get_shamsi_now

DB_NAME = Config.DB_NAME

VALID_ROLES = ('admin', 'manager', 'staff', 'read_only')
ROLE_LABELS = {
    'admin': 'مدیر سیستم',
    'manager': 'مدیر',
    'staff': 'کارمند',
    'read_only': 'فقط مشاهده',
}
VALID_ORDERS_VIEW_PREFERENCES = ('table', 'cards')


def _connect(row_factory=False):
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def get_orders_view_preference(user_id):
    """Return a safe dashboard layout preference for one user."""
    conn = None
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT orders_view_preference FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row and row[0] in VALID_ORDERS_VIEW_PREFERENCES:
            return row[0]
    except sqlite3.Error as exc:
        print(f"Error loading orders view preference: {exc}")
    finally:
        if conn:
            conn.close()
    return 'table'


def set_orders_view_preference(user_id, preference):
    """Persist a validated dashboard layout preference for one user."""
    if preference not in VALID_ORDERS_VIEW_PREFERENCES:
        return False
    conn = None
    try:
        conn = _connect()
        cursor = conn.execute(
            "UPDATE users SET orders_view_preference = ? WHERE id = ?",
            (preference, user_id),
        )
        conn.commit()
        return cursor.rowcount == 1
    except sqlite3.Error as exc:
        print(f"Error saving orders view preference: {exc}")
        return False
    finally:
        if conn:
            conn.close()


class User(UserMixin):
    """User model for Flask-Login"""
    
    def __init__(self, id, username, role, is_active, must_change_password=False,
                 session_version=0):
        self.id = id
        self.username = username
        self.role = role
        self._is_active = bool(is_active)
        self.must_change_password = bool(must_change_password)
        self.session_version = int(session_version or 0)
    
    def get_id(self):
        return str(self.id)
    
    @property
    def is_active(self):
        """Override UserMixin's is_active to use our database value"""
        return self._is_active
    
    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_manager(self):
        return self.role == 'manager'
    
    @property
    def is_staff(self):
        return self.role == 'staff'
    
    @property
    def is_read_only(self):
        return self.role == 'read_only'


def get_user_by_id(user_id):
    """Load user by ID for Flask-Login"""
    conn = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, role, is_active, must_change_password, session_version FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return User(
                id=row[0],
                username=row[1],
                role=row[2],
                is_active=row[3],
                must_change_password=row[4],
                session_version=row[5],
            )
    except sqlite3.Error as e:
        print(f"Error loading user: {e}")
    finally:
        if conn:
            conn.close()
    return None


def get_user_by_username(username):
    """Get user by username"""
    conn = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password_hash, role, is_active, must_change_password, failed_login_attempts, locked_until, session_version FROM users WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'username': row[1],
                'password_hash': row[2],
                'role': row[3],
                'is_active': row[4],
                'must_change_password': row[5],
                'failed_login_attempts': row[6],
                'locked_until': row[7],
                'session_version': row[8],
            }
    except sqlite3.Error as e:
        print(f"Error getting user: {e}")
    finally:
        if conn:
            conn.close()
    return None


def verify_password(user_data, password):
    """Verify password against hash"""
    return check_password_hash(user_data['password_hash'], password)


def validate_password_strength(password, username=''):
    """Return a simple Persian validation message, or None for an acceptable password."""
    if len(password or '') < 8:
        return 'رمز عبور باید حداقل ۸ کاراکتر باشد.'
    lowered = password.casefold()
    if username and lowered == username.casefold():
        return 'رمز عبور نباید با نام کاربری یکسان باشد.'
    if lowered in {'12345678', 'password', 'admin123', 'qwerty123', '11111111'}:
        return 'این رمز عبور بسیار ساده است. لطفاً رمز دیگری انتخاب کنید.'
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        return 'رمز عبور باید هم حرف و هم عدد داشته باشد.'
    return None


def check_account_locked(user_data):
    """Check if account is locked"""
    if user_data.get('locked_until'):
        try:
            # تبدیل تاریخ شمسی ذخیره شده به datetime برای مقایسه
            locked_until_str = user_data['locked_until']
            # تلاش برای parse کردن تاریخ شمسی
            locked_until_shamsi = jdatetime.datetime.strptime(locked_until_str, '%Y-%m-%d %H:%M:%S')
            locked_until = locked_until_shamsi.togregorian()
            
            # مقایسه با زمان فعلی
            now_shamsi = jdatetime.datetime.now()
            now = now_shamsi.togregorian()
            
            if now < locked_until:
                return True, locked_until_shamsi
        except (ValueError, TypeError):
            pass
    return False, None


def record_failed_login(username):
    """Record failed login attempt"""
    conn = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        
        # Increment failed attempts
        cursor.execute(
            "UPDATE users SET failed_login_attempts = failed_login_attempts + 1 WHERE username = ?",
            (username,)
        )
        
        # Check if should lock (after 5 failed attempts)
        cursor.execute("SELECT failed_login_attempts FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        
        if row and row[0] >= 5:
            # Lock for 15 minutes - استفاده از تاریخ شمسی
            now_shamsi = jdatetime.datetime.now()
            now_gregorian = now_shamsi.togregorian()
            locked_until_gregorian = now_gregorian + timedelta(minutes=15)
            locked_until_shamsi = jdatetime.datetime.fromgregorian(datetime=locked_until_gregorian)
            
            cursor.execute(
                "UPDATE users SET locked_until = ? WHERE username = ?",
                (locked_until_shamsi.strftime('%Y-%m-%d %H:%M:%S'), username)
            )
        
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error recording failed login: {e}")
    finally:
        if conn:
            conn.close()


def record_successful_login(user_id):
    """Record successful login and reset failed attempts"""
    conn = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        # استفاده از تاریخ شمسی برای last_login_at
        login_time = get_shamsi_datetime_iso()
        cursor.execute(
            """
            UPDATE users 
            SET last_login_at = ?, 
                failed_login_attempts = 0,
                locked_until = NULL
            WHERE id = ?
            """,
            (login_time, user_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error recording login: {e}")
    finally:
        if conn:
            conn.close()


def change_user_password(user_id, new_password, clear_must_change=True):
    """Change user password"""
    conn = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        
        password_hash = generate_password_hash(new_password)
        
        if clear_must_change:
            cursor.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0, session_version = session_version + 1 WHERE id = ?",
                (password_hash, user_id)
            )
        else:
            cursor.execute(
                "UPDATE users SET password_hash = ?, session_version = session_version + 1 WHERE id = ?",
                (password_hash, user_id)
            )
        
        changed = cursor.rowcount == 1
        conn.commit()
        return changed
    except sqlite3.Error as e:
        print(f"Error changing password: {e}")
        return False
    finally:
        if conn:
            conn.close()


def create_user(username, password, role='staff', must_change_password=True):
    """Create a new user (for admin use)"""
    conn = None
    try:
        if role not in VALID_ROLES:
            return False, "نقش انتخاب‌شده معتبر نیست"
        conn = _connect()
        cursor = conn.cursor()
        
        password_hash = generate_password_hash(password)
        
        cursor.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active, must_change_password)
            VALUES (?, ?, ?, 1, ?)
            """,
            (username, password_hash, role, 1 if must_change_password else 0)
        )
        
        user_id = cursor.lastrowid
        conn.commit()
        return True, user_id
    except sqlite3.IntegrityError:
        return False, "نام کاربری تکراری است"
    except sqlite3.Error as e:
        print(f"Error creating user: {e}")
        return False, str(e)
    finally:
        if conn:
            conn.close()


def get_all_users():
    """Get all users (for admin panel)"""
    conn = None
    users = []
    try:
        conn = _connect(row_factory=True)
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT id, username, role, is_active, must_change_password, 
                   created_at, last_login_at, failed_login_attempts, locked_until
            FROM users
            ORDER BY created_at DESC
            """
        )
        
        users = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"Error getting users: {e}")
    finally:
        if conn:
            conn.close()
    return users


def update_user_role(user_id, new_role):
    """Update user role (admin only)"""
    conn = None
    try:
        if new_role not in VALID_ROLES:
            return False
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET role = ?, session_version = session_version + 1 WHERE id = ?",
            (new_role, user_id),
        )
        changed = cursor.rowcount == 1
        conn.commit()
        return changed
    except sqlite3.Error as e:
        print(f"Error updating role: {e}")
        return False
    finally:
        if conn:
            conn.close()


def toggle_user_active(user_id):
    """Toggle user active status (admin only)"""
    conn = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_active = NOT is_active, session_version = session_version + 1 WHERE id = ?",
            (user_id,),
        )
        changed = cursor.rowcount == 1
        conn.commit()
        return changed
    except sqlite3.Error as e:
        print(f"Error toggling user: {e}")
        return False
    finally:
        if conn:
            conn.close()


def reset_user_password(user_id, new_password):
    """Reset user password (admin only) and force change on next login"""
    conn = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        
        password_hash = generate_password_hash(new_password)
        cursor.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 1, session_version = session_version + 1 WHERE id = ?",
            (password_hash, user_id)
        )
        
        changed = cursor.rowcount == 1
        conn.commit()
        return changed
    except sqlite3.Error as e:
        print(f"Error resetting password: {e}")
        return False
    finally:
        if conn:
            conn.close()


def delete_user(user_id):
    """Delete a user from the database (admin only)"""
    conn = None
    try:
        conn = _connect()
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            return False, "کاربر یافت نشد"
        
        # Delete the user
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return True, "کاربر با موفقیت حذف شد"
    except sqlite3.Error as e:
        print(f"Error deleting user: {e}")
        return False, str(e)
    finally:
        if conn:
            conn.close()


def count_active_admins():
    conn = None
    try:
        conn = _connect()
        return conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1"
        ).fetchone()[0]
    finally:
        if conn:
            conn.close()


def record_user_activity(actor_user_id, action, target_user_id=None, details=None):
    """Keep a short, immutable history of sensitive user-management actions."""
    conn = None
    try:
        conn = _connect()
        detail_text = json.dumps(details or {}, ensure_ascii=False, separators=(',', ':'))
        conn.execute(
            """
            INSERT INTO user_activity_logs(actor_user_id, target_user_id, action, details, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor_user_id, target_user_id, action, detail_text, get_shamsi_datetime_iso()),
        )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        print(f"Error recording user activity: {exc}")
        return False
    finally:
        if conn:
            conn.close()


def get_user_activity_logs(limit=50):
    conn = None
    try:
        conn = _connect(row_factory=True)
        rows = conn.execute(
            """
            SELECT l.id, l.action, l.details, l.created_at,
                   COALESCE(actor.username, 'کاربر حذف‌شده') AS actor_username,
                   COALESCE(target.username, 'کاربر حذف‌شده') AS target_username
            FROM user_activity_logs AS l
            LEFT JOIN users AS actor ON actor.id = l.actor_user_id
            LEFT JOIN users AS target ON target.id = l.target_user_id
            ORDER BY l.id DESC LIMIT ?
            """,
            (max(1, min(int(limit), 200)),),
        ).fetchall()
        logs = []
        for row in rows:
            item = dict(row)
            try:
                item['details_data'] = json.loads(item.get('details') or '{}')
            except (TypeError, json.JSONDecodeError):
                item['details_data'] = {}
            if item['target_username'] == 'کاربر حذف‌شده':
                item['target_username'] = item['details_data'].get('username', 'کاربر حذف‌شده')
            logs.append(item)
        return logs
    except sqlite3.Error as exc:
        print(f"Error loading user activity: {exc}")
        return []
    finally:
        if conn:
            conn.close()
