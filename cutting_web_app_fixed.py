# -*- coding: utf-8 -*-
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session
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
                # پر کردن مقادیر پیش‌فرض برای سایر ستون‌ها
                "rang": "",
                "noe_profile": "",
                "vaziat": "",
                "lola": "",
                "ghofl": "",
                "accessory": "",
                "kolaft": "",
                "dastgire": "",
                "tozihat": ""
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
                
            print(f"DEBUG: مقادیر سفارشی درب {door_id}: ghofl={door_data.get('ghofl')}, rang={door_data.get('rang')}")

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
    """تمام مقادیر ستون‌های سفارشی یک درب را برمی‌گرداند"""
    conn = None
    values = {}
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
            values[row[0]] = row[1]
            
        # اضافه کردن دستور دیباگ برای بررسی مقادیر بازیابی شده
        print(f"DEBUG: مقادیر سفارشی برای درب {door_id}: {values}")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در get_door_custom_values: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return values


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
    """تنظیم وضعیت اولیه ستون‌های نمایشی اگر قبلاً تنظیم نشده باشند"""
    session_key = f"visible_columns_{project_id}"
    if session_key not in session:
        # تنظیم ستون‌های پیش‌فرض برای نمایش (همه ستون‌ها به جز توضیحات)
        session[session_key] = ["rang", "noe_profile", "vaziat", "lola", "ghofl", "accessory", "kolaft", "dastgire"]
        print(f"DEBUG: تنظیم اولیه ستون‌های نمایشی برای پروژه {project_id}: {session[session_key]}")


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
    print(f"DEBUG: ستون‌های نمایشی از جلسه: {visible_columns}")
    
    # بررسی سریع مقادیر سفارشی
    for door in doors[:5]:  # فقط 5 درب اول را برای دیباگ بررسی می‌کنیم
        print(f"DEBUG: درب {door['id']} - رنگ: {door.get('rang', 'ندارد')}, نوع پروفیل: {door.get('noe_profile', 'ندارد')}")
    
    return render_template(
        "project_treeview.html", 
        project=project_info, 
        doors=doors, 
        refresh_param=refresh_param,
        visible_columns=visible_columns
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
    visible_columns = session.get(f"visible_columns_{project_id}", [])
    print(f"DEBUG: ستون‌های نمایشی برای پروژه {project_id}: {visible_columns}")

    # دریافت گزینه‌های ستون‌های قابل ویرایش
    columns_info = get_active_custom_columns()
    column_options = {}

    # گزینه‌های پیش‌فرض بر اساس cutting_tool.py
    default_options = {
        "rang": ["سفید", "آنادایز"],
        "noe_profile": [
            "فریم لس آلومینیومی",
            "فریم قدیمی",
            "فریم داخل چوب دار",
            "داخل چوب دار دو آلومینیوم درب",
        ],
        "vaziat": [
            "همزمان با تولید چهارچوب",
            "تولید درب در آینده",
            "بدون درب",
        ],
        "lola": ["OTLAV", "HTH", "NHN", "متفرقه"],
        "ghofl": ["STV", "ایزدو", "NHN", "HTN"],
        "accessory": [
            "آلومینیوم آستانه فاق و زبانه",
            "آرامبند مرونی",
            "قفل برق سارو با فنر",
            "آرامبند NHN",
        ],
        "kolaft": ["دو طرفه", "سه طرفه"],
        "dastgire": ["دو تیکه", "ایزدو", "گریف ورک", "متفرقه"],
    }

    # برای هر ستون، گزینه‌های آن را دریافت کنیم
    for column in columns_info:
        column_key = column["key"]
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
        
        # بررسی وضعیت نمایش ستون
        is_visible = column_key in visible_columns
        
        column_options[column_key] = {
            "display": column["display"],
            "options": options,
            "visible": is_visible  # وضعیت نمایش ستون
        }
        
    # افزودن پارامتر زمانی برای جلوگیری از کش شدن صفحه
    timestamp = int(time.time())

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
    door_ids = request.form.get("door_ids")
    if not door_ids:
        flash("هیچ دربی برای ویرایش انتخاب نشده است.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    door_ids = door_ids.split(",")

    # بررسی اینکه کدام ستون‌ها باید به‌روزرسانی شوند
    columns_to_update = {}
    for key, value in request.form.items():
        # اگر یک checkbox برای ستون فعال بود و مقدار وارد شده بود
        if key.startswith("update_") and value == "on":
            column_key = key.replace("update_", "")
            if f"value_{column_key}" in request.form:
                new_value = request.form.get(f"value_{column_key}")
                columns_to_update[column_key] = new_value

    if not columns_to_update:
        flash("هیچ فیلدی برای به‌روزرسانی انتخاب نشده است.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # اعمال تغییرات روی درب‌های انتخاب شده
    update_count = 0
    print(f"DEBUG: به‌روزرسانی {len(door_ids)} درب با ستون‌های: {columns_to_update}")
    
    for door_id in door_ids:
        try:
            door_id = int(door_id)
            
            # برای هر ستون، مقدار جدید را به‌روزرسانی کنیم
            for column_key, new_value in columns_to_update.items():
                # پیدا کردن ID ستون
                column_id = get_column_id_by_key(column_key)
                print(f"DEBUG: ستون '{column_key}' با ID={column_id}, مقدار جدید='{new_value}'")
                
                if column_id:
                    result = update_door_custom_value(door_id, column_id, new_value)
                    print(f"DEBUG: نتیجه به‌روزرسانی ستون '{column_key}' برای درب {door_id}: {result}")
                else:
                    print(f"ERROR: ستون با کلید '{column_key}' یافت نشد")

            update_count += 1

        except Exception as e:
            print(f"ERROR در به‌روزرسانی درب {door_id}: {e}")
            traceback.print_exc()

    if update_count > 0:
        flash(f"{update_count} درب با موفقیت به‌روزرسانی شد.", "success")
    else:
        flash("خطا در به‌روزرسانی درب‌ها.", "error")

    # افزودن پارامتر زمانی برای جلوگیری از کش شدن صفحه
    timestamp = int(time.time())
    return redirect(url_for("project_treeview", project_id=project_id, t=timestamp))


@app.route("/project/<int:project_id>/toggle_column_display", methods=["POST"])
def toggle_column_display(project_id):
    """تغییر وضعیت نمایش ستون در جلسه کاربر"""
    column_key = request.form.get("column_key")
    is_visible = request.form.get("is_visible") == "1"
    
    print(f"DEBUG: تغییر وضعیت نمایش ستون '{column_key}' به {is_visible}")
    
    # ذخیره وضعیت نمایش ستون در جلسه کاربر
    session_key = f"visible_columns_{project_id}"
    visible_columns = session.get(session_key, [])
    
    if is_visible and column_key not in visible_columns:
        visible_columns.append(column_key)
        print(f"DEBUG: ستون '{column_key}' به لیست نمایش اضافه شد")
    elif not is_visible and column_key in visible_columns:
        visible_columns.remove(column_key)
        print(f"DEBUG: ستون '{column_key}' از لیست نمایش حذف شد")
    
    session[session_key] = visible_columns
    print(f"DEBUG: لیست ستون‌های نمایشی به‌روز شد: {visible_columns}")
    
    return jsonify({"success": True})


@app.route("/settings/columns/<int:project_id>")
def settings_columns(project_id):
    """صفحه تنظیمات ستون‌ها"""
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("پروژه مورد نظر یافت نشد.", "error")
        return redirect(url_for("index"))

    # دریافت اطلاعات همه ستون‌ها (پایه و سفارشی)
    all_columns = get_all_custom_columns()

    return render_template(
        "settings_columns.html", project=project_info, columns=all_columns
    )


@app.route("/settings/add_custom_column/<int:project_id>", methods=["POST"])
def add_custom_column_route(project_id):
    """افزودن ستون سفارشی جدید"""
    display_name = request.form.get("display_name")
    if not display_name:
        flash("نام نمایشی ستون نمی‌تواند خالی باشد.", "error")
        return redirect(url_for("settings_columns", project_id=project_id))

    # تولید نام کلید داخلی براساس نام نمایشی
    internal_key = "".join(c if c.isalnum() else "_" for c in display_name.lower())

    # بررسی یکتا بودن کلید
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT column_name FROM custom_columns")
    existing_keys = [row[0] for row in cursor.fetchall()]
    conn.close()

    # اگر کلید تکراری بود، پسوند اضافه کنیم
    base_key = internal_key
    counter = 1
    while internal_key in existing_keys:
        internal_key = f"{base_key}_{counter}"
        counter += 1

    # افزودن ستون جدید
    try:
        new_id = add_custom_column(internal_key, display_name)
        if new_id:
            flash(f"ستون '{display_name}' با موفقیت اضافه شد.", "success")
        else:
            flash("خطا در افزودن ستون جدید.", "error")
    except Exception as e:
        flash(f"خطا در افزودن ستون جدید: {e}", "error")

    return redirect(url_for("settings_columns", project_id=project_id))


@app.route("/settings/toggle_column/<int:column_id>", methods=["POST"])
def toggle_column_status(column_id):
    """تغییر وضعیت فعال/غیرفعال ستون"""
    is_active = request.form.get("is_active", "0") == "1"

    try:
        success = update_custom_column_status(column_id, is_active)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "خطا در به‌روزرسانی وضعیت ستون"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/settings/update_column_name/<int:column_id>", methods=["POST"])
def update_column_name(column_id):
    """به‌روزرسانی نام نمایشی ستون"""
    display_name = request.form.get("display_name")
    project_id = request.args.get("project_id")

    if not display_name:
        flash("نام نمایشی ستون نمی‌تواند خالی باشد.", "error")
        return redirect(url_for("settings_columns", project_id=project_id))

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE custom_columns SET display_name = ? WHERE id = ?",
            (display_name, column_id),
        )
        conn.commit()
        conn.close()
        flash(f"نام ستون با موفقیت به '{display_name}' تغییر یافت.", "success")
    except Exception as e:
        flash(f"خطا در به‌روزرسانی نام ستون: {e}", "error")

    return redirect(url_for("settings_columns", project_id=project_id))


@app.route("/settings/delete_column/<int:column_id>")
def delete_column_route(column_id):
    """حذف ستون سفارشی"""
    project_id = request.args.get("redirect_to")

    try:
        # ابتدا باید بررسی کنیم که آیا ستون از ستون‌های پایه حیاتی نیست
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT column_name FROM custom_columns WHERE id = ?", (column_id,)
        )
        column_data = cursor.fetchone()

        if column_data:
            column_key = column_data[0]
            # برخی ستون‌های پایه که نباید حذف شوند
            critical_base_keys = ["rang", "noe_profile", "vaziat", "tozihat"]

            if column_key in critical_base_keys:
                flash(
                    f"ستون '{column_key}' یک ستون پایه است و نمی‌تواند حذف شود.", "error"
                )
                return redirect(url_for("settings_columns", project_id=project_id))

            # حذف ستون
            cursor.execute("DELETE FROM custom_columns WHERE id = ?", (column_id,))
            conn.commit()
            conn.close()

            flash("ستون با موفقیت حذف شد.", "success")
        else:
            flash("ستون مورد نظر یافت نشد.", "error")
    except Exception as e:
        flash(f"خطا در حذف ستون: {e}", "error")


@app.route("/project/<int:project_id>/update", methods=["POST"])
def update_project(project_id):
    """به‌روزرسانی اطلاعات یک پروژه"""
    print(f"DEBUG: ورود به route بروزرسانی پروژه با ID: {project_id}")
    
    customer_name = request.form.get("customer_name", "")
    order_ref = request.form.get("order_ref", "")
    date_shamsi = request.form.get("date_shamsi", "")
    
    print(f"DEBUG: اطلاعات دریافتی از فرم - مشتری: {customer_name}, سفارش: {order_ref}, تاریخ: {date_shamsi}")
    
    success = update_project_db(project_id, customer_name, order_ref, date_shamsi)
    
    if success:
        flash("اطلاعات پروژه با موفقیت به‌روزرسانی شد", "success")
    else:
        flash("خطا در به‌روزرسانی اطلاعات پروژه", "error")
    
    return redirect(url_for("view_project", project_id=project_id))


@app.route("/project/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    """حذف یک پروژه از دیتابیس"""
    print(f"DEBUG: ورود به route حذف پروژه با ID: {project_id}")
    
    success = delete_project_db(project_id)
    
    if success:
        flash("پروژه با موفقیت حذف شد", "success")
    else:
        flash("خطا در حذف پروژه", "error")
    
    return redirect(url_for("index"))


def fix_persian_text(text):
    """تبدیل متن فارسی برای نمایش صحیح در PDF"""
    if not text:
        return ""
    reshaped_text = arabic_reshaper.reshape(str(text))
    return get_display(reshaped_text)


@app.route("/project/<int:project_id>/export_pdf", methods=["GET"])
def export_table_to_pdf_web(project_id):
    """خروجی PDF از داده‌های پروژه"""
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("پروژه مورد نظر یافت نشد.", "error")
        return redirect(url_for("index"))

    doors = get_doors_for_project_db(project_id)
    if not doors:
        flash("هیچ دربی برای این پروژه ثبت نشده است.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # دریافت ستون‌های فعال
    visible_columns = session.get(f"visible_columns_{project_id}", [])
    
    try:
        # اطمینان از وجود پوشه خروجی
        os.makedirs("static/exports", exist_ok=True)
        
        # ایجاد PDF جدید (افقی)
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # افزودن فونت فارسی
        pdf.add_font('Vazir', '', './static/Vazir.ttf', uni=True)
        pdf.set_font('Vazir', '', 10)
        
        # عنوان
        title_txt = fix_persian_text("لیست سفارشات درب")
        pdf.cell(0, 10, txt=title_txt, border=0, ln=1, align="C")
        
        # اطلاعات مشتری
        pdf.set_font('Vazir', '', 9)
        pdf.ln(2)
        
        # اطلاعات مشتری
        customer_name = project_info.get("customer_name", "")
        order_ref = project_info.get("order_ref", "")
        date_shamsi = project_info.get("date_shamsi", "")
        
        # جدول اطلاعات مشتری
        info_cell_width = 45
        info_cell_height = 7
        pdf.set_fill_color(240, 248, 255)  # رنگ پس‌زمینه آبی روشن
        
        # ردیف اول
        pdf.set_font('Vazir', '', 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(25, info_cell_height, fix_persian_text("نام مشتری:"), 1, 0, "R", 1)
        pdf.set_font('Vazir', '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(info_cell_width, info_cell_height, fix_persian_text(customer_name), 1, 0, "R", 1)
        
        pdf.set_font('Vazir', '', 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(25, info_cell_height, fix_persian_text("شماره سفارش:"), 1, 0, "R", 1)
        pdf.set_font('Vazir', '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(info_cell_width, info_cell_height, fix_persian_text(order_ref), 1, 1, "R", 1)
        
        # ردیف دوم
        pdf.set_font('Vazir', '', 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(25, info_cell_height, fix_persian_text("تاریخ:"), 1, 0, "R", 1)
        pdf.set_font('Vazir', '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(info_cell_width, info_cell_height, fix_persian_text(date_shamsi), 1, 0, "R", 1)
        
        # فضای خالی برای تکمیل ردیف
        remaining_width = pdf.w - pdf.get_x() - pdf.r_margin
        pdf.cell(remaining_width, info_cell_height, "", 1, 1, "C", 1)
        
        pdf.ln(5)
        pdf.set_font('Vazir', '', 10)
        pdf.set_text_color(0, 0, 0)
        
        # تعیین ستون‌های جدول اصلی
        headers = ["مکان نصب", "عرض", "ارتفاع", "تعداد", "جهت"]
        keys_for_columns = ["location", "width", "height", "quantity", "direction"]
        
        # افزودن ستون‌های سفارشی فعال
        for col_key in visible_columns:
            if col_key in ["rang", "noe_profile", "vaziat", "lola", "ghofl", "accessory", "kolaft", "dastgire"]:
                # یافتن نام نمایشی
                for col in get_active_custom_columns():
                    if col['key'] == col_key:
                        headers.append(col['display'])
                        keys_for_columns.append(col_key)
                        break
        
        # افزودن ستون توضیحات در انتها (اگر فعال باشد)
        if "tozihat" in visible_columns:
            headers.append("توضیحات")
            keys_for_columns.append("tozihat")
        
        # محاسبه عرض ستون‌ها
        page_width = pdf.w - 2 * pdf.l_margin
        col_widths = []
        total_width = 0
        
        # تعیین عرض هر ستون براساس طول عنوان و محتوا
        for i, header in enumerate(headers):
            key = keys_for_columns[i]
            # محاسبه حداکثر طول برای عنوان و محتوا
    except Exception as e:
        flash(f"خطا در ایجاد فایل PDF: {str(e)}", "error")
        return redirect(url_for("view_project", project_id=project_id))

@app.route("/project/<int:project_id>/export_pdf_html", methods=["GET"])
def export_table_to_pdf_html(project_id):
    """خروجی HTML از داده‌های پروژه به‌صورت PDF"""
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("پروژه مورد نظر یافت نشد.", "error")
        return redirect(url_for("index"))

    doors = get_doors_for_project_db(project_id)
    if not doors:
        flash("هیچ دربی برای این پروژه ثبت نشده است.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # دریافت ستون‌های فعال
    visible_columns = session.get(f"visible_columns_{project_id}", [])
    
    # آماده‌سازی لیست هدرهای ستون‌ها و کلیدهای مربوط به آن‌ها
    custom_headers = []
    custom_keys = []
    
    # افزودن ستون‌های سفارشی فعال
    for col_key in visible_columns:
        if col_key in ["rang", "noe_profile", "vaziat", "lola", "ghofl", "accessory", "kolaft", "dastgire"]:
            # یافتن نام نمایشی
            for col in get_active_custom_columns():
                if col['key'] == col_key:
                    custom_headers.append(col['display'])
                    custom_keys.append(col_key)
                    break
    
    # آیا ستون توضیحات نمایش داده شود
    show_notes = "tozihat" in visible_columns
    
    # تاریخ امروز
    today_date = jdatetime.datetime.now().strftime("%Y/%m/%d")
    
    # مسیر فونت وزیر
    font_path = os.path.abspath("static/Vazir.ttf")
    
    # ایجاد یک کپی از قالب اصلی اما با تغییرات CSS بهینه‌سازی شده
    optimized_template = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>جدول درب‌ها - {{ project.customer_name }}</title>
    <style>
        @font-face {
            font-family: 'Vazir';
            src: url('file:///{{ font_path }}') format('truetype');
            font-weight: normal;
            font-style: normal;
        }
        
        body {
            font-family: 'Vazir', sans-serif;
            margin: 20px;
            color: #333;
        }
        
        .header {
            text-align: center;
            margin-bottom: 25px;
        }
        
        .customer-info {
            display: table;
            width: 100%;
            margin-bottom: 20px;
            background-color: #f8f9fa;
            border-radius: 5px;
            padding: 10px;
        }
        
        .info-row {
            display: table-row;
        }
        
        .info-cell {
            display: table-cell;
            padding: 5px 10px;
        }
        
        .info-label {
            font-weight: bold;
            color: #555;
        }
        
        table.doors-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            table-layout: fixed;
        }
        
        table.doors-table th {
            background-color: #3498db;
            color: white;
            font-weight: bold;
            text-align: center;
            padding: 10px;
            border: 1px solid #ddd;
        }
        
        table.doors-table td {
            padding: 8px;
            border: 1px solid #ddd;
            text-align: center;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        table.doors-table tr:nth-child(even) {
            background-color: #f2f2f2;
        }
        
        /* رنگ‌های سفارشی */
        .yellow {
            background-color: #fff9c4 !important;
        }
        
        .lightgreen {
            background-color: #c8e6c9 !important;
        }
        
        .lightblue {
            background-color: #bbdefb !important;
        }
        
        .footer {
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>لیست درب‌های پروژه {{ project.customer_name }}</h1>
    </div>
    
    <div class="customer-info">
        <div class="info-row">
            <div class="info-cell"><span class="info-label">نام مشتری:</span> {{ project.customer_name }}</div>
            <div class="info-cell"><span class="info-label">شماره تماس:</span> {{ project.phone_number }}</div>
            <div class="info-cell"><span class="info-label">تاریخ:</span> {{ today_date }}</div>
        </div>
        <div class="info-row">
            <div class="info-cell"><span class="info-label">آدرس:</span> {{ project.address }}</div>
        </div>
    </div>
    
    <table class="doors-table">
        <thead>
            <tr>
                <th>ردیف</th>
                <th>کد</th>
                <th>عرض</th>
                <th>ارتفاع</th>
                {% for header in custom_headers %}
                <th>{{ header }}</th>
                {% endfor %}
                {% if show_notes %}
                <th>توضیحات</th>
                {% endif %}
            </tr>
        </thead>
        <tbody>
            {% for door in doors %}
            <tr>
                <td>{{ loop.index }}</td>
                <td>{{ door.code }}</td>
                <td>{{ door.width }}</td>
                <td>{{ door.height }}</td>
                {% for key in custom_keys %}
                <td>{{ door[key] }}</td>
                {% endfor %}
                {% if show_notes %}
                <td>{{ door.notes }}</td>
                {% endif %}
            </tr>
            {% endfor %}
        </tbody>
    </table>
    
    <div class="footer">
        <p>تولید شده توسط نرم‌افزار مدیریت برش</p>
    </div>
</body>
</html>"""

    return render_template_string(
        optimized_template,
        project=project_info,
        doors=doors,
        custom_headers=custom_headers,
        custom_keys=custom_keys,
        show_notes=show_notes,
        today_date=today_date,
        font_path=font_path
    )

if __name__ == "__main__":
    print("INFO: Starting Flask application...")
    app.run(debug=True, host="0.0.0.0", port=8080)
