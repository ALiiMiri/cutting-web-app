import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, render_template_string
import os
import traceback  # برای نمایش خطای کامل
from flask import send_file, jsonify
import time
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display
from weasyprint import HTML, CSS
from datetime import datetime, date
import jdatetime
from inventory_init import initialize_inventory_database

# --- تنظیمات اولیه ---
DB_NAME = "cutting_web_data.db"

# --- توابع کار با دیتابیس (مستقیم در همین فایل) ---

# --- تابع کمکی برای بررسی وجود جدول ---


def check_table_exists(table_name):
    conn_check = None
    exists = False
    print(f"DEBUG: شروع بررسی وجود جدول '{table_name}'...")
    try:
        conn_check = sqlite3.connect(DB_NAME)
        cursor_check = conn_check.cursor()
        cursor_check.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        result = cursor_check.fetchone()
        if result:
            exists = True
            print(
                f"DEBUG: جدول '{table_name}' با موفقیت در دیتابیس '{DB_NAME}' پیدا شد."
            )
        else:
            print(
                f"DEBUG: جدول '{table_name}' در دیتابیس '{DB_NAME}' یافت نشد."
            )
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در check_table_exists: {e}")
        traceback.print_exc()
    finally:
        if conn_check:
            conn_check.close()
    return exists


# ------------------------------------


def initialize_database():
    """جدول پروژه‌ها، درب‌ها، ستون‌های سفارشی و گزینه‌ها را اگر وجود ندارند، با ساختار جدید می‌سازد"""
    conn = None
    try:
        print(f"DEBUG: تلاش برای اتصال به دیتابیس '{DB_NAME}' (initialize_database)")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        print("DEBUG: ایجاد جدول 'projects' (اگر وجود نداشته باشد)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                customer_name TEXT,
                order_ref TEXT,
                date_shamsi TEXT
            )
        """
        )

        print("DEBUG: ایجاد جدول 'doors' (اگر وجود نداشته باشد)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS doors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                location TEXT,
                width REAL,
                height REAL,
                quantity INTEGER,
                direction TEXT,
                row_color_tag TEXT DEFAULT 'white',
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )
        """
        )

        print("DEBUG: ایجاد جدول 'custom_columns' (اگر وجود نداشته باشد)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_columns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                column_name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """
        )

        print("DEBUG: ایجاد جدول 'custom_column_options' (اگر وجود نداشته باشد)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_column_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                column_id INTEGER NOT NULL,
                option_value TEXT NOT NULL,
                FOREIGN KEY (column_id) REFERENCES custom_columns (id) ON DELETE CASCADE
            )
        """
        )

        print("DEBUG: ایجاد جدول 'door_custom_values' (اگر وجود نداشته باشد)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS door_custom_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                door_id INTEGER NOT NULL,
                column_id INTEGER NOT NULL,
                value TEXT,
                FOREIGN KEY (door_id) REFERENCES doors (id) ON DELETE CASCADE,
                FOREIGN KEY (column_id) REFERENCES custom_columns (id) ON DELETE CASCADE
            )
        """
        )
        
        # اضافه کردن ستون تاریخ به جدول projects اگر وجود نداشته باشد
        try:
            cursor.execute("SELECT date_shamsi FROM projects LIMIT 1")
        except sqlite3.OperationalError:
            print("DEBUG: اضافه کردن ستون 'date_shamsi' به جدول 'projects'...")
            cursor.execute("ALTER TABLE projects ADD COLUMN date_shamsi TEXT")
        
        # اضافه کردن جداول سیستم انبارداری
        print("DEBUG: ایجاد جداول سیستم انبارداری...")
        
        # جدول انواع پروفیل
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profile_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,               -- نام نوع پروفیل
                description TEXT,                        -- توضیحات
                default_length INTEGER DEFAULT 600,      -- طول پیش‌فرض شاخه به سانتی‌متر
                weight_per_meter REAL DEFAULT 1.9,       -- وزن هر متر به کیلوگرم
                color TEXT,                              -- رنگ پروفیل
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # جدول موجودی انبار (شاخه‌های کامل)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_type_id INTEGER NOT NULL,        -- نوع پروفیل
                quantity INTEGER NOT NULL DEFAULT 0,     -- تعداد شاخه‌های موجود
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE
            )
        """)

        # جدول شاخه‌های برش خورده (غیر کامل)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_pieces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_type_id INTEGER NOT NULL,       -- نوع پروفیل
                length REAL NOT NULL,                   -- طول شاخه به سانتی‌متر
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE
            )
        """)

        # جدول لاگ تغییرات انبار
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_type_id INTEGER NOT NULL,        -- نوع پروفیل
                change_type TEXT NOT NULL,               -- نوع تغییر: add, remove, cut
                quantity INTEGER,                        -- تعداد شاخه‌های اضافه/کم شده (برای شاخه‌های کامل)
                length REAL,                             -- طول (برای شاخه‌های برش خورده)
                project_id INTEGER,                      -- شناسه پروژه مرتبط (اگر موجود باشد)
                description TEXT,                        -- توضیحات بیشتر
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL
            )
        """)

        # جدول تنظیمات محاسبه برش
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cutting_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,              -- نام تنظیم
                value TEXT,                             -- مقدار تنظیم
                description TEXT                        -- توضیحات
            )
        """)

        # داده‌های پیش‌فرض برای تنظیمات
        cursor.execute("""
            INSERT OR IGNORE INTO cutting_settings (name, value, description) 
            VALUES 
                ('waste_threshold', '70', 'آستانه اندازه ضایعات کوچک (سانتی‌متر)'),
                ('use_inventory', 'true', 'استفاده از سیستم انبار در محاسبات'),
                ('prefer_pieces', 'true', 'اولویت استفاده از شاخه‌های نیمه بر کامل')
        """)

        # داده‌های پیش‌فرض برای انواع پروفیل
        cursor.execute("""
            INSERT OR IGNORE INTO profile_types (name, description, default_length, weight_per_meter, color) 
            VALUES 
                ('فریم لس آلومینیومی - سفید', 'پروفیل استاندارد فریم لس رنگ سفید', 600, 1.9, 'سفید'),
                ('فریم لس آلومینیومی - آنادایز', 'پروفیل استاندارد فریم لس رنگ آنادایز', 600, 1.9, 'آنادایز'),
                ('فریم قدیمی - سفید', 'پروفیل فریم قدیمی رنگ سفید', 600, 2.1, 'سفید'),
                ('فریم قدیمی - آنادایز', 'پروفیل فریم قدیمی رنگ آنادایز', 600, 2.1, 'آنادایز'),
                ('داخل چوب دار - سفید', 'پروفیل داخل چوب دار رنگ سفید', 600, 2.2, 'سفید'),
                ('داخل چوب دار - آنادایز', 'پروفیل داخل چوب دار رنگ آنادایز', 600, 2.2, 'آنادایز')
        """)
        
        # اضافه کردن این خط در انتهای تابع قبل از conn.commit()
        ensure_base_columns_exist()

        conn.commit()
        print("DEBUG: تغییرات سایت به دیتابیس با موفقیت Commit شد.")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در initialize_database: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()


def ensure_base_columns_exist():
    """اطمینان از وجود ستون‌های پایه در دیتابیس"""
    base_columns = [
        ("rang", "رنگ پروفیل"),
        ("noe_profile", "نوع پروفیل"),
        ("vaziat", "وضعیت تولید درب"),
        ("lola", "لولا"),
        ("ghofl", "قفل"),
        ("accessory", "اکسسوری"),
        ("kolaft", "کلاف"),
        ("dastgire", "دستگیره"),
        ("tozihat", "توضیحات")
    ]
    
    for column_key, display_name in base_columns:
        conn = None
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            # بررسی وجود ستون
            cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
            result = cursor.fetchone()
            if not result:
                print(f"DEBUG: افزودن ستون پایه '{column_key}' به دیتابیس")
                cursor.execute(
                    "INSERT INTO custom_columns (column_name, display_name, is_active) VALUES (?, ?, 1)",
                    (column_key, display_name)
                )
                conn.commit()
        except sqlite3.Error as e:
            print(f"ERROR در ensure_base_columns_exist برای ستون {column_key}: {e}")
        finally:
            if conn:
                conn.close()


def get_all_projects():
    """لیستی از تمام پروژه‌ها (id, نام مشتری، شماره سفارش) را برمی‌گرداند"""
    conn = None
    projects = []
    print("DEBUG: ورود به تابع get_all_projects")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, customer_name, order_ref, date_shamsi FROM projects ORDER BY id DESC"
        )
        projects = [
            {"id": row[0], "cust_name": row[1], "order_ref": row[2], "date_shamsi": row[3]}
            for row in cursor.fetchall()
        ]
        print(f"DEBUG: get_all_projects {len(projects)} پروژه یافت.")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_all_projects: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return projects


def add_project_db(customer_name, order_ref, date_shamsi=""):
    """اضافه کردن یک پروژه جدید به دیتابیس"""
    print(f"DEBUG: ورود به تابع add_project_db، customer_name: {customer_name}, order_ref: {order_ref}, date_shamsi: {date_shamsi}")
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO projects (customer_name, order_ref, date_shamsi) VALUES (?, ?, ?)",
            (customer_name, order_ref, date_shamsi),
        )
        project_id = cursor.lastrowid
        conn.commit()
        print(f"DEBUG: پروژه‌ی جدید با آی‌دی {project_id} اضافه شد.")
        return project_id
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در add_project_db: {e}")
        traceback.print_exc()
        return None
    finally:
        if conn:
            conn.close()


def get_project_details_db(project_id):
    """جزئیات یک پروژه خاص را بر اساس ID برمی‌گرداند"""
    conn = None
    project_details = None
    print(f"DEBUG: ورود به تابع get_project_details_db برای ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, customer_name, order_ref, date_shamsi FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        if row:
            project_details = {
                "id": row[0],
                "customer_name": row[1],
                "order_ref": row[2],
                "date_shamsi": row[3]
            }
            print(f"DEBUG: جزئیات پروژه ID {project_id} یافت شد.")
        else:
            print(f"DEBUG: پروژه ID {project_id} یافت نشد.")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_project_details_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return project_details


def get_doors_for_project_db(project_id):
    """لیستی از تمام درب‌های مربوط به یک پروژه خاص را برمی‌گرداند"""
    conn = None
    doors = []
    print(f"DEBUG: ورود به تابع get_doors_for_project_db برای پروژه ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # ابتدا اطلاعات پایه درب‌ها را می‌گیریم
        cursor.execute(
            """
            SELECT id, location, width, height, quantity, direction, row_color_tag 
            FROM doors 
            WHERE project_id = ? 
            ORDER BY id
        """,
            (project_id,),
        )

        base_doors_data = cursor.fetchall()
        print(f"DEBUG: تعداد درب‌های پایه یافت شده: {len(base_doors_data)}")

        for row in base_doors_data:
            door_id = row[0]
            door_data = {
                "id": door_id,
                "location": row[1],
                "width": row[2],
                "height": row[3],
                "quantity": row[4],
                "direction": row[5],
                "row_color_tag": row[6] if row[6] else "white",
            }

            # مقادیر ستون‌های سفارشی را برای این درب دریافت می‌کنیم
            cursor.execute("""
                SELECT cc.column_name, dcv.value
                FROM door_custom_values dcv
                JOIN custom_columns cc ON dcv.column_id = cc.id
                WHERE dcv.door_id = ?
            """, (door_id,))
            
            for custom_col in cursor.fetchall():
                col_name = custom_col[0]
                col_value = custom_col[1]
                door_data[col_name] = col_value
                
            print(f"DEBUG: مقادیر سفارشی درب {door_id}: {door_data}")

            doors.append(door_data)

        print(f"DEBUG: get_doors_for_project_db {len(doors)} درب یافت.")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_doors_for_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return doors


def add_door_db(
    project_id, location, width, height, quantity, direction, row_color="white"
):
    """اطلاعات یک درب جدید را برای پروژه مشخص شده در دیتابیس ذخیره می‌کند"""
    conn = None
    door_id = None
    print(f"DEBUG: ورود به تابع add_door_db برای پروژه ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO doors (project_id, location, width, height, quantity, direction, row_color_tag) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (project_id, location, width, height, quantity, direction, row_color),
        )
        door_id = cursor.lastrowid
        conn.commit()
        print(
            f"DEBUG: درب جدید با ID {door_id} برای پروژه ID {project_id} ذخیره و commit شد."
        )
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در add_door_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return door_id


def get_all_custom_columns():
    """لیست تمام ستون‌های سفارشی را برمی‌گرداند"""
    conn = None
    columns = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, column_name, display_name, is_active FROM custom_columns ORDER BY id"
        )
        columns = [
            {"id": row[0], "key": row[1], "display": row[2], "is_active": row[3]}
            for row in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_all_custom_columns: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return columns


def get_active_custom_columns():
    """لیست ستون‌های سفارشی فعال را برمی‌گرداند"""
    conn = None
    columns = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, column_name, display_name FROM custom_columns WHERE is_active = 1 ORDER BY id"
        )
        columns = [
            {"id": row[0], "key": row[1], "display": row[2]}
            for row in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_active_custom_columns: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return columns


def add_custom_column(column_name, display_name):
    """افزودن ستون سفارشی جدید"""
    conn = None
    new_id = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO custom_columns (column_name, display_name) VALUES (?, ?)",
            (column_name, display_name),
        )
        new_id = cursor.lastrowid
        conn.commit()
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در add_custom_column: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return new_id


def update_custom_column_status(column_id, is_active):
    """تغییر وضعیت فعال/غیرفعال ستون سفارشی"""
    conn = None
    success = False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE custom_columns SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, column_id),
        )
        conn.commit()
        success = True
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در update_custom_column_status: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


def get_column_id_by_key(column_key):
    """یافتن شناسه ستون براساس کلید آن"""
    conn = None
    column_id = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM custom_columns WHERE column_name = ?", (column_key,)
        )
        result = cursor.fetchone()
        if result:
            column_id = result[0]
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_column_id_by_key: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return column_id


def get_custom_column_options(column_id):
    """گزینه‌های یک ستون سفارشی را برمی‌گرداند"""
    conn = None
    options = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT option_value FROM custom_column_options WHERE column_id = ? ORDER BY id",
            (column_id,),
        )
        options = [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_custom_column_options: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return options


def add_option_to_column(column_id, option_value):
    """افزودن گزینه جدید به ستون سفارشی"""
    conn = None
    success = False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO custom_column_options (column_id, option_value) VALUES (?, ?)",
            (column_id, option_value),
        )
        conn.commit()
        success = True
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در add_option_to_column: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


def delete_column_option(option_id):
    """حذف یک گزینه از ستون سفارشی"""
    conn = None
    success = False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM custom_column_options WHERE id = ?", (option_id,))
        conn.commit()
        success = True
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در delete_column_option: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


def update_door_custom_value(door_id, column_id, value):
    """به‌روزرسانی مقدار یک ستون سفارشی برای یک درب"""
    conn = None
    success = False
    
    print(f"DEBUG: شروع به‌روزرسانی مقدار سفارشی - درب: {door_id}, ستون: {column_id}, مقدار: '{value}'")
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # ابتدا چک می‌کنیم که آیا رکوردی وجود دارد
        cursor.execute(
            "SELECT id FROM door_custom_values WHERE door_id = ? AND column_id = ?",
            (door_id, column_id),
        )
        exists = cursor.fetchone()

        if exists:
            print(f"DEBUG: بروزرسانی مقدار موجود برای درب {door_id}, ستون {column_id}")
            cursor.execute(
                "UPDATE door_custom_values SET value = ? WHERE door_id = ? AND column_id = ?",
                (value, door_id, column_id),
            )
            print(f"DEBUG: تعداد رکوردهای به‌روزرسانی شده: {cursor.rowcount}")
        else:
            print(f"DEBUG: درج مقدار جدید برای درب {door_id}, ستون {column_id}")
            cursor.execute(
                "INSERT INTO door_custom_values (door_id, column_id, value) VALUES (?, ?, ?)",
                (door_id, column_id, value),
            )
            print(f"DEBUG: شناسه درج شده: {cursor.lastrowid}")

        conn.commit()
        print(f"DEBUG: تغییرات در door_custom_values با موفقیت ذخیره شد (commit).")
        
        # برای اطمینان، مقدار نهایی را بخوانیم
        cursor.execute(
            "SELECT value FROM door_custom_values WHERE door_id = ? AND column_id = ?",
            (door_id, column_id),
        )
        final_value = cursor.fetchone()
        print(f"DEBUG: مقدار نهایی ذخیره شده: {final_value[0] if final_value else 'NULL'}")
        
        success = True
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در update_door_custom_value: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    
    print(f"DEBUG: پایان به‌روزرسانی مقدار سفارشی - نتیجه: {'موفق' if success else 'ناموفق'}")
    return success


def get_door_custom_values(door_id):
    """دریافت مقادیر سفارشی برای درب"""
    conn = None
    custom_values = {}
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT cc.column_name, dcv.value 
            FROM door_custom_values dcv
            JOIN custom_columns cc ON dcv.column_id = cc.id
            WHERE dcv.door_id = ?
            """,
            (door_id,),
        )
        
        for row in cursor.fetchall():
            custom_values[row[0]] = row[1]
        
        # برای ستون‌های موجود ولی بدون مقدار، مقدار پیش‌فرض خالی
        all_columns = get_all_custom_columns()
        for col in all_columns:
            if col["key"] not in custom_values:
                custom_values[col["key"]] = ""
                
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_door_custom_values: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return custom_values


def update_project_db(project_id, customer_name, order_ref, date_shamsi=""):
    """به‌روزرسانی اطلاعات یک پروژه با ID مشخص"""
    conn = None
    success = False
    print(f"DEBUG: ورود به تابع update_project_db برای ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE projects SET customer_name = ?, order_ref = ?, date_shamsi = ? WHERE id = ?",
            (customer_name, order_ref, date_shamsi, project_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        print(f"DEBUG: به‌روزرسانی پروژه ID {project_id} {'انجام شد' if success else 'انجام نشد'}.")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در update_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


def delete_project_db(project_id):
    """حذف یک پروژه و تمام درب‌های مرتبط با آن (با استفاده از ON DELETE CASCADE)"""
    conn = None
    success = False
    print(f"DEBUG: ورود به تابع delete_project_db برای ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        success = cursor.rowcount > 0
        print(f"DEBUG: حذف پروژه ID {project_id} {'انجام شد' if success else 'انجام نشد'}.")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در delete_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


# --- Flask App Setup ---
app = Flask(__name__, template_folder='templates')
app.secret_key = "a_different_secret_key_now_for_sure"  # کلید مخفی

# --- مقداردهی اولیه دیتابیس ---
initialize_database()

# --- بررسی وجود جداول بعد از مقداردهی اولیه ---
print("\n--- شروع بررسی جداول ---")
check_table_exists("projects")
check_table_exists("doors")
check_table_exists("custom_columns")
check_table_exists("custom_column_options")
check_table_exists("door_custom_values")
print("--- پایان بررسی جداول ---\n")


# --- Routes (آدرس‌های وب) ---


@app.route("/")
def index():
    print("DEBUG: روت / (index) فراخوانی شد.")
    try:
        projects_list = get_all_projects()
        return render_template("index.html", projects=projects_list)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت index: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش لیست پروژه‌ها رخ داد.", "error")
        return render_template("index.html", projects=[])


@app.route("/home")
def home():
    """نام دیگر برای صفحه اصلی (برای سازگاری با تمپلیت‌ها)"""
    return index()


@app.route("/project/add", methods=["GET"])
def add_project_form():
    print("DEBUG: روت /project/add (GET - add_project_form) فراخوانی شد.")
    return render_template("add_project.html")


@app.route("/project/add", methods=["POST"])
def add_project_route():
    print("DEBUG: روت /project/add (POST - add_project_route) فراخوانی شد.")
    customer_name = request.form.get("customer_name")
    order_ref = request.form.get("order_ref")
    date_shamsi = request.form.get("date_shamsi", "")
    
    if not customer_name and not order_ref:
        flash("لطفاً حداقل نام مشتری یا شماره سفارش را وارد کنید.", "error")
        return render_template("add_project.html")
    
    new_id = add_project_db(customer_name, order_ref, date_shamsi)
    if new_id:
        flash(
            f"پروژه جدید برای مشتری '{customer_name}' (شماره سفارش: {order_ref}) با موفقیت اضافه شد.",
            "success",
        )
        print(f"DEBUG: پروژه ID {new_id} اضافه شد، ریدایرکت به index.")
        return redirect(url_for("index"))
    else:
        flash("خطایی در ذخیره پروژه رخ داد.", "error")
        return render_template("add_project.html")


@app.route("/project/<int:project_id>")
def view_project(project_id):
    print(f"DEBUG: >>>>>>> ورود به روت /project/{project_id} (view_project) <<<<<<<")
    print(f"DEBUG: Request Headers (view_project):\n{request.headers}")
    project_details = None
    door_list = []
    try:
        project_details = get_project_details_db(project_id)
        if not project_details:
            flash(f"پروژه با ID {project_id} یافت نشد.", "error")
            print(f"DEBUG: پروژه {project_id} یافت نشد، ریدایرکت به index.")
            return redirect(url_for("index"))
        door_list = get_doors_for_project_db(project_id)
        print(
            f"DEBUG: رندر کردن project_details.html برای پروژه {project_id} با {len(door_list)} درب."
        )
        return render_template(
            "project_details.html", project=project_details, doors=door_list
        )
    except Exception as e:
        print(f"!!!!!! خطای جدی در روت view_project برای ID {project_id}: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش جزئیات پروژه رخ داد. لطفاً دوباره تلاش کنید.", "error")
        print(f"DEBUG: خطا در view_project، ریدایرکت به index.")
        return redirect(url_for("index"))


@app.route("/project/<int:project_id>/add_door", methods=["GET"])
def add_door_form(project_id):
    print(
        f"DEBUG: روت /project/{project_id}/add_door (GET - add_door_form) فراخوانی شد."
    )
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash(f"پروژه با ID {project_id} یافت نشد.", "error")
        return redirect(url_for("index"))
    # <-- کلید session منحصر به فرد برای هر پروژه
    pending_doors = session.get(f"pending_doors_{project_id}", [])
    pending_count = len(pending_doors)
    print(
        f"DEBUG: نمایش فرم افزودن درب برای پروژه {project_id}. تعداد منتظر: {pending_count}"
    )
    return render_template(
        "add_door.html", project_info=project_info, pending_count=pending_count
    )


@app.route("/project/<int:project_id>/add_door", methods=["POST"])
def add_door_buffer(project_id):
    print(
        f"DEBUG: روت /project/{project_id}/add_door (POST - add_door_buffer) فراخوانی شد."
    )
    location = request.form.get("location")
    width_str = request.form.get("width")
    height_str = request.form.get("height")
    quantity_str = request.form.get("quantity")
    direction = request.form.get("direction")

    # فیلدهای سفارشی جدید
    rang = request.form.get("rang", "")
    noe_profile = request.form.get("noe_profile", "")
    vaziat = request.form.get("vaziat", "")
    lola = request.form.get("lola", "")
    ghofl = request.form.get("ghofl", "")
    accessory = request.form.get("accessory", "")
    kolaft = request.form.get("kolaft", "")
    dastgire = request.form.get("dastgire", "")
    tozihat = request.form.get("tozihat", "")
    row_color_tag = request.form.get("row_color_tag", "white")

    project_info = get_project_details_db(project_id)
    if not project_info:
        flash(f"پروژه با ID {project_id} یافت نشد.", "error")
        return redirect(url_for("index"))

    width = None
    height = None
    quantity = None
    errors = False
    try:
        if width_str:
            width = float(width_str)
        if height_str:
            height = float(height_str)
        if quantity_str:
            quantity = int(quantity_str)
        if (
            (width is not None and width <= 0)
            or (height is not None and height <= 0)
            or (quantity is not None and quantity <= 0)
        ):
            flash("مقادیر عرض، ارتفاع و تعداد باید مثبت باشند.", "error")
            errors = True
    except ValueError:
        flash("مقادیر عرض، ارتفاع و تعداد باید به صورت عددی وارد شوند.", "error")
        errors = True

    if errors:
        pending_doors = session.get(f"pending_doors_{project_id}", [])
        pending_count = len(pending_doors)
        print(f"DEBUG: خطای اعتبارسنجی در افزودن درب. بازگشت به فرم با داده‌های قبلی.")
        return render_template(
            "add_door.html",
            project_info=project_info,
            pending_count=pending_count,
            form_data=request.form,
        )

    # <-- کلید session منحصر به فرد
    pending_doors = session.get(f"pending_doors_{project_id}", [])
    new_door_data = {
        "location": location,
        "width": width,
        "height": height,
        "quantity": quantity,
        "direction": direction,
        "rang": rang,
        "noe_profile": noe_profile,
        "vaziat": vaziat,
        "lola": lola,
        "ghofl": ghofl,
        "accessory": accessory,
        "kolaft": kolaft,
        "dastgire": dastgire,
        "tozihat": tozihat,
        "row_color_tag": row_color_tag,
    }
    pending_doors.append(new_door_data)
    # <-- کلید session منحصر به فرد
    session[f"pending_doors_{project_id}"] = pending_doors
    print(
        f"DEBUG: درب به لیست موقت پروژه {project_id} اضافه شد. تعداد منتظر: {len(pending_doors)}"
    )
    flash(
        "درب به لیست موقت اضافه شد. برای ذخیره نهایی از دکمه 'اتمام' استفاده کنید.",
        "success",
    )
    return redirect(url_for("add_door_form", project_id=project_id))


@app.route("/project/<int:project_id>/finish_doors", methods=["GET"])
def finish_adding_doors(project_id):
    print(
        f"DEBUG: روت /project/{project_id}/finish_doors (GET - finish_adding_doors) فراخوانی شد."
    )
    # <-- کلید session منحصر به فرد
    pending_doors = session.get(f"pending_doors_{project_id}", [])
    saved_count = 0
    error_count = 0

    if not pending_doors:
        flash("هیچ دربی در لیست موقت برای ذخیره وجود ندارد.", "warning")
        print(f"DEBUG: لیست موقت خالی بود، ریدایرکت به view_project {project_id}")
        return redirect(url_for("view_project", project_id=project_id))

    project_info = get_project_details_db(project_id)
    if not project_info:
        flash(f"پروژه با ID {project_id} یافت نشد.", "error")
        session.pop(f"pending_doors_{project_id}", None)
        return redirect(url_for("index"))

    print(
        f"DEBUG: شروع ذخیره {len(pending_doors)} درب از لیست موقت برای پروژه {project_id}..."
    )
    for door_data in pending_doors:
        # اضافه کردن یک درب جدید و دریافت ID آن
        door_id = add_door_db(
            project_id=project_id,
            location=door_data.get("location"),
            width=door_data.get("width"),
            height=door_data.get("height"),
            quantity=door_data.get("quantity"),
            direction=door_data.get("direction"),
            row_color=door_data.get("row_color_tag", "white"),
        )

        if door_id:
            saved_count += 1

            # ذخیره مقادیر ستون‌های سفارشی
            for key, value in door_data.items():
                # اگر کلید مربوط به ستون‌های پایه نباشد
                if key not in [
                    "location",
                    "width",
                    "height",
                    "quantity",
                    "direction",
                    "row_color_tag",
                ]:
                    # ابتدا ID ستون را پیدا می‌کنیم
                    column_id = get_column_id_by_key(key)
                    if column_id:
                        # مقدار ستون سفارشی را ذخیره می‌کنیم
                        update_door_custom_value(door_id, column_id, value)
        else:
            error_count += 1

    # <-- کلید session منحصر به فرد
    session.pop(f"pending_doors_{project_id}", None)
    print(f"DEBUG: لیست موقت پروژه {project_id} از session پاک شد.")

    if error_count == 0:
        flash(f"{saved_count} درب با موفقیت در دیتابیس ذخیره شد.", "success")
    else:
        flash(
            f"{saved_count} درب ذخیره شد، اما در ذخیره {error_count} درب خطا رخ داد.",
            "error",
        )

    target_url = url_for("view_project", project_id=project_id)
    print(f"DEBUG: ذخیره نهایی انجام شد. ریدایرکت به: {target_url}")
    return redirect(target_url)


def initialize_visible_columns(project_id):
    """تنظیم ستون‌های نمایشی پیش‌فرض برای پروژه"""
    print(f"DEBUG: شروع initialize_visible_columns برای پروژه {project_id}")
    
    # اگر ستون‌های نمایشی قبلاً تنظیم شده‌اند، کاری انجام نده
    session_key = f"visible_columns_{project_id}"
    if session_key in session and session[session_key]:
        print(f"DEBUG: ستون‌های نمایشی قبلاً تنظیم شده‌اند: {session[session_key]}")
        return
    
    # دریافت همه ستون‌های فعال
    active_columns = get_active_custom_columns()
    
    # تنظیم ستون‌های پیش‌فرض (فقط ستون‌های سفارشی)
    visible_columns = [
        "rang", "noe_profile", "vaziat", "lola", "ghofl", "accessory", "kolaft", "dastgire", "tozihat"
    ]
    
    # ذخیره در جلسه
    session[session_key] = visible_columns
    print(f"DEBUG: ستون‌های نمایشی پیش‌فرض تنظیم شدند: {visible_columns}")
    print(f"DEBUG: session پس از تنظیم: {dict(session)}")


@app.route("/project/<int:project_id>/treeview")
def project_treeview(project_id):
    """نمایش درب‌های پروژه در قالب TreeView پیشرفته"""
    print(f"DEBUG: ++++ شروع روت project_treeview برای پروژه {project_id}")
    
    # برای اطمینان از عدم کش‌شدن، یک پارامتر زمانی اضافه کنیم
    refresh_param = int(time.time())
    print(f"DEBUG: پارامتر زمانی برای جلوگیری از کش: {refresh_param}")
    
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash(f"پروژه با ID {project_id} یافت نشد.", "error")
        return redirect(url_for("index"))

    # تنظیم وضعیت اولیه ستون‌ها اگر لازم باشد
    initialize_visible_columns(project_id)
    
    # درب‌ها را از دیتابیس دریافت می‌کنیم 
    doors = get_doors_for_project_db(project_id)
    print(f"DEBUG: دریافت {len(doors)} درب برای پروژه {project_id}")
    
    # دریافت ستون‌های قابل نمایش از جلسه کاربر
    visible_columns = session.get(f"visible_columns_{project_id}", [])
    
    # اضافه کردن ستون‌های پایه برای تری‌ویو
    basic_columns = ["location", "width", "height", "quantity", "direction"]
    for col in basic_columns:
        if col not in visible_columns:
            visible_columns.append(col)
    
    print(f"DEBUG: ستون‌های نمایشی از جلسه با ستون‌های پایه: {visible_columns}")
    
    # دریافت ستون‌های سفارشی فعال
    active_custom_columns = get_active_custom_columns()
    
    # بررسی سریع مقادیر سفارشی
    for door in doors[:5]:  # فقط 5 درب اول را برای دیباگ بررسی می‌کنیم
        print(f"DEBUG: درب {door['id']} - مقادیر سفارشی: {door}")
    
    return render_template(
        "project_treeview.html", 
        project=project_info, 
        doors=doors, 
        refresh_param=refresh_param,
        visible_columns=visible_columns,
        active_custom_columns=active_custom_columns
    )


@app.route("/project/<int:project_id>/door/<int:door_id>/set_color", methods=["POST"])
def set_door_color(project_id, door_id):
    """تغییر رنگ یک درب"""
    color = request.form.get("color", "white")

    # اتصال به دیتابیس
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # به‌روزرسانی رنگ در جدول درب‌ها
        cursor.execute(
            "UPDATE doors SET row_color_tag = ? WHERE id = ? AND project_id = ?",
            (color, door_id, project_id),
        )
        conn.commit()
        return jsonify({"success": True})
    except sqlite3.Error as e:
        print(f"خطا در تغییر رنگ: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/project/<int:project_id>/delete_door/<int:door_id>", methods=["POST"])
def delete_door(project_id, door_id):
    """حذف یک درب از پروژه"""
    print(f"DEBUG: درخواست برای حذف درب با ID {door_id} از پروژه {project_id}")
    
    # اتصال به دیتابیس
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # ابتدا بررسی می‌کنیم که آیا درب متعلق به این پروژه است
        cursor.execute(
            "SELECT id FROM doors WHERE id = ? AND project_id = ?",
            (door_id, project_id),
        )
        door = cursor.fetchone()
        
        if not door:
            print(f"ERROR: درب با ID {door_id} در پروژه {project_id} یافت نشد")
            return jsonify({"success": False, "error": "درب مورد نظر یافت نشد"}), 404
        
        # حذف مقادیر ستون‌های سفارشی مربوط به این درب
        cursor.execute("DELETE FROM door_custom_values WHERE door_id = ?", (door_id,))
        
        # حذف درب از جدول اصلی
        cursor.execute("DELETE FROM doors WHERE id = ?", (door_id,))
        
        conn.commit()
        print(f"DEBUG: درب با ID {door_id} با موفقیت حذف شد")
        return jsonify({"success": True})
    except sqlite3.Error as e:
        print(f"ERROR: خطا در حذف درب: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/project/<int:project_id>/export/excel", methods=["GET"])
def export_to_excel(project_id):
    """خروجی اکسل از داده‌های پروژه"""
    import pandas as pd
    import os
    from datetime import datetime

    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("پروژه مورد نظر یافت نشد.", "error")
        return redirect(url_for("index"))

    doors = get_doors_for_project_db(project_id)
    if not doors:
        flash("هیچ دربی برای این پروژه ثبت نشده است.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # تبدیل به دیتافریم پانداس
    df = pd.DataFrame(doors)

    # تنظیم مسیر فایل خروجی
    export_dir = "static/exports"
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    customer_name = project_info.get("customer_name", "unknown")
    excel_filename = f"{customer_name}_{timestamp}.xlsx"
    excel_path = os.path.join(export_dir, excel_filename)

    # ذخیره به فایل اکسل
    df.to_excel(excel_path, index=False)

    # ارسال فایل به کاربر
    return send_file(excel_path, as_attachment=True)


@app.route("/project/<int:project_id>/calculate_cutting", methods=["GET"])
def calculate_cutting(project_id):
    """محاسبه برش بهینه با پیش‌پردازش مقادیر برای قالب"""
    STOCK_LENGTH = 600  # طول استاندارد شاخه
    WEIGHT_PER_METER = 1.9  # وزن هر متر
    WASTE_THRESHOLD = 70  # آستانه ضایعات کوچک (سانتی‌متر)

    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("پروژه مورد نظر یافت نشد.", "error")
        return redirect(url_for("index"))

    doors = get_doors_for_project_db(project_id)
    if not doors:
        flash("هیچ دربی برای این پروژه ثبت نشده است.", "warning")
        return redirect(url_for("view_project", project_id=project_id))

    # --- جمع‌آوری قطعات مورد نیاز ---
    required_pieces = []  # لیست (طول، تعداد)

    valid_rows = 0
    for door in doors:
        try:
            width = float(door["width"])
            height = float(door["height"])
            quantity = int(door["quantity"])

            if width <= 0 or height <= 0 or quantity <= 0:
                continue  # رد کردن داده‌های نامعتبر

            # محاسبه مشابه نسخه دسکتاپ
            # دو قطعه عمودی برای هر درب
            required_pieces.append((height, quantity * 2))
            # یک قطعه افقی برای هر درب
            required_pieces.append((width, quantity * 1))

            valid_rows += 1

        except (ValueError, TypeError, KeyError) as e:
            print(f"خطا در پردازش درب {door.get('id')}: {e}")
            continue

    if not required_pieces:
        flash(
            "هیچ درب معتبری (با عرض، ارتفاع و تعداد عددی مثبت) در جدول برای محاسبه برش یافت نشد.",
            "warning",
        )
        return redirect(url_for("view_project", project_id=project_id))

    if valid_rows < len(doors):
        flash(
            "برخی ردیف‌ها به دلیل داشتن مقادیر نامعتبر (غیرعددی یا صفر) در عرض، ارتفاع یا تعداد، در محاسبه نادیده گرفته شدند.",
            "warning",
        )

    # --- الگوریتم بسته‌بندی (First Fit Decreasing) ---
    bins = []  # هر شاخه به صورت: {"pieces": [], "remaining": float}

    # تبدیل به لیست صاف: [(length1, 1), (length1, 1), ... (length2, 1), ...]
    flat_pieces = []
    for length, count in required_pieces:
        flat_pieces.extend([length] * count)

    # مرتب‌سازی نزولی براساس طول
    sorted_pieces = sorted(flat_pieces, reverse=True)

    for piece_length in sorted_pieces:
        if piece_length > STOCK_LENGTH:
            flash(
                f"امکان برش قطعه‌ای به طول {piece_length}cm از شاخه {STOCK_LENGTH}cm وجود ندارد!",
                "error",
            )
            return redirect(url_for("view_project", project_id=project_id))

        placed = False
        # سعی در قرار دادن در شاخه‌های موجود
        for bin_data in bins:
            if bin_data["remaining"] >= piece_length:
                bin_data["pieces"].append(piece_length)
                bin_data["remaining"] -= piece_length
                placed = True
                break

        # اگر در هیچ شاخه‌ای جا نشد، یک شاخه جدید ایجاد کن
        if not placed:
            bins.append(
                {"pieces": [piece_length], "remaining": STOCK_LENGTH - piece_length}
            )

    # --- محاسبه آمار ---
    total_bins_used = len(bins)

    # اطلاعات قطعات کوچک (ضایعات)
    small_pieces_info = [
        (i + 1, bin_data["remaining"])
        for i, bin_data in enumerate(bins)
        if 0 < bin_data["remaining"] < WASTE_THRESHOLD
    ]
    small_pieces_count = len(small_pieces_info)
    total_small_waste_length = sum(rem for _, rem in small_pieces_info)
    total_small_waste_weight = (
        total_small_waste_length / 100
    ) * WEIGHT_PER_METER  # تبدیل سانتی‌متر به متر

    # مشاهده اطلاعات ضایعات متوسط و بزرگ برای تحلیل بیشتر
    medium_pieces_info = [
        (i + 1, bin_data["remaining"])
        for i, bin_data in enumerate(bins)
        if WASTE_THRESHOLD <= bin_data["remaining"] < (STOCK_LENGTH / 2)
    ]
    large_pieces_info = [
        (i + 1, bin_data["remaining"])
        for i, bin_data in enumerate(bins)
        if (STOCK_LENGTH / 2) <= bin_data["remaining"] < STOCK_LENGTH
    ]

    medium_pieces_count = len(medium_pieces_info)
    large_pieces_count = len(large_pieces_info)
    total_medium_waste_length = sum(rem for _, rem in medium_pieces_info)
    total_large_waste_length = sum(rem for _, rem in large_pieces_info)

    # محاسبه کل ضایعات
    total_waste_length = sum(bin_data["remaining"] for bin_data in bins)
    total_waste_weight = (total_waste_length / 100) * WEIGHT_PER_METER
    total_waste_percentage = (
        total_waste_length / (STOCK_LENGTH * total_bins_used)
    ) * 100

    # ---------- پیش‌پردازش داده‌ها برای قالب ----------
    # این بخش به منظور جلوگیری از خطای سینتکسی در قالب اضافه شده است

    # گرد کردن مقادیر اصلی
    small_waste_length_rounded = round(total_small_waste_length, 1)
    small_waste_weight_rounded = round(total_small_waste_weight, 2)
    total_waste_percentage_rounded = round(total_waste_percentage, 1)

    # پیش‌پردازش داده‌های شاخه‌ها
    processed_bins = []
    for i, bin_data in enumerate(bins):
        used_length = STOCK_LENGTH - bin_data["remaining"]
        used_percent = int((used_length / STOCK_LENGTH) * 100)
        waste_percent = int((bin_data["remaining"] / STOCK_LENGTH) * 100)
        # فرمت‌بندی درصدها به صورت رشته‌ای با % برای CSS
        used_percent_style = f"{used_percent}%"
        waste_percent_style = f"{waste_percent}%"
        # گرد کردن اعداد قطعات
        rounded_pieces = [round(piece, 1) for piece in bin_data["pieces"]]

        processed_bins.append(
            {
                "index": i + 1,
                "pieces": [round(piece, 1) for piece in bin_data["pieces"]],
                "remaining": round(bin_data["remaining"], 1),
                "used_length": round(used_length, 1),
                "used_percent": used_percent,
                "waste_percent": waste_percent,
                "used_percent_style": used_percent_style,  # این خط اضافه شده
                "waste_percent_style": waste_percent_style,  # این خط اضافه شده
                "waste_type": (
                    "small"
                    if bin_data["remaining"] < WASTE_THRESHOLD
                    else (
                        "medium"
                        if bin_data["remaining"] < (STOCK_LENGTH / 2)
                        else "large"
                    )
                ),
            }
        )
    # رندر نتیجه در قالب HTML با مقادیر از پیش محاسبه شده
    return render_template(
        "cutting_result.html",
        project=project_info,
        bins=processed_bins,
        total_bins=total_bins_used,
        stock_length=STOCK_LENGTH,
        waste_threshold=WASTE_THRESHOLD,
        small_pieces_count=small_pieces_count,
        small_waste_length=small_waste_length_rounded,
        small_waste_weight=small_waste_weight_rounded,
        medium_pieces_count=medium_pieces_count,
        medium_waste_length=round(total_medium_waste_length, 1),
        large_pieces_count=large_pieces_count,
        large_waste_length=round(total_large_waste_length, 1),
        total_waste_length=round(total_waste_length, 1),
        total_waste_weight=round(total_waste_weight, 2),
        total_waste_percentage=total_waste_percentage_rounded,
    )


def ensure_default_custom_columns():
    """اضافه کردن ستون‌های سفارشی پیش‌فرض اگر هیچ ستونی وجود نداشته باشد"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # بررسی تعداد ستون‌های سفارشی فعال
        cursor.execute("SELECT COUNT(*) FROM custom_columns WHERE is_active = 1")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print("DEBUG: هیچ ستون سفارشی فعالی یافت نشد. اضافه کردن ستون‌های پیش‌فرض...")
            
            # ستون‌های پیش‌فرض را تعریف کنیم
            default_columns = [
                ("rang", "رنگ پروفیل"),
                ("noe_profile", "نوع پروفیل"),
                ("vaziat", "وضعیت تولید درب"),
                ("lola", "لولا"),
                ("ghofl", "قفل"),
                ("accessory", "اکسسوری"),
                ("kolaft", "کلافت"),
                ("dastgire", "دستگیره"),
                ("tozihat", "توضیحات")
            ]
            
            for column_key, display_name in default_columns:
                # ابتدا چک کنیم که این ستون قبلاً وجود دارد یا خیر
                cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
                column = cursor.fetchone()
                
                if column:
                    # اگر وجود دارد، فعال کنیم
                    cursor.execute("UPDATE custom_columns SET is_active = 1 WHERE id = ?", (column[0],))
                    print(f"DEBUG: ستون '{column_key}' فعال شد")
                else:
                    # اگر وجود ندارد، اضافه کنیم
                    cursor.execute(
                        "INSERT INTO custom_columns (column_name, display_name, is_active) VALUES (?, ?, 1)",
                        (column_key, display_name)
                    )
                    print(f"DEBUG: ستون '{column_key}' اضافه شد")
            
            conn.commit()
            print("DEBUG: ستون‌های پیش‌فرض با موفقیت اضافه/فعال شدند")
        
    except sqlite3.Error as e:
        print(f"ERROR: خطا در تابع ensure_default_custom_columns: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()


@app.route("/project/<int:project_id>/batch_edit", methods=["GET"])
def batch_edit_form(project_id):
    """نمایش فرم ویرایش گروهی"""
    door_ids = request.args.get("door_ids")
    if not door_ids:
        flash("هیچ دربی برای ویرایش انتخاب نشده است.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # تبدیل رشته به لیست
    door_ids = door_ids.split(",")

    # بازیابی اطلاعات پایه
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("پروژه مورد نظر یافت نشد.", "error")
        return redirect(url_for("index"))

    # دریافت وضعیت ستون‌های نمایشی از جلسه
    session_key = f"visible_columns_{project_id}"
    visible_columns = session.get(session_key, [])
    
    # اگر هیچ ستونی برای نمایش انتخاب نشده، همه ستون‌ها را نمایش می‌دهیم
    if not visible_columns:
        # اجرای تابع مقداردهی اولیه
        initialize_visible_columns(project_id)
        # بازخوانی مجدد از سشن
        visible_columns = session.get(session_key, [])
    
    # بررسی و اضافه کردن ستون‌های پیش‌فرض اگر لازم باشد
    ensure_default_custom_columns()
    
    # اضافه کردن ستون‌های پایه پیش‌فرض اگر در لیست نباشند
    default_visible_columns = [
        "rang", "noe_profile", "vaziat", "lola", 
        "ghofl", "accessory", "kolaft", "dastgire", "tozihat"
    ]
    
    # اضافه کردن ستون‌های پیش‌فرض که در لیست نیستند
    for col in default_visible_columns:
        if col not in visible_columns:
            visible_columns.append(col)
    
    # ستون‌های پایه که همیشه نمایش داده می‌شوند
    basic_columns = ["location", "width", "height", "quantity", "direction"]
    
    # دریافت گزینه‌های ستون‌های قابل ویرایش
    columns_info = get_active_custom_columns()
    print(f"DEBUG: تعداد ستون‌های سفارشی فعال: {len(columns_info)}")  # برای دیباگ
    column_options = {}

    # گزینه‌های پیش‌فرض
    default_options = {
        "rang": ["سفید", "آنادایز"],
        "noe_profile": ["فریم لس آلومینیومی", "فریم قدیمی", "فریم داخل چوب دار"],
        "vaziat": ["همزمان با تولید چهارچوب", "تولید درب در آینده", "بدون درب"],
        "lola": ["OTLAV", "HTH", "NHN", "متفرقه"],
        "ghofl": ["STV", "ایزدو", "NHN", "HTN"],
        "accessory": ["آلومینیوم آستانه فاق و زبانه", "آرامبند مرونی", "قفل برق سارو با فنر"],
        "kolaft": ["دو طرفه", "سه طرفه"],
        "dastgire": ["دو تیکه", "ایزدو", "گریف ورک", "متفرقه"],
        "direction": ["راست", "چپ"],
    }

    # برای هر ستون سفارشی، گزینه‌های آن را دریافت کنیم
    for column in columns_info:
        column_key = column["key"]
        
        # تغییر منطق: یک ستون باید تیک بخورد اگر در لیست ستون‌های نمایشی نباشد
        is_visible = column_key in visible_columns
        is_checked = not is_visible  # منطق معکوس: اگر ستون نمایش داده نمی‌شود، باید تیک بخورد
        
        # ترکیب گزینه‌های پیش‌فرض با گزینه‌های دیتابیس
        options = []
        
        # اگر گزینه‌های پیش‌فرض برای این ستون وجود دارد
        if column_key in default_options:
            options = default_options[column_key]
        else:
            # گزینه‌های دیتابیس را دریافت کنیم
            db_options = get_custom_column_options(column["id"])
            if db_options:
                options = db_options
        
        column_options[column_key] = {
            "display": column["display"],
            "options": options,
            "visible": column_key not in basic_columns,  # ستون‌های پایه همیشه باید نمایش داده شوند
            "checked": is_checked  # وضعیت چک‌باکس بر اساس عدم وجود در لیست نمایش
        }

    # افزودن پارامتر زمانی برای جلوگیری از کش شدن صفحه
    timestamp = int(time.time())

    # برای دیباگ
    print("DEBUG visible_columns:", visible_columns)
    print("DEBUG column_options:", column_options)

    return render_template(
        "batch_edit.html",
        project=project_info,
        door_ids=door_ids,
        column_options=column_options,
        visible_columns=visible_columns,
        timestamp=timestamp
    )


@app.route("/project/<int:project_id>/batch_edit", methods=["POST"])
def apply_batch_edit(project_id):
    """اعمال تغییرات گروهی روی درب‌های انتخاب شده"""
    
    # حذف بررسی احراز هویت کاربر چون flask_login استفاده نشده
    # if not current_user.is_authenticated:
    #    return redirect(url_for("login"))
    
    door_ids = request.form.get("door_ids")
    if not door_ids:
        flash("هیچ دربی برای ویرایش انتخاب نشده است.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    door_ids = door_ids.split(",")
    print(f"DEBUG: به‌روزرسانی درب‌های {door_ids}")

    # دریافت ستون‌های قابل نمایش
    session_key = f"visible_columns_{project_id}"
    visible_columns = session.get(session_key, [])

    # بررسی اینکه کدام ستون‌ها باید به‌روزرسانی شوند
    columns_to_update = {}
    base_fields_to_update = {}
    
    # ذخیره ستون‌های انتخاب شده برای استفاده بعدی
    checked_columns = []
    
    for key, value in request.form.items():
        # اگر یک checkbox برای ستون فعال بود و مقدار وارد شده بود
        if key.startswith("update_") and value == "on":
            field_key = key.replace("update_", "")
            field_value_key = f"value_{field_key}"
            
            # اضافه کردن به لیست ستون‌های انتخاب شده
            checked_columns.append(field_key)
            
            if field_value_key in request.form:
                new_value = request.form.get(field_value_key)
                
                # بررسی اینکه آیا فیلد پایه است یا سفارشی
                if field_key in ["location", "width", "height", "quantity", "direction"]:
                    # فقط اگر فیلد پایه در ستون‌های قابل نمایش باشد، اجازه به‌روزرسانی بده
                    if field_key in visible_columns:
                        base_fields_to_update[field_key] = new_value
                else:
                    # فقط اگر فیلد سفارشی در ستون‌های قابل نمایش باشد، اجازه به‌روزرسانی بده
                    if field_key in visible_columns:
                        columns_to_update[field_key] = new_value
    
    # ذخیره ستون‌های انتخاب شده در سشن
    batch_edit_checked_key = f"batch_edit_checked_{project_id}"
    session[batch_edit_checked_key] = checked_columns

    print(f"DEBUG: فیلدهای پایه برای به‌روزرسانی: {base_fields_to_update}")
    print(f"DEBUG: فیلدهای سفارشی برای به‌روزرسانی: {columns_to_update}")

    if not columns_to_update and not base_fields_to_update:
        flash("هیچ فیلدی برای به‌روزرسانی انتخاب نشده است.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # اعمال تغییرات روی درب‌های انتخاب شده
    successful_updates = 0
    failed_updates = 0
    success_messages = []
    error_messages = []
    
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        for door_id in door_ids:
            try:
                door_id = int(door_id)
                door_updated = False
                
                # دریافت اطلاعات کنونی درب برای استفاده در گزارش
                cursor.execute(
                    "SELECT location FROM doors WHERE id = ?", 
                    (door_id,)
                )
                door_info = cursor.fetchone()
                door_location = door_info[0] if door_info else f"ID: {door_id}"
                
                # به‌روزرسانی فیلدهای پایه
                if base_fields_to_update:
                    update_parts = []
                    params = []
                    field_updates = []
                    
                    for field, value in base_fields_to_update.items():
                        if field == "width" or field == "height" or field == "quantity":
                            try:
                                # تبدیل به عدد
                                value = float(value) if field != "quantity" else int(value)
                                update_parts.append(f"{field} = ?")
                                params.append(value)
                                field_updates.append(f"{field} = {value}")
                            except (ValueError, TypeError):
                                error_msg = f"مقدار نامعتبر برای {field}: '{value}' در درب {door_location}"
                                print(f"WARNING: {error_msg}")
                                error_messages.append(error_msg)
                                continue
                        else:
                            update_parts.append(f"{field} = ?")
                            params.append(value)
                            field_updates.append(f"{field} = '{value}'")
                    
                    if update_parts:
                        query = f"UPDATE doors SET {', '.join(update_parts)} WHERE id = ?"
                        params.append(door_id)
                        
                        try:
                            cursor.execute(query, params)
                            if cursor.rowcount > 0:
                                door_updated = True
                                msg = f"درب {door_location}: به‌روزرسانی {', '.join(field_updates)}"
                                success_messages.append(msg)
                                print(f"DEBUG: {msg}")
                        except sqlite3.Error as e:
                            error_msg = f"خطا در به‌روزرسانی فیلدهای پایه برای درب {door_location}: {str(e)}"
                            error_messages.append(error_msg)
                            print(f"ERROR: {error_msg}")
                
                # به‌روزرسانی فیلدهای سفارشی
                for column_key, new_value in columns_to_update.items():
                    try:
                        # پیدا کردن ID ستون
                        column_id = get_column_id_by_key(column_key)
                        if not column_id:
                            error_msg = f"ستون '{column_key}' یافت نشد برای درب {door_location}"
                            error_messages.append(error_msg)
                            print(f"ERROR: {error_msg}")
                            continue
                            
                        # دریافت نام نمایشی ستون
                        cursor.execute(
                            "SELECT display_name FROM custom_columns WHERE id = ?", 
                            (column_id,)
                        )
                        display_result = cursor.fetchone()
                        column_display = display_result[0] if display_result else column_key
                        
                        # بررسی مقدار فعلی برای گزارش تغییرات
                        cursor.execute(
                            "SELECT value FROM door_custom_values WHERE door_id = ? AND column_id = ?",
                            (door_id, column_id)
                        )
                        current_result = cursor.fetchone()
                        current_value = current_result[0] if current_result else None
                        
                        # ذخیره مقدار جدید با استفاده از تابع update_door_custom_value
                        update_door_custom_value(door_id, column_id, new_value)
                        door_updated = True
                        
                        # ساختن پیام موفقیت
                        if current_value:
                            msg = f"ستون '{column_display}' از '{current_value}' به '{new_value}' تغییر کرد"
                        else:
                            msg = f"ستون '{column_display}' به '{new_value}' تنظیم شد"
                            
                        success_messages.append(f"درب {door_location}: {msg}")
                        print(f"DEBUG: درب {door_location}: {msg}")
                    
                    except Exception as e:
                        error_msg = f"خطا در به‌روزرسانی ستون '{column_key}' برای درب {door_location}: {str(e)}"
                        error_messages.append(error_msg)
                        print(f"ERROR: {error_msg}")
                
                # شمارش درب‌های به‌روزرسانی شده
                if door_updated:
                    successful_updates += 1
                else:
                    failed_updates += 1
                    error_msg = f"هیچ فیلدی برای درب {door_location} به‌روزرسانی نشد"
                    error_messages.append(error_msg)
                    print(f"WARNING: {error_msg}")

            except Exception as e:
                failed_updates += 1
                error_msg = f"خطا در به‌روزرسانی درب {door_id}: {str(e)}"
                error_messages.append(error_msg)
                print(f"ERROR: {error_msg}")
                traceback.print_exc()
        
        # ذخیره تغییرات
        conn.commit()
        print(f"DEBUG: همه تغییرات با موفقیت ذخیره شد. {successful_updates} درب به‌روزرسانی شد.")

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        failed_updates += len(door_ids)
        error_msg = f"خطا در دیتابیس: {str(e)}"
        error_messages.append(error_msg)
        print(f"ERROR: {error_msg}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

    # نمایش پیام‌های مناسب
    if successful_updates > 0:
        success_summary = f"{successful_updates} درب با موفقیت به‌روزرسانی شد."
        if len(success_messages) <= 5:  # نمایش جزئیات فقط برای تعداد کمی مورد
            success_summary += "<br>" + "<br>".join(success_messages[:5])
        flash(success_summary, "success")
    
    if failed_updates > 0:
        error_summary = f"{failed_updates} درب با خطا مواجه شد."
        if len(error_messages) <= 5:  # نمایش جزئیات فقط برای تعداد کمی خطا
            error_summary += "<br>" + "<br>".join(error_messages[:5])
        flash(error_summary, "error")
    
    if successful_updates == 0 and failed_updates == 0:
        flash("هیچ به‌روزرسانی انجام نشد.", "warning")

    # افزودن پارامتر زمانی برای جلوگیری از کش شدن صفحه
    timestamp = int(time.time())
    return redirect(url_for("project_treeview", project_id=project_id, t=timestamp))


@app.route("/project/<int:project_id>/toggle_column_display", methods=["POST"])
def toggle_column_display(project_id):
    """تغییر وضعیت نمایش یک ستون"""
    column_key = request.form.get("column_key")
    is_visible = request.form.get("is_visible", "0") == "1"  # تبدیل به بولین
    
    if not column_key:
        return jsonify({"success": False, "error": "کلید ستون ارسال نشده است"})
    
    try:
        session_key = f"visible_columns_{project_id}"
        visible_columns = session.get(session_key, [])
        
        # اگر ستون باید نمایش داده شود و در لیست نیست، اضافه می‌کنیم
        if is_visible and column_key not in visible_columns:
            visible_columns.append(column_key)
            session[session_key] = visible_columns
            print(f"DEBUG: ستون {column_key} به لیست ستون‌های نمایشی پروژه {project_id} اضافه شد")
            return jsonify({"success": True})
        
        # اگر ستون نباید نمایش داده شود و در لیست هست، حذف می‌کنیم
        elif not is_visible and column_key in visible_columns:
            # قبل از حذف بررسی کنیم که آیا ستون حاوی داده است یا خیر
            # اگر ستون دارای داده باشد، اجازه مخفی کردن نمی‌دهیم
            if column_key in ["width", "height", "quantity", "direction"]:
                return jsonify({
                    "success": False, 
                    "error": f"ستون '{column_key}' یک ستون پایه است و نمی‌تواند مخفی شود"
                })
                
            # بررسی تعداد داده‌های ستون با استفاده از اندپوینت check_column_can_hide
            column_check = check_column_can_hide_internal(project_id, column_key)
            if not column_check.get("can_hide", True):
                return jsonify({
                    "success": False, 
                    "error": column_check.get("reason", "این ستون دارای داده است و نمی‌تواند مخفی شود")
                })
            
            # اگر به اینجا رسیدیم، ستون می‌تواند مخفی شود
            visible_columns.remove(column_key)
            session[session_key] = visible_columns
            print(f"DEBUG: ستون {column_key} از لیست ستون‌های نمایشی پروژه {project_id} حذف شد")
            return jsonify({"success": True})
        
        # در غیر این صورت، نیازی به تغییر نیست
        return jsonify({"success": True, "info": "وضعیت ستون تغییری نکرد"})
        
    except Exception as e:
        print(f"ERROR: خطا در تغییر وضعیت نمایش ستون {column_key}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


def check_column_can_hide_internal(project_id, column_key):
    """بررسی اینکه آیا یک ستون می‌تواند مخفی شود یا خیر (نسخه داخلی)"""
    if not column_key:
        return {"can_hide": True, "reason": "کلید ستون خالی است"}
    
    try:
        # بررسی اینکه آیا ستون در پایگاه داده وجود دارد
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # ابتدا شناسه ستون را پیدا می‌کنیم
        cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
        result = cursor.fetchone()
        if not result:
            # اگر ستون وجود ندارد، می‌تواند مخفی شود
            return {"can_hide": True, "reason": "ستون در پایگاه داده وجود ندارد"}
        
        column_id = result[0]
        
        # حالا بررسی می‌کنیم که آیا این ستون در جدول door_custom_values دارای مقدار است
        cursor.execute("""
            SELECT COUNT(*) FROM door_custom_values 
            JOIN doors ON door_custom_values.door_id = doors.id
            WHERE door_custom_values.column_id = ? 
            AND doors.project_id = ?
            AND door_custom_values.value IS NOT NULL 
            AND door_custom_values.value != ''
        """, (column_id, project_id))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        if count > 0:
            # اگر این ستون دارای مقدار است، نمی‌تواند مخفی شود
            return {
                "can_hide": False, 
                "reason": f"ستون '{column_key}' دارای {count} مقدار در پروژه است"
            }
        
        # اگر به اینجا رسیدیم، یعنی ستون می‌تواند مخفی شود
        return {"can_hide": True, "reason": "ستون هیچ داده‌ای ندارد"}
        
    except sqlite3.Error as e:
        print(f"خطا در بررسی ستون {column_key}: {e}")
        # در صورت بروز خطا، از روی احتیاط اجازه مخفی کردن نمی‌دهیم
        return {"can_hide": False, "reason": f"خطای پایگاه داده: {e}"}
    except Exception as e:
        print(f"خطای غیرمنتظره در بررسی ستون {column_key}: {e}")
        return {"can_hide": False, "reason": f"خطای غیرمنتظره: {e}"}


@app.route("/project/<int:project_id>/check_column_can_hide", methods=["POST"])
def check_column_can_hide(project_id):
    """بررسی می‌کند که آیا ستون مورد نظر می‌تواند مخفی شود یا خیر"""
    column_key = request.form.get("column_key")
    if not column_key:
        return jsonify({"can_hide": False, "reason": "کلید ستون مشخص نشده است."})
    
    return jsonify(check_column_can_hide_internal(project_id, column_key))


# --- مسیرهای مربوط به سیستم انبار ---

@app.route("/inventory")
def inventory_route():
    """صفحه اصلی مدیریت انبار"""
    try:
        # در اینجا اطلاعات مورد نیاز برای داشبورد انبار را استخراج می‌کنیم
        # برای مثال، آمار کلی انبار و انواع پروفیل
        
        # آمار کلی انبار (فعلاً با مقادیر پیش‌فرض)
        stats = {
            "total_profiles": 0,
            "total_complete_pieces": 0,
            "total_cut_pieces": 0,
            "total_weight": 0,
            "total_complete_length": 0,
            "total_cut_length": 0,
            "total_length": 0,
            "average_piece_length": 0
        }
        
        # لیست انواع پروفیل (فعلاً خالی)
        profiles = []
        
        return render_template("inventory_dashboard.html", stats=stats, profiles=profiles)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه مدیریت انبار رخ داد.", "error")
        return redirect(url_for("index"))


@app.route("/inventory/profile_types")
def profile_types_route():
    """صفحه مدیریت انواع پروفیل"""
    try:
        # در اینجا لیست انواع پروفیل را از دیتابیس دریافت می‌کنیم
        # فعلاً با لیست خالی کار می‌کنیم
        profile_types = []
        
        return render_template("profile_types.html", profile_types=profile_types)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت profile_types_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه انواع پروفیل رخ داد.", "error")
        return redirect(url_for("inventory_route"))


@app.route("/inventory/settings")
def inventory_settings_route():
    """صفحه تنظیمات انبار"""
    try:
        # در اینجا تنظیمات فعلی را از دیتابیس دریافت می‌کنیم
        # فعلاً با مقادیر پیش‌فرض کار می‌کنیم
        settings = {
            "waste_threshold": 70,
            "use_inventory": True,
            "prefer_pieces": True
        }
        
        return render_template("inventory_settings.html", settings=settings)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory_settings_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه تنظیمات انبار رخ داد.", "error")
        return redirect(url_for("inventory_route"))


@app.route("/inventory/logs")
def inventory_logs_route():
    """صفحه تاریخچه تغییرات انبار"""
    try:
        # در اینجا لیست لاگ‌های تغییرات را از دیتابیس دریافت می‌کنیم
        # فعلاً با لیست خالی کار می‌کنیم
        logs = []
        
        return render_template("inventory_logs.html", logs=logs)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory_logs_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه تاریخچه تغییرات انبار رخ داد.", "error")
        return redirect(url_for("inventory_route"))


@app.route("/inventory/profile/<int:profile_id>")
def inventory_details_route(profile_id):
    """صفحه جزئیات موجودی یک نوع پروفیل"""
    try:
        # در اینجا اطلاعات پروفیل و موجودی آن را از دیتابیس دریافت می‌کنیم
        # فعلاً با مقادیر پیش‌فرض کار می‌کنیم
        profile = {
            "id": profile_id,
            "name": "نوع پروفیل",
            "description": "توضیحات",
            "default_length": 600,
            "weight_per_meter": 1.9,
            "color": "#cccccc"
        }
        
        items = {
            "complete_pieces": 0,
            "cut_pieces": []
        }
        
        return render_template("profile_inventory_details.html", profile=profile, items=items)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory_details_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه جزئیات موجودی رخ داد.", "error")
        return redirect(url_for("inventory_route"))


@app.route("/inventory/profile/<int:profile_id>/add")
def add_inventory_items_route(profile_id):
    """صفحه افزودن موجودی برای یک نوع پروفیل"""
    try:
        # در اینجا اطلاعات پروفیل را از دیتابیس دریافت می‌کنیم
        # فعلاً با مقادیر پیش‌فرض کار می‌کنیم
        profile = {
            "id": profile_id,
            "name": "نوع پروفیل",
            "default_length": 600
        }
        
        return render_template("add_items.html", profile=profile)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت add_inventory_items_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه افزودن موجودی رخ داد.", "error")
        return redirect(url_for("inventory_route"))


@app.route("/project/<int:project_id>/export_pdf", methods=["GET"])
def export_table_to_pdf_html(project_id):
    """صفحه خروجی PDF از جدول پروژه با استفاده از HTML"""
    try:
        # دریافت اطلاعات پروژه و درب‌ها
        project = get_project_details_db(project_id)
        if not project:
            flash(f"پروژه با شناسه {project_id} یافت نشد.", "error")
            return redirect(url_for("index"))
        
        doors = get_doors_for_project_db(project_id)
        
        # دریافت ستون‌های قابل نمایش از session
        session_key = f"visible_columns_{project_id}"
        visible_columns = session.get(session_key, [])
        
        # ایجاد یک نام فایل موقت برای خروجی HTML
        current_date = jdatetime.datetime.now().strftime("%Y%m%d")
        pdf_filename = f"project_{project_id}_{current_date}.pdf"
        
        # رندر قالب جدول برای PDF
        return render_template(
            "pdf_table_template.html",
            project=project,
            doors=doors,
            visible_columns=visible_columns,
            pdf_filename=pdf_filename
        )
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت export_table_to_pdf_html: {e}")
        traceback.print_exc()
        flash("خطایی در ایجاد خروجی PDF رخ داد.", "error")
        return redirect(url_for("project_treeview", project_id=project_id))


@app.route("/project/<int:project_id>/settings_columns", methods=["GET"])
def settings_columns(project_id):
    """صفحه تنظیمات ستون‌های نمایشی جدول"""
    try:
        # دریافت اطلاعات پروژه
        project = get_project_details_db(project_id)
        if not project:
            flash(f"پروژه با شناسه {project_id} یافت نشد.", "error")
            return redirect(url_for("index"))
        
        # دریافت لیست همه ستون‌های سفارشی
        all_columns = get_all_custom_columns()
        
        # دریافت ستون‌های قابل نمایش فعلی از session
        session_key = f"visible_columns_{project_id}"
        visible_columns = session.get(session_key, [])
        
        return render_template(
            "column_settings.html",
            project=project,
            all_columns=all_columns,
            visible_columns=visible_columns
        )
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت settings_columns: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه تنظیمات ستون‌ها رخ داد.", "error")
        return redirect(url_for("project_treeview", project_id=project_id))


@app.route("/project/<int:project_id>/add_column", methods=["POST"])
def add_column_route(project_id):
    """افزودن ستون جدید سفارشی"""
    display_name = request.form.get("display_name")
    column_key = request.form.get("column_key")
    
    if not display_name or not column_key:
        flash("لطفاً نام نمایشی و کلید ستون را وارد کنید.", "error")
        return redirect(url_for("settings_columns", project_id=project_id))
    
    # چک کردن اینکه آیا ستون با این کلید قبلاً وجود دارد
    existing_column_id = get_column_id_by_key(column_key)
    if existing_column_id:
        flash("ستونی با این کلید قبلاً وجود دارد.", "error")
        return redirect(url_for("settings_columns", project_id=project_id))
    
    # افزودن ستون جدید
    new_column_id = add_custom_column(column_key, display_name)
    if new_column_id:
        flash(f"ستون '{display_name}' با موفقیت اضافه شد.", "success")
    else:
        flash("خطا در افزودن ستون جدید.", "error")
    
    return redirect(url_for("settings_columns", project_id=project_id))


@app.route("/project/<int:project_id>/update_column_display", methods=["POST"])
def update_column_display(project_id):
    """به‌روزرسانی تنظیمات نمایش ستون‌ها"""
    try:
        visible_columns = request.form.getlist("visible_columns")
        
        # ذخیره در session
        session_key = f"visible_columns_{project_id}"
        session[session_key] = visible_columns
        
        flash("تنظیمات ستون‌های نمایشی با موفقیت ذخیره شد.", "success")
        return redirect(url_for("project_treeview", project_id=project_id))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت update_column_display: {e}")
        traceback.print_exc()
        flash("خطایی در ذخیره تنظیمات ستون‌ها رخ داد.", "error")
        return redirect(url_for("settings_columns", project_id=project_id))


@app.route("/project/<int:project_id>/get_columns_with_data", methods=["GET"])
def get_columns_with_data(project_id):
    """دریافت لیست ستون‌هایی که دارای داده هستند"""
    try:
        conn = None
        columns_with_data = []
        
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            # دریافت تمام ستون‌ها
            cursor.execute("SELECT id, column_name FROM custom_columns")
            columns = cursor.fetchall()
            
            # بررسی هر ستون برای مقادیر غیر خالی
            for column_id, column_key in columns:
                cursor.execute("""
                    SELECT COUNT(*) FROM door_custom_values dcv
                    JOIN doors d ON dcv.door_id = d.id
                    WHERE dcv.column_id = ? 
                    AND d.project_id = ?
                    AND dcv.value IS NOT NULL 
                    AND dcv.value != ''
                """, (column_id, project_id))
                
                count = cursor.fetchone()[0]
                if count > 0:
                    columns_with_data.append(column_key)
        
        except sqlite3.Error as e:
            print(f"خطا در بررسی ستون‌های دارای داده: {e}")
            return jsonify({"success": False, "error": str(e)})
        finally:
            if conn:
                conn.close()
                
        return jsonify({"success": True, "columns_with_data": columns_with_data})
    
    except Exception as e:
        print(f"خطای غیرمنتظره در get_columns_with_data: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


@app.route("/column/<int:column_id>/delete/<int:project_id>", methods=["GET"])
def delete_column_route(column_id, project_id):
    """حذف ستون سفارشی"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # حذف مقادیر مربوط به این ستون
        cursor.execute("DELETE FROM door_custom_values WHERE column_id = ?", (column_id,))
        
        # حذف ستون
        cursor.execute("DELETE FROM custom_columns WHERE id = ?", (column_id,))
        
        conn.commit()
        flash("ستون با موفقیت حذف شد.", "success")
    except Exception as e:
        print(f"خطا در حذف ستون: {e}")
        flash("خطا در حذف ستون.", "error")
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("settings_columns", project_id=project_id))


@app.route('/save_batch_edit_checkbox_state', methods=['POST'])
def save_batch_edit_checkbox_state():
    data = request.get_json()
    column = data.get('column')
    checked = data.get('checked')
    
    if not column:
        return jsonify({'success': False, 'error': 'Column name is required'})
    
    # Initialize the session key if it doesn't exist
    if 'batch_edit_checked_columns' not in session:
        session['batch_edit_checked_columns'] = {}
    
    # Update the session with the new checkbox state
    session['batch_edit_checked_columns'][column] = checked
    session.modified = True
    
    return jsonify({'success': True})


@app.route("/project/<int:project_id>/save_batch_edit_checkbox_state", methods=["POST"])
def save_batch_edit_checkbox_state_project(project_id):
    """ذخیره وضعیت چک‌باکس‌های ویرایش گروهی"""
    column_key = request.form.get("column_key")
    is_checked = request.form.get("is_checked", "0") == "1"
    door_id = request.form.get("door_id")  # اضافه کردن شناسه درب
    
    if not column_key:
        return jsonify({"success": False, "error": "کلید ستون ارسال نشده است"})
    
    try:
        # ۱. ذخیره وضعیت چک‌باکس‌های ویرایش گروهی برای هر درب
        batch_edit_checked_key = f"batch_edit_checked_{project_id}_{door_id}"
        checked_columns = session.get(batch_edit_checked_key, [])
        
        # به‌روزرسانی لیست ستون‌های تیک خورده برای این درب
        if is_checked and column_key not in checked_columns:
            checked_columns.append(column_key)
        elif not is_checked and column_key in checked_columns:
            checked_columns.remove(column_key)
        
        session[batch_edit_checked_key] = checked_columns
        session.modified = True
        
        # ۲. به‌روزرسانی وضعیت نمایش ستون‌ها
        session_key = f"visible_columns_{project_id}"
        visible_columns = session.get(session_key, [])
        
        # ستون‌های پایه که همیشه باید نمایش داده شوند
        basic_columns = ["location", "width", "height", "quantity", "direction"]
        
        # اگر ستون پایه نیست (جزو ستون‌های سفارشی است)
        if column_key not in basic_columns:
            # منطق معکوس: اگر چک‌باکس فعال شده، ستون را از لیست نمایش حذف کن
            if is_checked and column_key in visible_columns:
                visible_columns.remove(column_key)
            # منطق معکوس: اگر چک‌باکس غیرفعال شده، ستون را به لیست نمایش اضافه کن
            elif not is_checked and column_key not in visible_columns:
                visible_columns.append(column_key)
            
            session[session_key] = visible_columns
            session.modified = True
        
        print(f"DEBUG: درب {door_id} - ستون '{column_key}' به وضعیت {is_checked} تغییر یافت.")
        print(f"DEBUG: ستون‌های تیک خورده برای درب {door_id}: {checked_columns}")
        print(f"DEBUG: ستون‌های نمایشی: {visible_columns}")
        
        return jsonify({
            "success": True,
            "checked_columns": checked_columns,
            "visible_columns": visible_columns
        })
        
    except Exception as e:
        print(f"ERROR: خطا در ذخیره وضعیت چک‌باکس {column_key} برای درب {door_id}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


@app.route("/project/<int:project_id>/get_visible_columns", methods=["GET"])
def get_visible_columns(project_id):
    """دریافت لیست ستون‌های نمایشی"""
    try:
        session_key = f"visible_columns_{project_id}"
        visible_columns = session.get(session_key, [])
        
        # اگر لیست ستون‌های نمایشی خالی است، آن را با مقادیر پیش‌فرض پر کنیم
        if not visible_columns:
            initialize_visible_columns(project_id)
            visible_columns = session.get(session_key, [])
        
        # اضافه کردن ستون‌های پایه که همیشه باید نمایش داده شوند
        basic_columns = ["location", "width", "height", "quantity", "direction"]
        for col in basic_columns:
            if col not in visible_columns:
                visible_columns.append(col)
        
        print(f"DEBUG: ستون‌های نمایشی پروژه {project_id}: {visible_columns}")
        
        return jsonify({"success": True, "visible_columns": visible_columns})
    except Exception as e:
        print(f"ERROR: خطا در دریافت لیست ستون‌های نمایشی: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


# افزودن کد راه‌اندازی Flask در انتهای فایل
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
