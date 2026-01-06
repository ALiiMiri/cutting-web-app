import os
import sqlite3
import json
import shutil
import sys
import io
from datetime import datetime, timedelta
from config import Config
from date_utils import get_shamsi_timestamp, get_shamsi_datetime_str, shamsi_datetime_from_timestamp, add_days_shamsi
from werkzeug.security import generate_password_hash

# Fix encoding for Windows console (only if not already wrapped)
if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer') and not isinstance(sys.stdout, io.TextIOWrapper):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

# مسیر پوشه بکاپ‌ها
BACKUP_DIR = "backups"

def ensure_backup_directory():
    """ایجاد پوشه بکاپ در صورت عدم وجود"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"پوشه بکاپ ایجاد شد: {BACKUP_DIR}")

def create_backup(reason="manual", user="admin", metadata=None):
    """
    ایجاد بکاپ امن از دیتابیس با استفاده از SQLite backup API
    
    Args:
        reason: دلیل ایجاد بکاپ (مثل "before_delete_project")
        user: کاربری که بکاپ را درخواست کرده
        metadata: اطلاعات اضافی (dict)
    
    Returns:
        tuple: (success, backup_path_or_error_message)
    """
    ensure_backup_directory()
    
    db_path = Config.DB_NAME
    
    # بررسی وجود فایل دیتابیس اصلی
    if not os.path.exists(db_path):
        return False, "فایل دیتابیس یافت نشد."
    
    try:
        # ایجاد نام فایل بکاپ با تاریخ و زمان شمسی
        timestamp = get_shamsi_timestamp()
        backup_filename = f"backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # استفاده از SQLite Backup API برای بکاپ امن
        # این روش حتی اگر دیتابیس در حال استفاده باشد هم کار می‌کند
        source_conn = sqlite3.connect(db_path)
        backup_conn = sqlite3.connect(backup_path)
        
        # کپی امن دیتابیس
        with backup_conn:
            source_conn.backup(backup_conn)
        
        source_conn.close()
        backup_conn.close()
        
        # بررسی سلامت فایل بکاپ
        verify_result = verify_backup(backup_path)
        if not verify_result["valid"]:
            os.remove(backup_path)
            return False, f"بکاپ معتبر نیست: {verify_result['error']}"
        
        # ایجاد فایل متادیتا (اطلاعات بکاپ)
        metadata_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")
        backup_info = {
            "timestamp": timestamp,
            "datetime": get_shamsi_datetime_str(),  # تاریخ شمسی
            "reason": reason,
            "user": user,
            "db_size_bytes": os.path.getsize(backup_path),
            "original_db": db_path,
            "table_counts": verify_result.get("table_counts", {}),
            "metadata": metadata or {}
        }
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(backup_info, f, ensure_ascii=False, indent=2)
        
        print(f"✓ بکاپ با موفقیت ایجاد شد: {backup_path}")
        return True, backup_path
        
    except Exception as e:
        error_msg = f"خطا در ایجاد بکاپ: {str(e)}"
        print(f"!!! {error_msg}")
        return False, error_msg

def verify_backup(backup_path):
    """
    بررسی سلامت فایل بکاپ
    
    Returns:
        dict: {"valid": bool, "error": str, "table_counts": dict}
    """
    try:
        conn = sqlite3.connect(backup_path)
        cursor = conn.cursor()
        
        # بررسی یکپارچگی دیتابیس
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchone()[0]
        
        if integrity_result != "ok":
            conn.close()
            return {"valid": False, "error": f"Integrity check failed: {integrity_result}"}
        
        # شمارش رکوردها در جداول اصلی
        table_counts = {}
        important_tables = ["projects", "doors", "profile_types", "inventory_items", "custom_columns"]
        
        for table in important_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                table_counts[table] = count
            except sqlite3.OperationalError:
                # جدول وجود ندارد (طبیعی است برای دیتابیس‌های قدیمی)
                table_counts[table] = None
        
        conn.close()
        return {"valid": True, "error": None, "table_counts": table_counts}
        
    except Exception as e:
        return {"valid": False, "error": str(e)}

def list_backups():
    """
    لیست تمام بکاپ‌ها به همراه اطلاعات
    
    Returns:
        list: لیست دیکشنری‌های حاوی اطلاعات بکاپ
    """
    ensure_backup_directory()
    
    backups = []
    
    # پیدا کردن تمام فایل‌های بکاپ
    for filename in os.listdir(BACKUP_DIR):
        if filename.endswith(".db") and filename.startswith("backup_"):
            backup_path = os.path.join(BACKUP_DIR, filename)
            metadata_filename = filename.replace(".db", ".json")
            metadata_path = os.path.join(BACKUP_DIR, metadata_filename)
            
            # خواندن متادیتا
            backup_info = {
                "filename": filename,
                "path": backup_path,
                "size_bytes": os.path.getsize(backup_path),
                "created": shamsi_datetime_from_timestamp(os.path.getctime(backup_path)),  # تاریخ شمسی
            }
            
            # اگر فایل JSON وجود داشته باشد، اطلاعات بیشتری بخوانیم
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        backup_info.update(metadata)
                except:
                    pass
            
            backups.append(backup_info)
    
    # مرتب‌سازی بر اساس تاریخ (جدیدترین اول)
    backups.sort(key=lambda x: x.get("datetime", x["created"]), reverse=True)
    
    return backups

def restore_backup(backup_filename, create_pre_restore_backup=True):
    """
    بازگردانی دیتابیس از یک بکاپ
    
    Args:
        backup_filename: نام فایل بکاپ
        create_pre_restore_backup: آیا قبل از restore بکاپ بگیریم؟
    
    Returns:
        tuple: (success, message)
    """
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    # بررسی وجود فایل بکاپ
    if not os.path.exists(backup_path):
        return False, "فایل بکاپ یافت نشد."
    
    # بررسی سلامت بکاپ
    verify_result = verify_backup(backup_path)
    if not verify_result["valid"]:
        return False, f"بکاپ معتبر نیست: {verify_result['error']}"
    
    db_path = Config.DB_NAME
    
    try:
        # ایجاد بکاپ از وضعیت فعلی قبل از restore (برای اطمینان)
        if create_pre_restore_backup and os.path.exists(db_path):
            print("ایجاد بکاپ از وضعیت فعلی قبل از restore...")
            success, msg = create_backup(
                reason="pre_restore_safety_backup",
                user="system",
                metadata={"restoring_from": backup_filename}
            )
            if not success:
                return False, f"خطا در ایجاد بکاپ امنیتی: {msg}"
        
        # بستن تمام اتصالات فعال (اگر ممکن باشد)
        # نکته: در محیط production باید برنامه را در حالت Maintenance قرار دهیم
        
        # استفاده از SQLite Backup API برای restore امن
        # این روش حتی اگر اتصالات باز باشند هم کار می‌کند
        # و داده‌ها را به درستی restore می‌کند
        backup_conn = sqlite3.connect(backup_path)
        target_conn = sqlite3.connect(db_path)
        
        try:
            # استفاده از backup API برای کپی امن
            with target_conn:
                backup_conn.backup(target_conn)
        finally:
            backup_conn.close()
            target_conn.close()
        
        # بازنشانی رمز عبور admin به 'admin' برای دسترسی آسان بعد از restore
        try:
            reset_admin_password_after_restore(db_path)
        except Exception as e:
            try:
                print(f"⚠ هشدار: نتوانست رمز admin را reset کند: {e}")
            except UnicodeEncodeError:
                print(f"Warning: نتوانست رمز admin را reset کند: {e}")
            # این خطا مانع restore نمی‌شود
        
        print(f"✓ دیتابیس با موفقیت بازگردانی شد از: {backup_filename}")
        return True, "دیتابیس با موفقیت بازگردانی شد. رمز عبور admin به 'admin' بازنشانی شد."
        
    except Exception as e:
        error_msg = f"خطا در بازگردانی دیتابیس: {str(e)}"
        print(f"!!! {error_msg}")
        return False, error_msg

def delete_backup(backup_filename):
    """
    حذف یک بکاپ
    
    Returns:
        tuple: (success, message)
    """
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    metadata_path = os.path.join(BACKUP_DIR, backup_filename.replace(".db", ".json"))
    
    try:
        if os.path.exists(backup_path):
            os.remove(backup_path)
        
        if os.path.exists(metadata_path):
            os.remove(metadata_path)
        
        return True, "بکاپ با موفقیت حذف شد."
    except Exception as e:
        return False, f"خطا در حذف بکاپ: {str(e)}"

def cleanup_old_backups(retention_days=7):
    """
    حذف بکاپ‌های قدیمی (بیشتر از retention_days روز)
    
    Args:
        retention_days: تعداد روزهایی که بکاپ‌ها باید نگه داشته شوند
    
    Returns:
        int: تعداد بکاپ‌های حذف شده
    """
    ensure_backup_directory()
    
    # محاسبه تاریخ حد (cutoff) با استفاده از تاریخ شمسی
    cutoff_shamsi = add_days_shamsi(-retention_days)
    cutoff_date = cutoff_shamsi.togregorian()
    deleted_count = 0
    
    for filename in os.listdir(BACKUP_DIR):
        if filename.endswith(".db") and filename.startswith("backup_"):
            backup_path = os.path.join(BACKUP_DIR, filename)
            file_time = datetime.fromtimestamp(os.path.getctime(backup_path))
            
            if file_time < cutoff_date:
                try:
                    delete_backup(filename)
                    deleted_count += 1
                    print(f"بکاپ قدیمی حذف شد: {filename}")
                except Exception as e:
                    print(f"خطا در حذف {filename}: {e}")
    
    return deleted_count

def download_backup(backup_filename):
    """
    دریافت مسیر فایل بکاپ برای دانلود
    
    Returns:
        tuple: (success, file_path_or_error)
    """
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    if not os.path.exists(backup_path):
        return False, "فایل بکاپ یافت نشد."
    
    return True, backup_path

def reset_admin_password_after_restore(db_path):
    """
    بازنشانی رمز عبور admin به 'admin' بعد از restore
    این کار برای اطمینان از دسترسی به سیستم بعد از بازگردانی بکاپ است
    اگر جدول users وجود نداشته باشد، ابتدا آن را ایجاد می‌کند
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # بررسی وجود جدول users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            # اگر جدول users وجود ندارد، ابتدا آن را ایجاد می‌کنیم
            # NOTE: This is a safety measure for restoring very old backups that don't have the users table.
            # The proper migrations will be applied when init_db() runs at application startup.
            # Migration 005_create_users_table handles this in the normal migration flow.
            try:
                print("⚠ جدول users در بکاپ وجود ندارد. در حال ایجاد...")
            except UnicodeEncodeError:
                print("Warning: جدول users در بکاپ وجود ندارد. در حال ایجاد...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
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
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
            conn.commit()
            print("✓ جدول users ایجاد شد.")
        
        # بررسی وجود کاربر admin
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        admin_user = cursor.fetchone()
        
        if admin_user:
            # بازنشانی رمز عبور admin به 'admin'
            password_hash = generate_password_hash('admin')
            cursor.execute("""
                UPDATE users 
                SET password_hash = ?,
                    is_active = 1,
                    must_change_password = 0,
                    failed_login_attempts = 0,
                    locked_until = NULL
                WHERE username = 'admin'
            """, (password_hash,))
            conn.commit()
            print("✓ رمز عبور admin به 'admin' بازنشانی شد.")
        else:
            # اگر admin وجود ندارد، ایجاد می‌کنیم
            password_hash = generate_password_hash('admin')
            cursor.execute("""
                INSERT INTO users (username, password_hash, role, is_active, must_change_password, failed_login_attempts, locked_until)
                VALUES (?, ?, 'admin', 1, 0, 0, NULL)
            """, ('admin', password_hash))
            conn.commit()
            print("✓ کاربر admin ایجاد شد با رمز 'admin'.")
        
        conn.close()
        return True
    except Exception as e:
        try:
            print(f"خطا در بازنشانی رمز admin: {e}")
        except UnicodeEncodeError:
            print(f"Error in reset admin password: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_backup_stats():
    """
    دریافت آمار کلی بکاپ‌ها
    
    Returns:
        dict: آمار بکاپ‌ها
    """
    backups = list_backups()
    
    total_size = sum(b.get("size_bytes", 0) for b in backups)
    
    return {
        "total_backups": len(backups),
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "oldest_backup": backups[-1] if backups else None,
        "newest_backup": backups[0] if backups else None
    }
