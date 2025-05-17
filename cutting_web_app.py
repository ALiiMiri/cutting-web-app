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


def add_default_options_if_needed(cursor):
    """گزینه‌های پیش‌فرض برای ستون‌های دراپ‌داون پایه را اضافه می‌کند اگر قبلاً اضافه نشده باشند"""
    try:
        print("DEBUG: شروع بررسی و افزودن گزینه‌های پیش‌فرض برای ستون‌های دراپ‌داون...")
        
        # دیکشنری گزینه‌های پیش‌فرض برای ستون‌های دراپ‌داون پایه
        default_column_options_map = {
            "rang": ["سفید", "آنادایز", "مشکی", "شامپاینی", "طلایی", "نقره‌ای", "قهوه‌ای"],
            "noe_profile": ["فریم لس آلومینیومی", "فریم قدیمی", "داخل چوب دار", "فریم دار", "ساده"],
            "vaziat": ["همزمان با تولید چهارچوب", "تولید درب در آینده", "بدون درب", "درب دار", "نصب شده"],
            "lola": ["OTLAV", "HTH", "NHN", "سه تیکه", "مخفی", "متفرقه"],
            "ghofl": ["STV", "ایزدو", "NHN", "HTN", "یونی", "مگنتی", "بدون قفل"],
            "accessory": ["آلومینیوم آستانه فاق و زبانه", "آرامبند مرونی", "قفل برق سارو با فنر", "آینه", "دستگیره پشت درب"],
            "kolaft": ["دو طرفه", "سه طرفه", "یک طرفه", "بدون کلافت"],
            "dastgire": ["دو تیکه", "ایزدو", "گریف ورک", "گریف تو کار", "متفرقه"]
        }
        
        # برای هر ستون دراپ‌داون در نقشه
        for column_name, default_options in default_column_options_map.items():
            # پیدا کردن ستون در جدول custom_columns
            cursor.execute(
                "SELECT id, column_type FROM custom_columns WHERE column_name = ?",
                (column_name,)
            )
            column = cursor.fetchone()
            
            if not column:
                print(f"DEBUG: ستون '{column_name}' در دیتابیس یافت نشد.")
                continue
                
            column_id, column_type = column
            
            # اطمینان از اینکه ستون از نوع دراپ‌داون است
            if column_type != 'dropdown':
                print(f"DEBUG: ستون '{column_name}' از نوع دراپ‌داون نیست (نوع فعلی: {column_type}).")
                continue
            
            # بررسی اینکه آیا این ستون قبلاً گزینه‌ای دارد یا خیر
            cursor.execute(
                "SELECT COUNT(*) FROM custom_column_options WHERE column_id = ?",
                (column_id,)
            )
            option_count = cursor.fetchone()[0]
            
            if option_count > 0:
                print(f"DEBUG: ستون '{column_name}' قبلاً {option_count} گزینه دارد. نیازی به افزودن گزینه‌های پیش‌فرض نیست.")
                continue
            
            # اضافه کردن گزینه‌های پیش‌فرض
            print(f"DEBUG: افزودن {len(default_options)} گزینه پیش‌فرض برای ستون '{column_name}'...")
            for option_value in default_options:
                cursor.execute(
                    "INSERT INTO custom_column_options (column_id, option_value) VALUES (?, ?)",
                    (column_id, option_value)
                )
            
            print(f"DEBUG: گزینه‌های پیش‌فرض برای ستون '{column_name}' با موفقیت اضافه شدند.")
            
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در add_default_options_if_needed: {e}")
        traceback.print_exc()
        # خطا به تابع والد منتقل می‌شود تا آنجا مدیریت شود
        # raise e


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
                is_active INTEGER DEFAULT 1,
                column_type TEXT DEFAULT 'text' CHECK(column_type IN ('text', 'dropdown')) 
            )
        """
        )

        # اضافه کردن ستون column_type به جدول موجود اگر وجود نداشته باشد
        try:
            cursor.execute("SELECT column_type FROM custom_columns LIMIT 1")
        except sqlite3.OperationalError:
            print("DEBUG: اضافه کردن ستون 'column_type' به جدول 'custom_columns'...")
            # ابتدا ستون را بدون CHECK constraint اضافه می‌کنیم، سپس مقادیر پیش‌فرض را ست می‌کنیم
            # و در نهایت اگر SQLite از ALTER TABLE ... ADD CONSTRAINT پشتیبانی می‌کرد، آن را اضافه می‌کردیم.
            # چون SQLite محدودیت‌هایی در ALTER TABLE دارد، فعلاً فقط ستون با مقدار پیش‌فرض را اضافه می‌کنیم.
            # CHECK constraint در CREATE TABLE جدید اعمال خواهد شد.
            # برای جداول موجود، باید مطمئن شویم داده‌های نامعتبر وارد نمی‌شوند از طریق منطق برنامه.
            cursor.execute("ALTER TABLE custom_columns ADD COLUMN column_type TEXT DEFAULT 'text'")
            # برای ستون‌های پایه‌ای که از نوع دراپ‌داون هستند، نوعشان را آپدیت می‌کنیم
            base_dropdown_columns = ["rang", "noe_profile", "vaziat", "lola", "ghofl", "accessory", "kolaft", "dastgire"]
            for col_key in base_dropdown_columns:
                cursor.execute("UPDATE custom_columns SET column_type = 'dropdown' WHERE column_name = ? AND column_type = 'text'", (col_key,))
            print("DEBUG: ستون 'column_type' با مقدار پیش‌فرض 'text' اضافه شد و ستون‌های پایه دراپ‌داون به‌روز شدند.")

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
        ensure_base_columns_exist(cursor)
        
        # مطمئن می‌شویم که ستون‌های پایه دراپ‌داون به درستی نوعشان تنظیم شده باشد
        base_dropdown_columns = ["rang", "noe_profile", "vaziat", "lola", "ghofl", "accessory", "kolaft", "dastgire"]
        for col_key in base_dropdown_columns:
            cursor.execute("UPDATE custom_columns SET column_type = 'dropdown' WHERE column_name = ? AND column_type = 'text'", (col_key,))
        print("DEBUG: اطمینان از تنظیم صحیح نوع ستون‌های پایه دراپ‌داون پس از ensure_base_columns_exist")
        
        # افزودن گزینه‌های پیش‌فرض برای ستون‌های دراپ‌داون
        add_default_options_if_needed(cursor)

        conn.commit()
        print("DEBUG: تغییرات سایت به دیتابیس با موفقیت Commit شد.")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در initialize_database: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()


def ensure_base_columns_exist(cursor):
    """اطمینان از وجود ستون‌های پایه در دیتابیس با استفاده از cursor موجود"""
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
        try:
            # بررسی وجود ستون
            cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
            result = cursor.fetchone()
            if not result:
                print(f"DEBUG: افزودن ستون پایه '{column_key}' به دیتابیس")
                # تعیین نوع ستون بر اساس کلید
                col_type = 'dropdown'
                if column_key == 'tozihat': # توضیحات متنی است
                    col_type = 'text'
                
                cursor.execute(
                    "INSERT INTO custom_columns (column_name, display_name, is_active, column_type) VALUES (?, ?, 1, ?)",
                    (column_key, display_name, col_type)
                )
                print(f"DEBUG: ستون پایه '{column_key}' با موفقیت به دیتابیس اضافه شد.")
            else:
                print(f"DEBUG: ستون پایه '{column_key}' از قبل در دیتابیس وجود داشت.")
        except sqlite3.Error as e:
            print(f"ERROR در ensure_base_columns_exist برای ستون {column_key}: {e}")
            # در اینجا می‌توان خطا را به بالا pass داد تا initialize_database آن را مدیریت کند
            # raise e


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
            "SELECT id, column_name, display_name, is_active, column_type FROM custom_columns ORDER BY id"
        )
        columns = [
            {"id": row[0], "key": row[1], "display": row[2], "is_active": row[3], "type": row[4]}
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
            "SELECT id, column_name, display_name, column_type FROM custom_columns WHERE is_active = 1 ORDER BY id"
        )
        columns = [
            {"id": row[0], "key": row[1], "display": row[2], "type": row[3]}
            for row in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_active_custom_columns: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return columns


def get_active_custom_columns_values():
    """لیست کلیدهای ستون‌های سفارشی فعال را برمی‌گرداند"""
    active_columns = get_active_custom_columns()
    return [column["key"] for column in active_columns]


def add_custom_column(column_name, display_name, column_type='text'):
    """افزودن ستون سفارشی جدید"""
    conn = None
    new_id = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO custom_columns (column_name, display_name, is_active, column_type) VALUES (?, ?, 1, ?)",
            (column_name, display_name, column_type),
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
            "SELECT id, option_value FROM custom_column_options WHERE column_id = ? ORDER BY id",
            (column_id,),
        )
        options = [{"id": row[0], "value": row[1]} for row in cursor.fetchall()]
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
    
    # اطمینان از اینکه مقدار None به رشته خالی تبدیل شود
    if value is None:
        value = ""
    
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
    
    # بررسی پارامتر force_refresh برای تازه‌سازی کامل صفحه
    force_refresh = request.args.get("force_refresh", "0") == "1"
    
    # اگر force_refresh فعال است، به صفحه treeview هدایت می‌کنیم
    if force_refresh:
        print(f"DEBUG: ریدایرکت به صفحه treeview با force_refresh=1")
        timestamp = int(time.time())
        return redirect(url_for("project_treeview", project_id=project_id, force_refresh=1, refresh_columns=1, t=timestamp))
    
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


def refresh_project_visible_columns(project_id):
    print(f"DEBUG: شروع refresh_project_visible_columns برای پروژه ID: {project_id}")
    session_key = f"visible_columns_{project_id}"
    
    base_column_keys = ["location", "width", "height", "quantity", "direction"]
    final_visible_columns = list(base_column_keys)

    active_custom_columns_data = get_active_custom_columns() 

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for col_data in active_custom_columns_data:
            column_key = col_data["key"]
            column_id = col_data["id"]

            if column_key in base_column_keys:
                continue

            cursor.execute("""
                SELECT 1 FROM door_custom_values dcv
                JOIN doors d ON dcv.door_id = d.id
                WHERE d.project_id = ? AND dcv.column_id = ? AND dcv.value IS NOT NULL AND dcv.value != ''
                LIMIT 1
            """, (project_id, column_id))
            
            if cursor.fetchone(): 
                if column_key not in final_visible_columns:
                    final_visible_columns.append(column_key)
                print(f"DEBUG: ستون '{column_key}' در پروژه {project_id} داده دارد و به visible_columns اضافه شد/باقی ماند.")
            else:
                print(f"DEBUG: ستون '{column_key}' در پروژه {project_id} هیچ داده‌ای ندارد و در visible_columns نخواهد بود.")
        
        current_columns_in_session = session.get(session_key, [])
        # برای حفظ ترتیب ستون‌هایی که کاربر ممکن است دستی از طریق column_settings تنظیم کرده باشد،
        # می‌توانیم ترتیب final_visible_columns را بر اساس current_columns_in_session مرتب کنیم،
        # اما فقط برای ستون‌هایی که در final_visible_columns هستند.
        
        # یک راه ساده برای حفظ ترتیب نسبی ستون‌های سفارشی که از قبل در session بودند:
        ordered_final_visible_columns = list(base_column_keys) # پایه‌ها اول
        # ستون‌های سفارشی که هم در session قبلی بودند و هم در لیست جدید ما (چون داده دارند)
        for col_key_in_session in current_columns_in_session:
            if col_key_in_session in final_visible_columns and col_key_in_session not in ordered_final_visible_columns:
                ordered_final_visible_columns.append(col_key_in_session)
        # ستون‌های سفارشی جدیدی که داده دارند و در session قبلی نبودند
        for col_key_in_final in final_visible_columns:
            if col_key_in_final not in ordered_final_visible_columns:
                 ordered_final_visible_columns.append(col_key_in_final)


        if set(current_columns_in_session) != set(ordered_final_visible_columns) or \
           current_columns_in_session != ordered_final_visible_columns:
            session[session_key] = ordered_final_visible_columns
            session.modified = True
            print(f"DEBUG: visible_columns برای پروژه {project_id} به‌روز شد: {ordered_final_visible_columns}")
        else:
            print(f"DEBUG: visible_columns برای پروژه {project_id} تغییری نکرده است: {ordered_final_visible_columns}")
            
    except sqlite3.Error as e:
        print(f"ERROR در refresh_project_visible_columns (sqlite3.Error): {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"ERROR در refresh_project_visible_columns (Exception): {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    
    return session.get(session_key, [])


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

    session_key = f"visible_columns_{project_id}"
    # پارامتر force_refresh از URL می‌آید و نشان می‌دهد که آیا باید session به‌روز شود یا خیر
    force_refresh_session = request.args.get("force_refresh", "0") == "1" 

    # اگر force_refresh_session است، یا session برای این پروژه تنظیم نشده، آن را با تابع جدید به‌روز کن
    # تابع refresh_project_visible_columns (نسخه شما) خودش مقداردهی اولیه را هم انجام می‌دهد اگر session خالی باشد.
    if force_refresh_session or session_key not in session or not session[session_key]:
        print(f"DEBUG: فراخوانی refresh_project_visible_columns از داخل project_treeview (force_refresh_session={force_refresh_session} یا session خالی است)")
        refresh_project_visible_columns(project_id) # از نسخه موجود در کد شما استفاده می‌کند
    
    visible_columns = session.get(session_key, [])
    
    # حذف بخش مربوط به if refresh_columns: چون دیگر نیازی به آن نیست.
    # تابع refresh_project_visible_columns مسئول به‌روزرسانی لیست بر اساس داده‌های واقعی است.

    print(f"DEBUG: ستون‌های نمایشی نهایی برای رندر در project_treeview: {visible_columns}")
    
    # درب‌ها را از دیتابیس دریافت می‌کنیم 
    doors = get_doors_for_project_db(project_id)
    print(f"DEBUG: دریافت {len(doors)} درب برای پروژه {project_id}")
    
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
        # پارامترهای force_refresh و refresh_columns دیگر به تمپلیت پاس داده نمی‌شوند
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
    """خروجی اکسل فرمت‌شده از داده‌های پروژه با استفاده از ستون‌های قابل نمایش"""
    try:
        import pandas as pd
        import os
        import jdatetime
        from datetime import datetime
        from flask import make_response
        import re
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
        
        print(f"DEBUG: شروع صدور اکسل پیشرفته برای پروژه {project_id}")

        # دریافت اطلاعات پروژه
        project_info = get_project_details_db(project_id)
        if not project_info:
            print("DEBUG: پروژه یافت نشد")
            flash("پروژه مورد نظر یافت نشد.", "error")
            return redirect(url_for("index"))

        # دریافت داده‌های درب‌ها
        doors = get_doors_for_project_db(project_id)
        if not doors:
            print("DEBUG: هیچ دربی یافت نشد")
            flash("هیچ دربی برای این پروژه ثبت نشده است.", "warning")
            return redirect(url_for("project_treeview", project_id=project_id))
        
        print(f"DEBUG: {len(doors)} درب برای تبدیل به اکسل یافت شد")

        # دریافت ستون‌های قابل نمایش از session
        session_key = f"visible_columns_{project_id}"
        visible_columns = session.get(session_key, [])
        
        # اگر هیچ ستونی برای نمایش انتخاب نشده، ستون‌های پیش‌فرض را نمایش می‌دهیم
        if not visible_columns:
            # اجرای تابع مقداردهی اولیه
            initialize_visible_columns(project_id)
            # بازخوانی مجدد از سشن
            visible_columns = session.get(session_key, [])
        
        # اضافه کردن ستون‌های پایه که همیشه باید نمایش داده شوند
        basic_columns = ["location", "width", "height", "quantity", "direction"]
        for col in basic_columns:
            if col not in visible_columns:
                visible_columns.append(col)
        
        print(f"DEBUG: ستون‌های نمایشی برای اکسل: {visible_columns}")

        # ایجاد ترجمه فارسی برای نام ستون‌ها
        column_translations = {
            "id": "شماره ردیف",
            "location": "موقعیت",
            "width": "عرض CM",
            "height": "ارتفاع CM",
            "quantity": "تعداد درب",
            "direction": "جهت",
            "rang": "رنگ پروفیل آلومینیوم",
            "noe_profile": "نوع پروفیل",
            "vaziat": "وضعیت تولید درب",
            "lola": "نوع لولا",
            "ghofl": "نوع قفل",
            "accessory": "اکسسوری",
            "kolaft": "کلاف",
            "dastgire": "نوع دستگیره",
            "tozihat": "توضیحات"
        }
        
        # دریافت ستون‌های سفارشی فعال برای ترجمه نام‌ها
        custom_columns = get_all_custom_columns()
        for col in custom_columns:
            if col["key"] not in column_translations:
                column_translations[col["key"]] = col["display"]
        
        # ایجاد یک workbook جدید
        wb = Workbook()
        ws = wb.active
        ws.title = f"پروژه {project_id}"
        
        # استایل‌های مختلف برای سلول‌ها
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")  # آبی برای هدر
        alt_row_fill = PatternFill(start_color="E6F0FF", end_color="E6F0FF", fill_type="solid")  # آبی کمرنگ برای ردیف‌های زوج
        
        # تنظیم استایل برای مرزها
        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # نام مشتری و تاریخ در بالای اکسل - اصلاح بخش ادغام سلول‌ها
        today_jalali = jdatetime.datetime.now().strftime("%A, %d %B %Y")
        
        # باید ابتدا مقدار را به سلول اصلی بدهیم، سپس ادغام کنیم
        ws['A1'] = "تاریخ"
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws['A1'].font = Font(bold=True, size=12)
        ws['A1'].fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        ws.merge_cells('A1:C1')
        
        # ابتدا مقدار را به سلول اول می‌دهیم
        ws['D1'] = today_jalali
        ws['D1'].alignment = Alignment(horizontal='center', vertical='center')
        ws['D1'].fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        ws.merge_cells('D1:F1')
        
        # ابتدا مقدار را به سلول اول می‌دهیم
        ws['G1'] = "کد"
        ws['G1'].alignment = Alignment(horizontal='center', vertical='center')
        ws['G1'].font = Font(bold=True, size=12)
        ws['G1'].fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        ws.merge_cells('G1:I1')
        
        # ابتدا مقدار را به سلول اول می‌دهیم
        ws['J1'] = project_id
        ws['J1'].alignment = Alignment(horizontal='center', vertical='center')
        ws['J1'].font = Font(bold=True, size=14)
        ws.merge_cells('J1:K1')
        
        # فاصله بین جدول اصلی و هدر
        row_offset = 2
        
        # --- شروع ستون‌های نمایشی ---
        # ابتدا ستون شماره ردیف را به عنوان اولین ستون اضافه می‌کنیم
        visible_columns_with_translations = [{"key": "row_num", "display": "شماره ردیف"}]
        
        # اضافه کردن سایر ستون‌ها براساس لیست visible_columns
        for col_key in visible_columns:
            display_name = column_translations.get(col_key, col_key)
            visible_columns_with_translations.append({"key": col_key, "display": display_name})
        
        # درج هدر ستون‌ها
        for col_idx, col_info in enumerate(visible_columns_with_translations, 1):
            cell = ws.cell(row=row_offset+1, column=col_idx, value=col_info["display"])
            cell.font = Font(bold=True, color="FFFFFF", size=11)
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.fill = header_fill
            cell.border = thin_border
            # تنظیم عرض ستون
            ws.column_dimensions[get_column_letter(col_idx)].width = 15
        
        # درج داده‌های درب‌ها
        for row_idx, door in enumerate(doors, 1):
            # رنگ پس‌زمینه برای ردیف‌های زوج
            row_fill = alt_row_fill if row_idx % 2 == 0 else None
            
            # برای هر ستون قابل نمایش
            for col_idx, col_info in enumerate(visible_columns_with_translations, 1):
                col_key = col_info["key"]
                
                # مقدار ستون
                if col_key == "row_num":
                    value = row_idx
                else:
                    value = door.get(col_key, "")
                
                # تبدیل اعداد از string به عدد برای نمایش بهتر
                if col_key in ["width", "height"] and value:
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        pass
                elif col_key == "quantity" and value:
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        pass
                
                # درج سلول
                cell = ws.cell(row=row_offset+1+row_idx, column=col_idx, value=value)
                cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
                cell.border = thin_border
                
                # اعمال رنگ پس‌زمینه برای ردیف‌های زوج
                if row_fill:
                    cell.fill = row_fill
                
                # قالب‌بندی خاص برای سلول‌های خاص
                if col_key == "vaziat" and value and "درآینده" in str(value):
                    cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")  # قرمز کمرنگ
        
        # تنظیم مسیر فایل خروجی
        export_dir = "static/exports"
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        customer_name = project_info.get("customer_name", "unknown")
        
        # ایجاد نام فایل با حروف انگلیسی برای ذخیره سازی
        safe_filename = f"project_{project_id}_{timestamp}.xlsx"
        excel_path = os.path.join(export_dir, safe_filename)
        
        # ذخیره به فایل اکسل
        wb.save(excel_path)
        print(f"DEBUG: فایل اکسل با فرمت جدید با موفقیت ذخیره شد در: {excel_path}")
        
        # اصلاح شده: استفاده از نام فایل انگلیسی برای هدر Content-Disposition
        # حذف کاراکترهای فارسی و غیرمجاز از نام فایل
        display_filename = f"project_{project_id}_{timestamp}.xlsx"
        order_ref = project_info.get("order_ref", "")
        
        # اگر شماره سفارش موجود است، از آن استفاده کنیم (اگر شامل حروف لاتین است)
        if order_ref and any(c.isalnum() and ord(c) < 128 for c in order_ref):
            # فقط کاراکترهای مجاز را نگه داریم
            safe_order_ref = ''.join(c for c in order_ref if c.isalnum() or c in '-_')
            if safe_order_ref:
                display_filename = f"project_{project_id}_{safe_order_ref}.xlsx"
        
        print(f"DEBUG: نام فایل دانلودی: {display_filename}")
        
        # ارسال فایل به کاربر با هدرهای مناسب برای نمایش دیالوگ "ذخیره به عنوان"
        response = make_response(send_file(excel_path, as_attachment=True))
        response.headers["Content-Disposition"] = f"attachment; filename={display_filename}"
        return response
        
    except Exception as e:
        print(f"ERROR در صدور اکسل: {e}")
        traceback.print_exc()
        flash(f"خطا در ایجاد فایل اکسل: {str(e)}", "error")
        return redirect(url_for("project_treeview", project_id=project_id))


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

    # برای هر ستون سفارشی، گزینه‌های آن را دریافت کنیم
    for column in columns_info:
        column_key = column["key"]
        
        # تغییر منطق: یک ستون باید تیک بخورد اگر در لیست ستون‌های نمایشی نباشد
        is_visible = column_key in visible_columns
        is_checked = not is_visible  # منطق معکوس: اگر ستون نمایش داده نمی‌شود، باید تیک بخورد
        
        # لیست گزینه‌های ستون فعلی
        current_column_options_list = []
        
        # اگر ستون از نوع دراپ‌داون است، گزینه‌های آن را از دیتابیس دریافت کنیم
        if column.get("type") == "dropdown":
            db_options = get_custom_column_options(column["id"])
            if db_options:
                # فقط مقادیر (value) از آبجکت‌های گزینه را اضافه کن
                current_column_options_list = [opt['value'] for opt in db_options]
        
        column_options[column_key] = {
            "display": column["display"],
            "options": current_column_options_list,
            "type": column.get("type", "text"),  # نوع ستون را اضافه می‌کنیم
            "visible": column_key not in basic_columns,  # ستون‌های پایه همیشه باید نمایش داده شوند
            "checked": is_checked  # وضعیت چک‌باکس بر اساس عدم وجود در لیست نمایش
        }

    # حذف کد اضافه کردن دستی ستون "جهت"

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

    # بررسی اینکه کدام ستون‌ها باید به‌روزرسانی شوند
    columns_to_update = {}
    base_fields_to_update = {}
    
    print(f"DEBUG: تمام فرم‌ها: {request.form}")
    
    for key, value in request.form.items():
        # اگر یک checkbox برای ستون فعال بود و مقدار وارد شده بود
        if key.startswith("update_") and value == "on":
            field_key = key.replace("update_", "")
            field_value_key = f"value_{field_key}"
            
            if field_value_key in request.form:
                new_value = request.form.get(field_value_key)
                
                # بررسی اینکه آیا فیلد پایه است یا سفارشی
                if field_key in ["location", "width", "height", "quantity", "direction"]:
                    # اجازه به‌روزرسانی همه فیلدهای پایه را بده
                    base_fields_to_update[field_key] = new_value
                else:
                    # اجازه به‌روزرسانی همه فیلدهای سفارشی را بده
                    columns_to_update[field_key] = new_value

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
                        result = update_door_custom_value(door_id, column_id, new_value)
                        if result:
                            door_updated = True
                            
                            # ساختن پیام موفقیت
                            if current_value:
                                msg = f"ستون '{column_display}' از '{current_value}' به '{new_value}' تغییر کرد"
                            else:
                                msg = f"ستون '{column_display}' به '{new_value}' تنظیم شد"
                                
                            success_messages.append(f"درب {door_location}: {msg}")
                            print(f"DEBUG: درب {door_location}: {msg}")
                        else:
                            error_msg = f"به‌روزرسانی ستون '{column_display}' برای درب {door_location} ناموفق بود"
                            error_messages.append(error_msg)
                            print(f"ERROR: {error_msg}")
                    
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
        
        # به‌روزرسانی ستون‌های قابل مشاهده بر اساس داده‌های جدید
        if successful_updates > 0:
            refresh_project_visible_columns(project_id)

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

    # به‌روزرسانی ستون‌های قابل مشاهده بر اساس داده‌های جدید
    # این فراخوانی باید انجام شود تا اگر ستونی خالی شده، از لیست نمایش حذف گردد.
    refresh_project_visible_columns(project_id)

    # افزودن پارامتر زمانی برای جلوگیری از کش شدن صفحه
    timestamp = int(time.time())
    # اضافه کردن پارامتر force_refresh برای تازه‌سازی کامل صفحه
    return redirect(url_for("project_treeview", project_id=project_id, t=timestamp, force_refresh=1))


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
    """صفحه تنظیمات ستون‌های نمایشی جدول (برای سازگاری با قبل)"""
    # برای سازگاری با لینک‌های موجود در برنامه، به مسیر جدید ریدایرکت می‌کنیم
    return redirect(url_for("manage_custom_columns"))


@app.route("/project/<int:project_id>/add_column", methods=["POST"])
def add_column_route(project_id):
    """افزودن ستون جدید سفارشی (برای سازگاری با قبل)"""
    # دریافت اطلاعات فرم
    display_name = request.form.get("display_name")
    column_key = request.form.get("column_key")
    column_type = request.form.get("column_type")
    
    # ذخیره اطلاعات در session برای انتقال به روت جدید
    session['temp_column_data'] = {
        'display_name': display_name,
        'column_key': column_key,
        'column_type': column_type,
        'action': 'add_column'
    }
    
    # ریدایرکت به روت جدید
    return redirect(url_for("manage_custom_columns"))


@app.route("/project/<int:project_id>/update_column_display", methods=["POST"])
def update_column_display(project_id):
    """به‌روزرسانی تنظیمات نمایش ستون‌ها (برای سازگاری با قبل)"""
    # ریدایرکت به روت جدید
    return redirect(url_for("manage_custom_columns"))


@app.route("/column/<int:column_id>/delete/<int:project_id>", methods=["GET"])
def delete_column_route(column_id, project_id):
    """حذف ستون سفارشی (برای سازگاری با قبل)"""
    # ذخیره اطلاعات در session برای انتقال به روت جدید
    session['temp_column_data'] = {
        'column_id': column_id,
        'action': 'delete_column'
    }
    
    # ریدایرکت به روت جدید
    return redirect(url_for("manage_custom_columns"))


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
            # وقتی ستون تیک دارد، باید از لیست نمایش حذف شود
            if is_checked:
                if column_key in visible_columns:
                    visible_columns.remove(column_key)
                    print(f"DEBUG: ستون {column_key} تیک خورده و از لیست نمایشی حذف شد")
            # وقتی ستون تیک ندارد، باید به لیست نمایش اضافه شود
            else:
                if column_key not in visible_columns:
                    visible_columns.append(column_key)
                    print(f"DEBUG: ستون {column_key} تیک ندارد و به لیست نمایشی اضافه شد")
            
            session[session_key] = visible_columns
            session.modified = True
        
        print(f"DEBUG: درب {door_id} - ستون '{column_key}' به وضعیت تیک {is_checked} تغییر یافت.")
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


@app.route("/project/<int:project_id>/batch_remove_column_value", methods=["POST"])
def batch_remove_column_value_route(project_id):
    """
    این روت درخواست AJAX برای حذف مقادیر یک ستون خاص 
    برای درب‌های انتخاب شده را پردازش می‌کند.
    """
    print(f"DEBUG: ورود به روت batch_remove_column_value_route برای پروژه ID: {project_id}")

    if not request.is_json:
        print("ERROR: درخواست باید JSON باشد.")
        return jsonify({"success": False, "error": "درخواست باید با فرمت JSON باشد"}), 400

    data = request.get_json()
    door_ids_str_list = data.get('door_ids')  # انتظار داریم لیستی از IDها به صورت رشته باشد
    column_key_to_remove = data.get('column_key_to_remove')

    print(f"DEBUG: داده‌های دریافتی: door_ids={door_ids_str_list}, column_key={column_key_to_remove}")

    if not door_ids_str_list or not isinstance(door_ids_str_list, list) or not column_key_to_remove:
        error_msg = "ID درب‌ها (به صورت لیست) و کلید ستون مورد نیاز است."
        print(f"ERROR: {error_msg}")
        return jsonify({"success": False, "error": error_msg}), 400

    try:
        # تبدیل ID درب‌ها از رشته به عدد صحیح
        door_ids = [int(d_id) for d_id in door_ids_str_list]
    except ValueError:
        error_msg = "فرمت ID درب‌ها نامعتبر است. باید لیستی از اعداد صحیح باشد."
        print(f"ERROR: {error_msg}")
        return jsonify({"success": False, "error": error_msg}), 400

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # دریافت ID ستون از روی کلید (column_key)
        column_id = get_column_id_by_key(column_key_to_remove) 
        
        if not column_id:
            error_msg = f"ستون با کلید '{column_key_to_remove}' یافت نشد."
            print(f"ERROR: {error_msg}")
            return jsonify({"success": False, "error": error_msg}), 404

        print(f"DEBUG: ID ستون '{column_key_to_remove}' یافت شد: {column_id}")
        
        # تلاش برای دریافت نام نمایشی ستون
        display_name = None
        try:
            cursor.execute("SELECT display_name FROM custom_columns WHERE id = ?", (column_id,))
            result = cursor.fetchone()
            if result:
                display_name = result[0]  # نام نمایشی ستون
        except Exception as e:
            print(f"WARNING: خطا در دریافت نام نمایشی ستون: {e}")
        
        # اگر نام نمایشی دریافت نشد، از کلید ستون استفاده می‌کنیم
        column_identifier_for_message = display_name if display_name else column_key_to_remove

        deleted_count_total = 0
        for door_id in door_ids:
            # حذف مقدار از جدول door_custom_values
            print(f"DEBUG: تلاش برای حذف مقدار ستون {column_id} برای درب {door_id}")
            cursor.execute("""
                DELETE FROM door_custom_values 
                WHERE door_id = ? AND column_id = ?
            """, (door_id, column_id))
            
            if cursor.rowcount > 0:
                deleted_count_total += 1
                print(f"DEBUG: مقدار ستون {column_id} برای درب {door_id} حذف شد.")
            else:
                print(f"DEBUG: مقداری برای ستون {column_id} و درب {door_id} جهت حذف یافت نشد (ممکن است از قبل خالی بوده باشد).")
        
        conn.commit()
        print(f"DEBUG: عملیات حذف commit شد. تعداد کل رکوردهای حذف شده: {deleted_count_total}")
        
        # تهیه پیام مناسب بر اساس تعداد رکوردهای حذف شده
        if deleted_count_total == 0:
            message = f"مقداری برای ستون '{column_identifier_for_message}' جهت حذف یافت نشد (ممکن است از قبل خالی بوده یا تغییرات UI هنوز ذخیره نشده باشند)."
        else:
            message = f"{deleted_count_total} مقدار از ستون '{column_identifier_for_message}' با موفقیت از دیتابیس حذف شد."

        # اگر مقداری حذف شده یا حتی اگر حذف نشده (چون ممکن است آخرین مقدار بوده)، visible_columns را به‌روز کن
        # شرط if deleted_count_total > 0: می‌تواند برای بهینه‌سازی باشد، اما برای اطمینان بیشتر، همیشه فراخوانی می‌کنیم.
        refresh_project_visible_columns(project_id)

        return jsonify({"success": True, "message": message})

    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"ERROR - sqlite3.Error در batch_remove_column_value_route: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"خطای دیتابیس: {str(e)}"}), 500
    except Exception as e:
        print(f"ERROR - Exception عمومی در batch_remove_column_value_route: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"خطای عمومی سرور: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@app.route("/settings/custom_columns", methods=["GET", "POST"])
def manage_custom_columns():
    """صفحه مدیریت ستون‌های سفارشی"""
    try:
        # پردازش درخواست‌های POST یا داده موقت از session
        temp_data = session.pop('temp_column_data', None)
        
        if request.method == "POST" or temp_data:
            # تعیین منبع داده (POST یا temp_data)
            action = request.form.get("action") if request.method == "POST" else temp_data.get("action") if temp_data else None
            
            # افزودن ستون جدید
            if action == "add_column":
                if request.method == "POST":
                    display_name = request.form.get("display_name")
                    column_key = request.form.get("column_key")
                    column_type = request.form.get("column_type")
                else:
                    display_name = temp_data.get("display_name")
                    column_key = temp_data.get("column_key")
                    column_type = temp_data.get("column_type")
                
                if not display_name or not column_key or not column_type:
                    flash("لطفاً نام نمایشی، کلید ستون و نوع ستون را وارد کنید.", "error")
                    return redirect(url_for("manage_custom_columns"))
                
                if column_type not in ['text', 'dropdown']:
                    flash("نوع ستون انتخاب شده نامعتبر است. لطفاً 'متنی' یا 'دراپ‌داون' را انتخاب کنید.", "error")
                    return redirect(url_for("manage_custom_columns"))
                
                # چک کردن اینکه آیا ستون با این کلید قبلاً وجود دارد
                existing_column_id = get_column_id_by_key(column_key)
                if existing_column_id:
                    flash("ستونی با این کلید قبلاً وجود دارد.", "error")
                    return redirect(url_for("manage_custom_columns"))
                
                # افزودن ستون جدید
                new_column_id = add_custom_column(column_key, display_name, column_type)
                if new_column_id:
                    flash(f"ستون '{display_name}' با موفقیت اضافه شد.", "success")
                else:
                    flash("خطا در افزودن ستون جدید.", "error")
                return redirect(url_for("manage_custom_columns"))
            
            # حذف ستون
            elif action == "delete_column":
                if request.method == "POST":
                    column_id = request.form.get("column_id")
                else:
                    column_id = temp_data.get("column_id")
                
                if column_id:
                    column_id = int(column_id)
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
                return redirect(url_for("manage_custom_columns"))
            
            # تغییر وضعیت فعال/غیرفعال ستون
            elif action == "toggle_status":
                column_id_str = request.form.get("column_id")
                if column_id_str:
                    column_id = int(column_id_str)
                    # اگر کلید 'is_active' در request.form وجود داشت و مقدارش '1' بود، یعنی چک‌باکس تیک خورده است.
                    # در غیر این صورت (یعنی کلید 'is_active' اصلاً در فرم نبود چون تیک نخورده)، مقدار آن False خواهد بود.
                    is_active_bool = request.form.get("is_active") == "1"
                    
                    success = update_custom_column_status(column_id, is_active_bool)
                    if success:
                        status_text = "فعال" if is_active_bool else "غیرفعال"
                        flash(f"وضعیت ستون با موفقیت به {status_text} تغییر کرد.", "success")
                    else:
                        flash(f"خطا در تغییر وضعیت ستون با شناسه {column_id}.", "error")
                else:
                    flash("شناسه ستون برای تغییر وضعیت ارسال نشده است.", "error")
                return redirect(url_for("manage_custom_columns"))
        
        # پردازش درخواست GET (نمایش صفحه)
        all_columns = get_all_custom_columns()
        print(f"DEBUG: All columns from DB: {all_columns}")
        
        column_type_display_map = {
            'text': 'متنی',
            'dropdown': 'دراپ‌داون'
        }
        processed_columns = []
        for col in all_columns:
            col_copy = col.copy() 
            print(f"DEBUG: Processing column: {col_copy}")
            col_copy['type_display'] = column_type_display_map.get(col_copy.get('type'), col_copy.get('type', 'نامشخص'))
            if col_copy.get('type') == 'dropdown':
                col_copy['options'] = get_custom_column_options(col_copy['id'])
                print(f"DEBUG: Options for {col_copy['key']}: {col_copy['options']}")
            else:
                col_copy['options'] = [] # برای ستون‌های غیر دراپ‌داون، لیست گزینه‌ها خالی است
            processed_columns.append(col_copy)
        
        return render_template(
            "column_settings.html",
            all_columns=processed_columns
        )
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت manage_custom_columns: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه تنظیمات ستون‌ها رخ داد.", "error")
        return redirect(url_for("index"))

@app.route("/api/custom_columns/<int:column_id>/options", methods=["GET"])
def get_column_options_api(column_id):
    try:
        # تابع get_custom_column_options(column_id) از قبل موجود است 
        # و لیستی از رشته‌ها (مقادیر گزینه‌ها) را برمی‌گرداند.
        options = get_custom_column_options(column_id) 
        return jsonify({"success": True, "options": options})
    except Exception as e:
        print(f"Error fetching options for column {column_id}: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "خطا در دریافت گزینه‌ها"}), 500

@app.route("/api/custom_columns/<int:column_id>/options/add", methods=["POST"])
def add_column_option_api(column_id):
    """افزودن گزینه جدید به ستون دراپ‌داون"""
    try:
        # بررسی و دریافت داده‌های ارسالی
        data = request.get_json()
        if not data or 'option_value' not in data:
            return jsonify({"success": False, "error": "مقدار گزینه ارسال نشده است"}), 400
        
        option_value = data['option_value']
        if not option_value.strip():
            return jsonify({"success": False, "error": "مقدار گزینه نمی‌تواند خالی باشد"}), 400
        
        # بررسی نوع ستون قبل از افزودن گزینه
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT column_type FROM custom_columns WHERE id = ?", (column_id,))
        column = cursor.fetchone()
        conn.close()
        
        if not column:
            return jsonify({"success": False, "error": "ستون مورد نظر یافت نشد"}), 404
        
        if column[0] != 'dropdown':
            return jsonify({"success": False, "error": "فقط می‌توان به ستون‌های دراپ‌داون گزینه اضافه کرد"}), 400
            
        # افزودن گزینه با استفاده از تابع موجود
        success = add_option_to_column(column_id, option_value)
        
        if success:
            return jsonify({"success": True, "message": "گزینه با موفقیت اضافه شد"})
        else:
            return jsonify({"success": False, "error": "خطا در افزودن گزینه"}), 500
            
    except Exception as e:
        print(f"Error adding option to column {column_id}: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"خطای سرور: {str(e)}"}), 500

def get_custom_column_options(column_id):
    """گزینه‌های یک ستون سفارشی را برمی‌گرداند"""
    conn = None
    options = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, option_value FROM custom_column_options WHERE column_id = ? ORDER BY id",
            (column_id,),
        )
        options = [{"id": row[0], "value": row[1]} for row in cursor.fetchall()]
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

@app.route("/api/custom_columns/options/<int:option_id>/delete", methods=["POST"])
def delete_column_option_api(option_id):
    """حذف یک گزینه از ستون دراپ‌داون براساس شناسه گزینه"""
    try:
        # بررسی وجود گزینه قبل از حذف
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT column_id FROM custom_column_options WHERE id = ?", (option_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return jsonify({"success": False, "error": "گزینه مورد نظر یافت نشد"}), 404
            
        # حذف گزینه با استفاده از تابع موجود
        success = delete_column_option(option_id)
        
        if success:
            return jsonify({"success": True, "message": "گزینه با موفقیت حذف شد", "column_id": result[0]})
        else:
            return jsonify({"success": False, "error": "خطا در حذف گزینه"}), 500
            
    except Exception as e:
        print(f"Error deleting option {option_id}: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"خطای سرور: {str(e)}"}), 500

# افزودن کد راه‌اندازی Flask در انتهای فایل
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
