import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, render_template_string, get_flashed_messages
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
from math import ceil
import json
from collections import defaultdict
from config import Config
from database import (
    get_db_connection,
    check_table_exists,
    get_all_projects,
    add_project_db,
    get_project_details_db,
    get_doors_for_project_db,
    add_door_db,
    get_all_custom_columns,
    get_active_custom_columns,
    get_active_custom_columns_values,
    add_custom_column,
    update_custom_column_status,
    get_column_id_by_key,
    get_custom_column_options,
    add_option_to_column,
    delete_column_option,
    update_door_custom_value,
    get_door_custom_values,
    update_project_db,
    delete_project_db,
    check_column_can_hide_internal,
    ensure_default_custom_columns,
    update_custom_column_option,
    get_non_empty_custom_columns_for_project,
    get_price_settings_db,
    save_quote_db,
    get_all_saved_quotes_db,
    delete_quote_db,
    delete_multiple_quotes_db
)

# --- تنظیمات اولیه ---
DB_NAME = Config.DB_NAME


# --- تابع کمکی برای بررسی وجود جدول ---





# --- Flask App Setup ---
app = Flask(__name__, template_folder='templates')
app.secret_key = Config.SECRET_KEY

# --- مقداردهی اولیه دیتابیس ---
# initialize_database() # Removed this call

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
    
    # ایجاد یک اتصال دیتابیس برای تمام عملیات
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        for door_data in pending_doors:
            try:
                # اضافه کردن یک درب جدید و دریافت ID آن
                cursor.execute(
                    """
                    INSERT INTO doors (project_id, location, width, height, quantity, direction, row_color_tag) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        door_data.get("location"),
                        door_data.get("width"),
                        door_data.get("height"),
                        door_data.get("quantity"),
                        door_data.get("direction"),
                        door_data.get("row_color_tag", "white"),
                    ),
                )
                door_id = cursor.lastrowid
                print(
                    f"DEBUG: درب جدید با ID {door_id} برای پروژه ID {project_id} ذخیره شد."
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
                                update_door_custom_value(cursor, door_id, column_id, value)
            except sqlite3.Error as e:
                error_count += 1
                print(f"!!!!!! خطا در ذخیره درب: {e}")
                traceback.print_exc()
        
        # commit تمام تغییرات در پایان
        conn.commit()
        print(f"DEBUG: تمام تغییرات برای پروژه {project_id} commit شد.")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در finish_adding_doors: {e}")
        traceback.print_exc()
        if conn:
            conn.rollback()
        error_count = len(pending_doors)
        saved_count = 0
    finally:
        if conn:
            conn.close()

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
    print(f"DEBUG: Starting refresh_project_visible_columns for project ID: {project_id}")
    session_key = f"visible_columns_{project_id}"
    
    base_column_keys = ["location", "width", "height", "quantity", "direction"]
    final_visible_columns = list(base_column_keys)

    # Use the logic from database.py to get non-empty columns
    non_empty_cols = get_non_empty_custom_columns_for_project(project_id, base_column_keys)
    
    for col_key in non_empty_cols:
         if col_key not in final_visible_columns:
             final_visible_columns.append(col_key)
             print(f"DEBUG: Column '{col_key}' added to visible_columns.")
    
    current_columns_in_session = session.get(session_key, [])
    # Preserve relative order
    ordered_final_visible_columns = list(base_column_keys) 
    # Custom columns that were already in session and still have data
    for col_key_in_session in current_columns_in_session:
        if col_key_in_session in final_visible_columns and col_key_in_session not in ordered_final_visible_columns:
            ordered_final_visible_columns.append(col_key_in_session)
    # New custom columns that have data
    for col_key_in_final in final_visible_columns:
        if col_key_in_final not in ordered_final_visible_columns:
                ordered_final_visible_columns.append(col_key_in_final)

    if set(current_columns_in_session) != set(ordered_final_visible_columns) or \
       current_columns_in_session != ordered_final_visible_columns:
        session[session_key] = ordered_final_visible_columns
        session.modified = True
        print(f"DEBUG: visible_columns for project {project_id} updated: {ordered_final_visible_columns}")
    else:
        print(f"DEBUG: visible_columns for project {project_id} unchanged: {ordered_final_visible_columns}")
    
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
    
    print("-" * 50)
    print(f"DEBUG (treeview): Preparing to render for project_id: {project_id}")
    print(f"DEBUG (treeview): Visible columns from session: {visible_columns}")
    print(f"DEBUG (treeview): Doors list from DB: {doors}")
    print(f"DEBUG (treeview): Active custom columns list: {active_custom_columns}")
    print("-" * 50)
    
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
                        update_door_custom_value(cursor, door_id, column_id, new_value)
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
        # حذف print برای جلوگیری از خطای encoding در Windows
        # print(f"DEBUG: All columns from DB: {all_columns}")
        
        column_type_display_map = {
            'text': 'متنی',
            'dropdown': 'دراپ‌داون'
        }
        processed_columns = []
        for col in all_columns:
            col_copy = col.copy() 
            # حذف print برای جلوگیری از خطای encoding در Windows
            # print(f"DEBUG: Processing column: {col_copy}")
            col_copy['type_display'] = column_type_display_map.get(col_copy.get('type'), col_copy.get('type', 'نامشخص'))
            if col_copy.get('type') == 'dropdown':
                col_copy['options'] = get_custom_column_options(col_copy['id'])
                # حذف print برای جلوگیری از خطای encoding در Windows
                # print(f"DEBUG: Options for {col_copy['key']}: {col_copy['options']}")
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



@app.route("/api/custom_columns/options/<int:option_id>/edit", methods=["POST"])
def edit_column_option_api(option_id):
    """ویرایش متن یک گزینه از ستون دراپ‌داون براساس شناسه گزینه"""
    try:
        # بررسی و دریافت داده‌های ارسالی
        data = request.get_json()
        if not data or 'new_value' not in data:
            return jsonify({"success": False, "error": "مقدار جدید گزینه ارسال نشده است"}), 400
        
        new_value = data['new_value']
        if not new_value.strip():
            return jsonify({"success": False, "error": "مقدار گزینه نمی‌تواند خالی باشد"}), 400
        
        # بررسی وجود گزینه قبل از ویرایش
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT column_id FROM custom_column_options WHERE id = ?", (option_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({"success": False, "error": "گزینه مورد نظر یافت نشد"}), 404
        
        column_id = result[0]
        conn.close()
        
        # ویرایش گزینه با استفاده از تابع موجود
        success = update_custom_column_option(option_id, new_value)
        
        if success:
            return jsonify({
                "success": True, 
                "message": "گزینه با موفقیت ویرایش شد", 
                "updated_option": {"id": option_id, "value": new_value},
                "column_id": column_id
            })
        else:
            return jsonify({"success": False, "error": "خطا در ویرایش گزینه"}), 500
            
    except Exception as e:
        print(f"Error editing option {option_id}: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"خطای سرور: {str(e)}"}), 500


# --- Price Calculator Constants ---
قیمت_انواع_پروفیل = {
    "فریم لس قدیمی": 1.7,
    "فریم لس قالب جدید": 1.9,
    "توچوب دار": 1.5,
    "دور آلومینیوم": 1.5,
}

قیمت_ملزومات_نصب = {
    "لاستیک": 98000,
    "بست نصب": 600000,
}

قیمت_اجرت_ماشین_کاری = {
    "چهارچوب فریم لس": 20000000,
    "داخل چوب": 40000000,
    "دور آلومینیوم": 50000000,
}

قیمت_رنگ_آلومینیوم_جدول = {
    "خام": 3450000,
    "آنادایز": 3950000,
    "رنگی": 3750000,
}

قیمت_جنس_درب = {
    "ام دی اف": 0,
    "پلای وود": 19000000,
}

قیمت_پایه_درب_خام_بر_اساس_ارتفاع = {
    "تا 260 سانتی متر": 121000000,
    "261 تا 320 سانتی متر": 133100000,
    "321 تا 360 سانتی متر": 145200000,
    "بیش از 360 سانتی متر": 145200000,
}

قیمت_خدمات_رنگ = {
    ("رنگ نهایی", "خارجی"): 27000000,
    ("رنگ نهایی", "ایرانی"): 20000000,
    ("زیر سازی", "خارجی"): 22000000,
    ("زیر سازی", "ایرانی"): 15000000,
    ("کد رنگ", "خارجی"): 33000000,
    ("کد رنگ", "ایرانی"): 25000000,
}

قیمت_یراق_آلات = {
    "لولا": 18000000,
    "قفل": 14000000,
    "سیلندر": 6800000,
}

def get_قیمت_پایه_درب_خام(height_cm):
    if height_cm <= 260:
        return قیمت_پایه_درب_خام_بر_اساس_ارتفاع["تا 260 سانتی متر"]
    elif height_cm <= 320:
        return قیمت_پایه_درب_خام_بر_اساس_ارتفاع["261 تا 320 سانتی متر"]
    elif height_cm <= 360:
        return قیمت_پایه_درب_خام_بر_اساس_ارتفاع["321 تا 360 سانتی متر"]
    else:
        return قیمت_پایه_درب_خام_بر_اساس_ارتفاع["بیش از 360 سانتی متر"]

def format_price(price):
    """Format price with thousand separators"""
    return "{:,}".format(int(price))

@app.route("/price_calculator", methods=["GET", "POST"])
def price_calculator():
    """صفحه محاسبه قیمت درب"""
    try:
        # دریافت مقادیر از دیتابیس (مربوط به تنظیمات قیمت، نه ت فرم کاربر)
        # دریافت مقادیر از دیتابیس (مربوط به تنظیمات قیمت، نه ت فرم کاربر)
        db_prices = get_price_settings_db()

        # مقادیر پیش‌فرض قیمت‌ها از تنظیمات
        prices = {
            "فریم_لس_قدیمی": db_prices.get("فریم_لس_قدیمی", 0),
            "فریم_لس_قالب_جدید": db_prices.get("فریم_لس_قالب_جدید", 0),
            "توچوب_دار": db_prices.get("توچوب_دار", 0),
            "دور_آلومینیوم": db_prices.get("دور_آلومینیوم", 0),
            "لاستیک": db_prices.get("لاستیک", 0),
            "بست_نصب": db_prices.get("بست_نصب", 0),
            "چهارچوب_فریم_لس": db_prices.get("چهارچوب_فریم_لس", 0),
            "داخل_چوب": db_prices.get("داخل_چوب", 0),
            "دور_آلومینیوم_ماشین": db_prices.get("دور_آلومینیوم_ماشین", 0),
            "خام": db_prices.get("خام", 0), # قیمت رنگ آلومینیوم
            "آنادایز": db_prices.get("آنادایز", 0), # قیمت رنگ آلومینیوم
            "رنگی": db_prices.get("رنگی", 0), # قیمت رنگ آلومینیوم (جدیداً سفید شده)
            "سفید": db_prices.get("سفید", db_prices.get("رنگی",0)), # برای سازگاری اگر "رنگی" هنوز در دیتابیس باشد
            "پلای_وود": db_prices.get("پلای_وود", 0),
            "تا_260": db_prices.get("تا_260", 0),
            "261_تا_320": db_prices.get("261_تا_320", 0),
            "321_تا_360": db_prices.get("321_تا_360", 0),
            "بیش_از_360": db_prices.get("بیش_از_360", 0),
            "رنگ_نهایی_خارجی": db_prices.get("رنگ_نهایی_خارجی", 0),
            "رنگ_نهایی_ایرانی": db_prices.get("رنگ_نهایی_ایرانی", 0),
            "زیر_سازی_خارجی": db_prices.get("زیر_سازی_خارجی", 0),
            "زیر_سازی_ایرانی": db_prices.get("زیر_سازی_ایرانی", 0),
            "کد_رنگ_خارجی": db_prices.get("کد_رنگ_خارجی", 0),
            "کد_رنگ_ایرانی": db_prices.get("کد_رنگ_ایرانی", 0),
            "لولا": db_prices.get("لولا", 0),
            "قفل": db_prices.get("قفل", 0),
            "سیلندر": db_prices.get("سیلندر", 0)
        }
        # print("DEBUG: Initialized 'prices':", prices) # Removed

        today_shamsi = jdatetime.date.today().strftime("%Y/%m/%d")

        # مقادیر پیش‌فرض برای فیلدهای اصلی فرم (برای GET request)
        initial_form_values = {
            "عرض_درب": "110",
            "ارتفاع_درب": "280",
            "نوع_پروفیل_فریم_لس": "فریم لس قالب جدید",
            "رنگ_آلومینیوم": "سفید", # قبلا "رنگی" بود، طبق درخواست کاربر به سفید و آنادایز محدود شد
            "جنس_درب": "ام دی اف",
            "شرایط_رنگ": "بدون رنگ",
            "رند_رنگ": "بدون رنگ",
            "نام_مشتری": "", # اطمینان از وجود کلید برای نام مشتری
            "موبایل_مشتری": "", # اطمینان از وجود کلید برای موبایل مشتری
            "تاریخ_سفارش": today_shamsi # اضافه کردن تاریخ شمسی فعلی
        }

        # گزینه‌های دراپ‌داون
        dropdown_options = {
            "نوع_پروفیل_فریم_لس": ["فریم لس قدیمی", "فریم لس قالب جدید", "توچوب دار", "دور آلومینیوم"],
            "رنگ_آلومینیوم": ["آنادایز", "سفید"], # تغییر یافته طبق درخواست کاربر
            "جنس_درب": ["ام دی اف", "پلای وود"],
            "شرایط_رنگ": ["بدون رنگ", "رنگ نهایی", "زیر سازی", "کد رنگ"],
            "رند_رنگ": ["بدون رنگ", "خارجی", "ایرانی"]
        }

        # ساختار و مقادیر پیش‌فرض اولیه برای بخش انتخاب مولفه‌ها (برای GET request)
        initial_selections_config = {
            "درب_خام": (False, 0),
            "درب_با_رنگ_کامل": (True, 30),
            "فریم": (True, 30),
            "یراق_کامل": (True, 10),
            "رنگ_کاری": (False, 0)
        }

        if request.method == "POST":
            results = None
            current_selections_for_template = {}
            component_markup_rules = {} # برای محاسبات داخلی (درصد به صورت اعشاری)

            try:
                # دریافت مقادیر اصلی فرم
                width_str = request.form.get("عرض_درب", initial_form_values["عرض_درب"])
                height_str = request.form.get("ارتفاع_درب", initial_form_values["ارتفاع_درب"])
                width = float(width_str)
                height = float(height_str)
                profile_type_from_form = request.form.get("نوع_پروفیل_فریم_لس", initial_form_values["نوع_پروفیل_فریم_لس"])
                # Normalize profile_type_from_form to match the keys in the prices dictionary
                profile_type = profile_type_from_form.strip().replace(" ", "_")
                # print(f"DEBUG: profile_type_from_form: '{profile_type_from_form}'") # Removed
                # print(f"DEBUG: Normalized profile_type for prices lookup: '{profile_type}'") # Removed

                aluminum_color_from_form = request.form.get("رنگ_آلومینیوم", initial_form_values["رنگ_آلومینیوم"])
                # Normalize aluminum_color_from_form if necessary, though it seems to be working.
                # For consistency, let's normalize it as well if it might contain spaces.
                aluminum_color = aluminum_color_from_form.strip() # Assuming keys in prices don't have underscores for colors
                # print(f"DEBUG: aluminum_color_from_form: '{aluminum_color_from_form}'") # Removed
                # print(f"DEBUG: Normalized aluminum_color for prices lookup: '{aluminum_color}'") # Removed

                door_type = request.form.get("جنس_درب", initial_form_values["جنس_درب"])
                paint_type = request.form.get("شرایط_رنگ", initial_form_values["شرایط_رنگ"])
                paint_origin = request.form.get("رند_رنگ", initial_form_values["رند_رنگ"])

                # دریافت اطلاعات مشتری از فرم
                customer_name = request.form.get("نام_مشتری", "")
                customer_mobile = request.form.get("موبایل_مشتری", "")
                shamsi_order_date_from_form = request.form.get("تاریخ_سفارش", today_shamsi) # خواندن تاریخ از فرم

                # پردازش انتخاب‌ها و درصدها از فرم برای نمایش و محاسبه
                for key, (default_is_selected, default_percentage_value) in initial_selections_config.items():
                    is_selected_from_form = request.form.get(f"checkbox_{key}") == "on"
                    percentage_str_from_form = request.form.get(f"percentage_{key}")

                    template_percentage_to_use = 0.0 # برای نمایش در فرم (0-100)
                    calc_contrib_decimal_to_use = 0.0 # برای محاسبات (0.0-1.0)

                    if is_selected_from_form:
                        # اگر کاربر درصدی وارد کرده، آن را استفاده کن، در غیر این صورت از پیش‌فرض اولیه برای حالت انتخاب شده استفاده کن
                        fallback_percentage = float(default_percentage_value) # پیش‌فرض اولیه برای این مولفه
                        if percentage_str_from_form:
                            try:
                                parsed_percentage = float(percentage_str_from_form)
                                if 0 <= parsed_percentage <= 100:
                                    template_percentage_to_use = parsed_percentage
                                    calc_contrib_decimal_to_use = parsed_percentage / 100.0
                                else:
                                    flash(f"درصد برای '{key}' ({parsed_percentage}) خارج از محدوده بود. مقدار پیش‌فرض ({fallback_percentage}%) استفاده شد.", "warning")
                                    template_percentage_to_use = fallback_percentage
                                    calc_contrib_decimal_to_use = fallback_percentage / 100.0
                            except ValueError:
                                flash(f"مقدار درصد نامعتبر ('{percentage_str_from_form}') برای '{key}'. مقدار پیش‌فرض ({fallback_percentage}%) استفاده شد.", "warning")
                                template_percentage_to_use = fallback_percentage
                                calc_contrib_decimal_to_use = fallback_percentage / 100.0
                        else: # تیک خورده ولی فیلد درصد خالی است
                            flash(f"درصدی برای '{key}' وارد نشده. مقدار پیش‌فرض ({fallback_percentage}%) استفاده شد.", "warning")
                            template_percentage_to_use = fallback_percentage
                            calc_contrib_decimal_to_use = fallback_percentage / 100.0
                    # else: # اگر تیک نخورده، درصد نمایشی و محاسباتی صفر است
                        # template_percentage_to_use و calc_contrib_decimal_to_use به طور پیش‌فرض صفر هستند
                    
                    current_selections_for_template[key] = (is_selected_from_form, template_percentage_to_use)
                    component_markup_rules[key] = (is_selected_from_form, calc_contrib_decimal_to_use)

                # --- شروع محاسبات قیمت (منطق قبلی با استفاده از component_markup_rules) ---
                base_price = 0
                if height <= 260: base_price = prices["تا_260"]
                elif height <= 320: base_price = prices["261_تا_320"]
                elif height <= 360: base_price = prices["321_تا_360"]
                else: base_price = prices["بیش_از_360"]
                
                profile_weight_price = prices.get(profile_type, 0) # قیمت بر اساس وزن پروفیل انتخابی
                
                # هزینه فریم بر اساس طول و قیمت وزنی پروفیل
                # فرض می‌کنیم `prices[profile_type]` قیمت هر واحد وزن (مثلا کیلوگرم) است
                # و باید منطق محاسبه وزن کل پروفیل را داشته باشیم یا قیمت‌ها بر اساس متر باشند.
                # در اینجا فرض بر این است که قیمت‌های وارد شده در تنظیمات، قیمت نهایی به ازای هر متر یا واحد مناسب است.
                # اگر prices[profile_type] قیمت بر کیلوگرم است، باید وزن کل را محاسبه کنیم.
                # با توجه به نام فیلدها در price_calculator_settings.html مثل "فریم لس قدیمی:" (بدون واحد وزن)
                # به نظر میرسد قیمت‌های پروفیل در settings قیمت بر متر یا یک واحد دیگر است.
                # در اینجا، قیمت پروفیل را مستقیماً از prices[profile_type] میخوانیم (که در settings با وزن مشخص شده)
                # این بخش نیاز به شفاف‌سازی دارد که آیا قیمت‌های پروفیل در settings قیمت واحد وزن است یا قیمت واحد طول.
                # فعلا فرض می‌کنیم prices.get(profile_type,0) قیمت نهایی به ازای متر است.
                # اگر این قیمت وزنی است، باید وزن متر پروفیل را هم داشته باشیم.
                # با توجه به اینکه در settings کاربر وزن وارد می‌کند، prices[profile_type] باید وزن باشد.
                # پس باید قیمت واحد آلومینیوم را هم داشته باشیم.
                # این قسمت از محاسبات ممکن است نیاز به بازنگری بر اساس معنای دقیق مقادیر settings داشته باشد.
                # فعلا فرض می‌کنیم `profile_weight_price` وزن بر متر است و باید در قیمت واحد آلومینیوم ضرب شود.
                # اما در کد قبلی مستقیم ضرب میشد. پس قیمت واحد آلومینیوم در این وزن‌ها لحاظ شده.
                
                # قیمت واحد آلومینیوم بر اساس رنگ انتخابی
                aluminum_unit_price = prices.get(aluminum_color, prices.get("سفید", 0)) # اگر "آنادایز" یا "سفید" نبود، پیش‌فرض "سفید"

                total_profile_length_meters_raw = (width + (2 * height)) / 100.0 # برای اطمینان از تقسیم اعشاری
                total_profile_length_meters = ceil(total_profile_length_meters_raw) # گرد کردن به بالا
                
                # print(f"DEBUG: total_profile_length_meters_raw: {total_profile_length_meters_raw}") # Removed
                # print(f"DEBUG: total_profile_length_meters (ceil-ed): {total_profile_length_meters}") # Removed
                # print(f"DEBUG: profile_type (used for lookup): {profile_type}") # Removed
                # print(f"DEBUG: prices.get(profile_type, 0) (profile weight from prices): {prices.get(profile_type, 0)}") # Removed
                # print(f"DEBUG: aluminum_color (used for lookup): {aluminum_color}") # Removed
                # print(f"DEBUG: aluminum_unit_price (from prices): {aluminum_unit_price}") # Removed
                
                # هزینه فریم = طول کل پروفیل * وزن بر متر پروفیل انتخابی * قیمت واحد آلومینیوم بر اساس رنگ
                frame_cost = total_profile_length_meters * prices.get(profile_type, 0) * aluminum_unit_price

                rubber_cost = total_profile_length_meters * prices["لاستیک"]
                # installation_cost = prices["بست_نصب"] # Original line to be replaced
                half_bracket_unit_price = prices["بست_نصب"]          # قیمت یک «بست نصف»
                half_bracket_per_side   = ceil(height / 60)          # هر ۶۰ cm یک بست نصف
                total_half_bracket      = half_bracket_per_side * 2  # چون دو طرف در نصب می‌شود
                installation_cost       = total_half_bracket * half_bracket_unit_price
                
                machining_cost_key_map = {
                    "فریم_لس_قدیمی": "چهارچوب_فریم_لس", # کلید مقصد در prices
                    "فریم_لس_قالب_جدید": "چهارچوب_فریم_لس",
                    "توچوب_دار": "داخل_چوب",
                    "دور_آلومینیوم": "دور_آلومینیوم_ماشین" 
                }
                # profile_type از قبل نرمال شده است (مثلا "فریم_لس_قالب_جدید")
                machining_key_to_lookup_in_prices = machining_cost_key_map.get(profile_type, "چهارچوب_فریم_لس")
                machining_cost = prices.get(machining_key_to_lookup_in_prices, 0)

                paint_service_cost = 0
                if paint_type != "بدون رنگ" and paint_origin != "بدون رنگ":
                    paint_key = f"{paint_type}_{paint_origin}"
                    unit_paint_service_cost_per_sqm = prices.get(paint_key.replace(" ", "_"), 0) # e.g. رنگ_نهایی_خارجی
                    
                    # Calculate paint area (paint_area_sqm) based on door dimensions
                    # width و height اینجا باید مقادیر عددی سانتی متر باشند
                    if width > 10 and height > 6:  # برای جلوگیری از مساحت منفی
                        paint_area_sqm = ((width - 10.0) * (height - 6.0) * 2.0) / 10000.0
                    else:
                        paint_area_sqm = 0.0  # یا مقدار پیش فرض دیگر یا ایجاد خطا
                    
                    # Calculate total paint service cost
                    paint_service_cost = paint_area_sqm * unit_paint_service_cost_per_sqm
                
                # محاسبه تعداد لولا بر اساس ارتفاع درب
                height_meters = height / 100.0  # تبدیل ارتفاع به متر
                
                if height_meters <= 0:  # مدیریت ارتفاع نامعتبر
                    num_hinges = 2  # یا مقدار پیش فرض دیگر یا ایجاد خطا
                    # flash("ارتفاع درب نامعتبر است، تعداد لولا پیش‌فرض در نظر گرفته شد.", "warning")
                elif height_meters <= 1.8:
                    num_hinges = 2
                elif height_meters <= 2.1:
                    num_hinges = 3
                elif height_meters <= 2.4:
                    num_hinges = 3
                elif height_meters <= 2.7:
                    num_hinges = 4
                elif height_meters <= 3.2:
                    num_hinges = 5
                elif height_meters <= 3.6:
                    num_hinges = 6
                else:
                    # برای ارتفاع‌های بیشتر از ۳.۶ متر، یا یک مقدار ثابت در نظر بگیرید،
                    # یا بر اساس یک الگو ادامه دهید، یا خطا ایجاد کنید.
                    # فعلا فرض می کنیم برای ارتفاع بیشتر هم ۶ لولا کافی است یا باید بررسی شود.
                    num_hinges = 6  # یا مثلاً: num_hinges = 6 + math.ceil((height_meters - 3.6) / 0.5) اگر یک الگوی افزایشی دارید
                    # flash(f"ارتفاع درب ({height_meters} متر) بسیار زیاد است، تعداد لولا ({num_hinges}) بر اساس حداکثر پیش‌بینی شده در نظر گرفته شد.", "warning")
                
                # محاسبه هزینه کل یراق آلات
                # num_hinges از مرحله بالا محاسبه شده است
                price_per_hinge = prices.get("لولا", 0.0)  # قیمت هر عدد لولا از تنظیمات
                price_per_lock = prices.get("قفل", 0.0)   # قیمت پایه قفل از تنظیمات
                price_per_cylinder = prices.get("سیلندر", 0.0)  # قیمت پایه سیلندر از تنظیمات
                
                total_hinge_cost = num_hinges * price_per_hinge
                hardware_cost = total_hinge_cost + price_per_lock + price_per_cylinder
                door_material_cost = prices["پلای_وود"] if door_type == "پلای وود" else 0
                
                results = {}
                # سهم درب خام (شامل هزینه جنس درب)
                هزینه_پایه_درب_خام = base_price + door_material_cost
                is_selected_درب_خام, contrib_decimal_درب_خام = component_markup_rules["درب_خام"]
                if is_selected_درب_خام:
                    results["D14_هزینه_درب_خام_یک_درب"] = هزینه_پایه_درب_خام * (1 + contrib_decimal_درب_خام)
                else:
                    results["D14_هزینه_درب_خام_یک_درب"] = 0
                
                # سهم درب با رنگ کامل (شامل هزینه جنس درب و رنگ کاری)
                هزینه_پایه_درب_با_رنگ_کامل = base_price + door_material_cost + paint_service_cost
                is_selected_درب_با_رنگ, contrib_decimal_درب_با_رنگ = component_markup_rules["درب_با_رنگ_کامل"]
                if is_selected_درب_با_رنگ:
                    results["C11_درب_با_رنگ_کامل"] = هزینه_پایه_درب_با_رنگ_کامل * (1 + contrib_decimal_درب_با_رنگ)
                else:
                    results["C11_درب_با_رنگ_کامل"] = 0
                
                # سهم فریم
                # print(f"DEBUG: frame_cost: {frame_cost}") # Removed
                # print(f"DEBUG: rubber_cost: {rubber_cost}") # Removed
                # print(f"DEBUG: installation_cost: {installation_cost}") # Removed
                # print(f"DEBUG: machining_cost: {machining_cost}") # Removed
                هزینه_پایه_فریم = frame_cost + rubber_cost + installation_cost + machining_cost
                is_selected_فریم, contrib_decimal_فریم = component_markup_rules["فریم"]
                if is_selected_فریم:
                    results["D11_فریم"] = هزینه_پایه_فریم * (1 + contrib_decimal_فریم)
                else:
                    results["D11_فریم"] = 0
                
                # گرد کردن سهم نهایی فریم
                if results.get("D11_فریم") is not None and results["D11_فریم"] > 0: # فقط اگر مقدار مثبت و معناداری دارد
                    results["D11_فریم"] = ceil(results["D11_فریم"] / 1000000.0) * 1000000
                elif results.get("D11_فریم") is None: # اگر کلید اصلا وجود نداشت یا None بود
                     results["D11_فریم"] = 0 # یا مقدار مناسب دیگر
                # اگر صفر بود، صفر باقی می ماند

                # سهم یراق کامل
                هزینه_پایه_یراق_کامل = hardware_cost
                is_selected_یراق, contrib_decimal_یراق = component_markup_rules["یراق_کامل"]
                if is_selected_یراق:
                    results["E11_یراق_کامل"] = هزینه_پایه_یراق_کامل * (1 + contrib_decimal_یراق)
                else:
                    results["E11_یراق_کامل"] = 0
                
                # سهم رنگ کاری (فقط هزینه خدمات رنگ)
                هزینه_پایه_رنگ_کاری = paint_service_cost
                is_selected_رنگ_کاری, contrib_decimal_رنگ_کاری = component_markup_rules["رنگ_کاری"]
                if is_selected_رنگ_کاری:
                    results["رنگ_کاری_contrib"] = هزینه_پایه_رنگ_کاری * (1 + contrib_decimal_رنگ_کاری)
                else:
                    results["رنگ_کاری_contrib"] = 0
                
                # مقادیر نمایشی که حذف شده بودند، برای سازگاری و جلوگیری از خطا None یا 0 میگذاریم
                results["G14_هزینه_فریم_کل"] = frame_cost + rubber_cost + installation_cost + machining_cost # این در محاسبات اصلی استفاده نمیشود، فقط برای نمایش اگر لازم شد
                results["N14_هزینه_کل_رنگ_کاری_یک_درب"] = paint_service_cost # اینم

                results["total_cost"] = sum(filter(None, [
                    results.get("D14_هزینه_درب_خام_یک_درب"),
                    results.get("C11_درب_با_رنگ_کامل"),
                    results.get("D11_فریم"),
                    results.get("E11_یراق_کامل"),
                    results.get("رنگ_کاری_contrib")
                ]))
                # گرد کردن قیمت نهایی کل
                if results.get("total_cost") is not None and results["total_cost"] > 0: # فقط اگر مقدار مثبت و معناداری دارد
                    results["total_cost"] = ceil(results["total_cost"] / 1000000.0) * 1000000
                elif results.get("total_cost") is None:
                    results["total_cost"] = 0
                # اگر صفر بود، صفر باقی می ماند
                # --- پایان محاسبات ---

                # Check if this is an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    # Collect flash messages for AJAX response
                    flashed_messages = []
                    for category, message in get_flashed_messages(with_categories=True):
                        flashed_messages.append({"category": category, "message": message})
                    
                    return jsonify(success=True, results=results, flash_messages=flashed_messages)

                return render_template(
                    "price_calculator.html",
                    results=results,
                    default_values=request.form, # برای حفظ مقادیر فرم اصلی
                    dropdown_options=dropdown_options,
                    selections=current_selections_for_template # برای حفظ وضعیت چک‌باکس‌ها و درصدها
                )
                
            except ValueError as ve: # خطای تبدیل نوع مثل float()
                flash(f"خطا در مقادیر ورودی: {str(ve)}. لطفاً مقادیر عددی صحیح وارد کنید.", "error")
                traceback.print_exc()
                # در صورت خطا، فرم را با مقادیر وارد شده توسط کاربر نمایش بده
                preserved_selections_on_error = {}
                for key, (default_sel, default_perc) in initial_selections_config.items():
                    is_selected = request.form.get(f"checkbox_{key}") == "on"
                    percentage_str = request.form.get(f"percentage_{key}")
                    perc_to_display = 0.0
                    if is_selected:
                        fallback_percentage = float(default_perc)
                        if percentage_str:
                            try: perc_to_display = float(percentage_str)
                            except: perc_to_display = fallback_percentage
                            if not (0 <= perc_to_display <= 100): perc_to_display = fallback_percentage
                        else: perc_to_display = fallback_percentage
                    preserved_selections_on_error[key] = (is_selected, perc_to_display)
                
                # Check if this is an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    flashed_messages = []
                    for category, message in get_flashed_messages(with_categories=True):
                        flashed_messages.append({"category": category, "message": message})
                    return jsonify(success=False, error=str(ve), default_values=request.form.to_dict(), 
                                 selections=preserved_selections_on_error, flash_messages=flashed_messages), 400

                return render_template(
                    "price_calculator.html", results=None, default_values=request.form,
                    dropdown_options=dropdown_options, selections=preserved_selections_on_error
                )
            except Exception as e:
                flash(f"خطا در محاسبه قیمت: {str(e)}", "error")
                traceback.print_exc()
                # تلاش برای حفظ حالت فرم در صورت خطای عمومی
                preserved_selections_on_error = {}
                for key, (default_sel, default_perc) in initial_selections_config.items():
                    is_selected = request.form.get(f"checkbox_{key}") == "on"
                    percentage_str = request.form.get(f"percentage_{key}")
                    perc_to_display = 0.0
                    if is_selected:
                        fallback_percentage = float(default_perc)
                        if percentage_str:
                            try: perc_to_display = float(percentage_str)
                            except: perc_to_display = fallback_percentage
                            if not (0 <= perc_to_display <= 100): perc_to_display = fallback_percentage
                        else: perc_to_display = fallback_percentage
                    preserved_selections_on_error[key] = (is_selected, perc_to_display)

                # Check if this is an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    flashed_messages = []
                    for category, message in get_flashed_messages(with_categories=True):
                        flashed_messages.append({"category": category, "message": message})
                    return jsonify(success=False, error=str(e), flash_messages=flashed_messages), 500

                return render_template(
                    "price_calculator.html", results=None, default_values=request.form,
                    dropdown_options=dropdown_options, selections=preserved_selections_on_error
                )
        
        # GET request
        # مقادیر پیش‌فرض اولیه برای نمایش در اولین بارگذاری صفحه
        # اطمینان از اینکه selections به درستی برای قالب آماده شده (شامل مقادیر پیش‌فرض درصد)
        prepared_initial_selections = {
            key: (val[0], val[1] if val[1] is not None else 0) 
            for key, val in initial_selections_config.items()
        }

        # مقادیر پیش‌فرض فرم را ابتدا با مقادیر اولیه پر کن
        current_default_values = initial_form_values.copy() 

        # بررسی اطلاعات مشتری فلش شده از روت save_quote
        preserved_customer_data = session.pop('preserved_customer_info_data', None) # NEW way: Get from session

        if preserved_customer_data: # NEW way: Check if data exists
            if isinstance(preserved_customer_data, dict): # اطمینان از اینکه دیکشنری است
                current_default_values['نام_مشتری'] = preserved_customer_data.get('customer_name', initial_form_values.get('نام_مشتری', ''))
                current_default_values['موبایل_مشتری'] = preserved_customer_data.get('customer_mobile', initial_form_values.get('موبایل_مشتری', ''))
                # سایر فیلدهای ورودی (عرض، ارتفاع و ...) باید از initial_form_values باشند تا برای یک محاسبه جدید ریست شوند
                # فقط نام و موبایل حفظ می شوند.

        return render_template(
            "price_calculator.html",
            results=None, # برای سفارش جدید یا پس از ذخیره، نتایج باید خالی باشند
            default_values=current_default_values, # استفاده از مقادیری که ممکن است اطلاعات مشتری را حفظ کرده باشند
            dropdown_options=dropdown_options,
            selections=prepared_initial_selections # انتخاب‌های پیش‌فرض اولیه با مقادیر درصد صحیح
        )
        
    except Exception as e:
        print(f"خطای کلی در روت price_calculator: {e}")
        traceback.print_exc()
        flash("خطایی در بارگذاری صفحه محاسبه قیمت رخ داد.", "error")
        return redirect(url_for("index"))

@app.route("/price_calculator_settings", methods=["GET", "POST"])
def price_calculator_settings():
    """صفحه تنظیمات قیمت پایه"""
    # print("\\n--- Initiating price_calculator_settings ---") # Removed
    try:
        if request.method == "POST":
            # print("--- Method: POST ---") # Removed
            
            # # چاپ مقادیر خام از فرم # Removed
            # print("DEBUG: Raw form data:") # Removed
            # for key in request.form: # Removed
            #     print(f"  {key}: {request.form.getlist(key)}") # استفاده از getlist برای دیدن همه مقادیر در صورت وجود کلید تکراری # Removed
            
            value_for_sefid_price = request.form.get("رنگی") 
            # print(f"DEBUG: Raw 'رنگی' value from form: {value_for_sefid_price}") # Removed

            prices_to_save = {
                "فریم_لس_قدیمی": float(request.form.get("فریم_لس_قدیمی")),
                "فریم_لس_قالب_جدید": float(request.form.get("فریم_لس_قالب_جدید")),
                "توچوب_دار": float(request.form.get("توچوب_دار")),
                "دور_آلومینیوم": float(request.form.get("دور_آلومینیوم")),
                "لاستیک": float(request.form.get("لاستیک")),
                "بست_نصب": float(request.form.get("بست_نصب")),
                "چهارچوب_فریم_لس": float(request.form.get("چهارچوب_فریم_لس")),
                "داخل_چوب": float(request.form.get("داخل_چوب")),
                "دور_آلومینیوم_ماشین": float(request.form.get("دور_آلومینیوم_ماشین")),
                "خام": float(request.form.get("خام")),
                "آنادایز": float(request.form.get("آنادایز")),
                "سفید": float(value_for_sefid_price),
                "پلای_وود": float(request.form.get("پلای_وود")),
                "تا_260": float(request.form.get("تا_260")),
                "261_تا_320": float(request.form.get("261_تا_320")),
                "321_تا_360": float(request.form.get("321_تا_360")),
                "بیش_از_360": float(request.form.get("بیش_از_360")),
                "رنگ_نهایی_خارجی": float(request.form.get("رنگ_نهایی_خارجی")),
                "رنگ_نهایی_ایرانی": float(request.form.get("رنگ_نهایی_ایرانی")),
                "زیر_سازی_خارجی": float(request.form.get("زیر_سازی_خارجی")),
                "زیر_سازی_ایرانی": float(request.form.get("زیر_سازی_ایرانی")),
                "کد_رنگ_خارجی": float(request.form.get("کد_رنگ_خارجی")),
                "کد_رنگ_ایرانی": float(request.form.get("کد_رنگ_ایرانی")),
                "لولا": float(request.form.get("لولا")),
                "قفل": float(request.form.get("قفل")),
                "سیلندر": float(request.form.get("سیلندر"))
            }
            # print(f"DEBUG: Prices to save (after _to_float): {prices_to_save}") # Removed
            
            conn = None # Initialize conn to None
            try:
                conn = get_db_connection()
                # print("DEBUG: Database connection obtained for POST.") # Removed
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS price_settings (key TEXT PRIMARY KEY, value REAL)")
                # print("DEBUG: 'price_settings' table ensured.") # Removed
                
                # print("DEBUG: Attempting to save to DB:") # Removed
                for key, value in prices_to_save.items():
                    # print(f"  Saving: {key} = {value} (Type: {type(value)})") # Removed
                    cursor.execute("INSERT OR REPLACE INTO price_settings (key, value) VALUES (?, ?)", (key, value))
                
                conn.commit()
                # print("DEBUG: conn.commit() executed successfully.") # Removed
            except sqlite3.Error as db_err:
                print(f"!!!!!! DATABASE ERROR during POST: {db_err}")
                traceback.print_exc()
                flash(f"خطای دیتابیس هنگام ذخیره: {db_err}", "error")
            finally:
                if conn:
                    conn.close()
                    # print("DEBUG: Database connection closed for POST.") # Removed
            
            if not flash_messages_exist(category_filter="error"): # Only flash success if no DB error occurred
                 flash("تنظیمات با موفقیت ذخیره شد.", "success")
            return redirect(url_for("price_calculator_settings"))
        
        # GET request - نمایش فرم
        # print("--- Method: GET ---") # Removed
        conn = None # Initialize conn to None
        current_prices = {}
        try:
            conn = get_db_connection()
            # print("DEBUG: Database connection obtained for GET.") # Removed
            cursor = conn.cursor()
            # اطمینان از وجود جدول قبل از خواندن (اگرچه در POST هم ایجاد می‌شود)
            cursor.execute("CREATE TABLE IF NOT EXISTS price_settings (key TEXT PRIMARY KEY, value REAL)")
            # print("DEBUG: 'price_settings' table ensured for GET.") # Removed
            cursor.execute("SELECT key, value FROM price_settings")
            rows = cursor.fetchall()
            # print(f"DEBUG: Rows fetched from DB: {len(rows)} rows") # Removed
            current_prices = {row[0]: row[1] for row in rows}
            # print(f"DEBUG: Current prices from DB: {current_prices}") # Removed
        except sqlite3.Error as db_err:
            print(f"!!!!!! DATABASE ERROR during GET: {db_err}")
            traceback.print_exc()
            flash(f"خطای دیتابیس هنگام خواندن تنظیمات: {db_err}", "error")
            # اگر در خواندن از دیتابیس خطا رخ دهد، current_prices خالی می‌ماند و مقادیر پیش‌فرض استفاده می‌شوند
        finally:
            if conn:
                conn.close()
                # print("DEBUG: Database connection closed for GET.") # Removed
        
        display_prices = {
            "فریم_لس_قدیمی": current_prices.get("فریم_لس_قدیمی", 0.0),
            "فریم_لس_قالب_جدید": current_prices.get("فریم_لس_قالب_جدید", 0.0),
            "توچوب_دار": current_prices.get("توچوب_دار", 0.0),
            "دور_آلومینیوم": current_prices.get("دور_آلومینیوم", 0.0),
            "لاستیک": current_prices.get("لاستیک", 0.0),
            "بست_نصب": current_prices.get("بست_نصب", 0.0),
            "چهارچوب_فریم_لس": current_prices.get("چهارچوب_فریم_لس", 0.0),
            "داخل_چوب": current_prices.get("داخل_چوب", 0.0),
            "دور_آلومینیوم_ماشین": current_prices.get("دور_آلومینیوم_ماشین", 0.0),
            "خام": current_prices.get("خام", 0.0),
            "آنادایز": current_prices.get("آنادایز", 0.0),
            "رنگی": current_prices.get("سفید", 0.0), 
            "پلای_وود": current_prices.get("پلای_وود", 0.0),
            "تا_260": current_prices.get("تا_260", 0.0),
            "261_تا_320": current_prices.get("261_تا_320", 0.0),
            "321_تا_360": current_prices.get("321_تا_360", 0.0),
            "بیش_از_360": current_prices.get("بیش_از_360", 0.0),
            "رنگ_نهایی_خارجی": current_prices.get("رنگ_نهایی_خارجی", 0.0),
            "رنگ_نهایی_ایرانی": current_prices.get("رنگ_نهایی_ایرانی", 0.0),
            "زیر_سازی_خارجی": current_prices.get("زیر_سازی_خارجی", 0.0),
            "زیر_سازی_ایرانی": current_prices.get("زیر_سازی_ایرانی", 0.0),
            "کد_رنگ_خارجی": current_prices.get("کد_رنگ_خارجی", 0.0),
            "کد_رنگ_ایرانی": current_prices.get("کد_رنگ_ایرانی", 0.0),
            "لولا": current_prices.get("لولا", 0.0),
            "قفل": current_prices.get("قفل", 0.0),
            "سیلندر": current_prices.get("سیلندر", 0.0),
        }
        # print(f"DEBUG: Display prices sent to template: {display_prices}") # Removed
        
        return render_template("price_calculator_settings.html", prices=display_prices)
        
    except Exception as e:
        print(f"!!!!!! خطای کلی در روت price_calculator_settings: {e}")
        traceback.print_exc()
        flash("خطایی در تنظیمات قیمت پایه رخ داد.", "error")
        return redirect(url_for("index")) # تغییر به ایندکس برای جلوگیری از حلقه احتمالی

# Helper function to check if flash messages of a certain category exist
def flash_messages_exist(category_filter=None):
    if '_flashes' in session:
        for category, message in session['_flashes']:
            if category_filter is None or category == category_filter:
                return True
    return False

@app.route("/save_quote", methods=["POST"])
def save_quote():
    if request.method == "POST":
        conn = None  # Initialize conn to None
        try:
            # Ensure the request is JSON
            if not request.is_json:
                flash("درخواست باید با فرمت JSON باشد.", "danger")
                # Return JSON error for AJAX, redirect otherwise (though AJAX is expected)
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, error="درخواست باید با فرمت JSON باشد"), 400
                return redirect(url_for('price_calculator'))

            data = request.get_json()
            if not data:
                flash("اطلاعات ارسال نشده یا فرمت نامعتبر است.", "danger")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, error="اطلاعات ارسال نشده یا فرمت نامعتبر است."), 400
                return redirect(url_for('price_calculator'))

            # Log دریافت داده‌ها
            print(f"DEBUG: Data received in /save_quote: {data}")

            customer_name = data.get("customer_name")
            customer_mobile = data.get("customer_mobile")
            input_width = data.get("input_width")
            input_height = data.get("input_height")
            profile_type = data.get("profile_type")
            aluminum_color = data.get("aluminum_color")
            door_material = data.get("door_material")
            paint_condition = data.get("paint_condition")
            paint_brand = data.get("paint_brand")
            selections_details = data.get("selections_details") # Already a JSON string from JS
            final_price = data.get("final_price")
            shamsi_order_date = data.get("shamsi_date", "") # دریافت تاریخ شمسی از payload

            # اعتبارسنجی اولیه
            if not all([customer_name, input_width, input_height, profile_type, selections_details, final_price]):
                error_message = "اطلاعات ضروری برای ذخیره قیمت ناقص است."
                flash(error_message, "danger")
                # حفظ اطلاعات مشتری حتی در صورت خطا در سایر فیلدها
                if customer_name or customer_mobile:
                     # flash({'customer_name': customer_name, 'customer_mobile': customer_mobile}, 'preserved_customer_info') # OLD way
                     session['preserved_customer_info_data'] = {'customer_name': customer_name, 'customer_mobile': customer_mobile} # NEW way
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, error=error_message, preserved_info={'customer_name': customer_name, 'customer_mobile': customer_mobile}), 400
                return redirect(url_for('price_calculator'))


            # فراخوانی تابع دیتابیس برای ذخیره
            data_to_save = {
                'customer_name': customer_name,
                'customer_mobile': customer_mobile,
                'input_width': input_width,
                'input_height': input_height,
                'profile_type': profile_type,
                'aluminum_color': aluminum_color,
                'door_material': door_material,
                'paint_condition': paint_condition,
                'paint_brand': paint_brand,
                'selections_details': selections_details,
                'final_price': final_price,
                'shamsi_order_date': shamsi_order_date
            }
            
            if save_quote_db(data_to_save):
                success_message = "قیمت‌دهی با موفقیت ذخیره شد."
                flash(success_message, "success")
                session['preserved_customer_info_data'] = {'customer_name': customer_name, 'customer_mobile': customer_mobile}
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=True, message=success_message, preserved_info={'customer_name': customer_name, 'customer_mobile': customer_mobile})
                return redirect(url_for('price_calculator'))
            else:
                raise Exception("خطا در عملیات ذخیره در پایگاه داده")

        except Exception as e:
            print(f"Error in /save_quote: {e}")
            traceback.print_exc()
            error_message = f"خطا در ذخیره اطلاعات: {str(e)}"
            flash(error_message, "danger")

            preserved_customer_name = ""
            preserved_customer_mobile = ""
            if request.is_json:
                data_for_flash = request.get_json() or {}
                preserved_customer_name = data_for_flash.get("customer_name", "")
                preserved_customer_mobile = data_for_flash.get("customer_mobile", "")
            
            if preserved_customer_name or preserved_customer_mobile:
                session['preserved_customer_info_data'] = {'customer_name': preserved_customer_name, 'customer_mobile': preserved_customer_mobile}

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, error=error_message, preserved_info={'customer_name': preserved_customer_name, 'customer_mobile': preserved_customer_mobile}), 500
            return redirect(url_for('price_calculator'))
    
    # اگر متد POST نبود یا خطای دیگری قبل از try رخ داد
    flash("درخواست نامعتبر برای ذخیره قیمت.", "warning")
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(success=False, error="درخواست نامعتبر برای ذخیره قیمت."), 405 # Method Not Allowed
    return redirect(url_for('price_calculator'))

@app.route("/saved_quotes")
def saved_quotes():
    """نمایش قیمت‌دهی‌های ذخیره شده با قابلیت گروه‌بندی و باز/بسته شدن"""
    try:
        quotes = get_all_saved_quotes_db()
        
        grouped_quotes = defaultdict(list)
        for quote_data in quotes:
            quote_dict = {
                'id': quote_data['id'],
                'customer_name': quote_data['customer_name'] if quote_data['customer_name'] else "بدون نام مشتری",
                'customer_mobile': quote_data['customer_mobile'],
                'input_width': quote_data['input_width'],
                'input_height': quote_data['input_height'],
                'profile_type': quote_data['profile_type'],
                'aluminum_color': quote_data['aluminum_color'],
                'door_material': quote_data['door_material'],
                'paint_condition': quote_data['paint_condition'],
                'paint_brand': quote_data['paint_brand'],
                'final_calculated_price': quote_data['final_calculated_price'],
                'shamsi_order_date': quote_data['shamsi_order_date'] if quote_data['shamsi_order_date'] else "تاریخ نامشخص"
            }

            timestamp_val = quote_data['timestamp']
            if isinstance(timestamp_val, str):
                try:
                    timestamp_val = datetime.strptime(timestamp_val.split('.')[0], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        timestamp_val = datetime.strptime(timestamp_val, '%Y-%m-%d %H:%M')
                    except ValueError:
                        print(f"WARNING: Could not parse timestamp string: {quote_data['timestamp']} for quote id {quote_dict['id']}. Setting to None.")
                        timestamp_val = None
            elif timestamp_val is None:
                # print(f"WARNING: Timestamp is None for quote id {quote_dict['id']}. Setting to None.")
                timestamp_val = None
            quote_dict['timestamp'] = timestamp_val
            
            try:
                if quote_data['selections_details']:
                    # Handle both JSON string and already parsed JSON (if DB driver did it, though sqlite returns str)
                    if isinstance(quote_data['selections_details'], str):
                         quote_dict['selections_details'] = json.loads(quote_data['selections_details'])
                    else:
                         quote_dict['selections_details'] = quote_data['selections_details']
                else:
                    quote_dict['selections_details'] = {}
            except json.JSONDecodeError as json_err:
                print(f"ERROR: JSONDecodeError for quote id {quote_dict['id']}: {json_err}")
                quote_dict['selections_details'] = {}
            except Exception as e_json:
                print(f"ERROR: Unknown error parsing selections_details for quote id {quote_dict['id']}: {e_json}")
                quote_dict['selections_details'] = {}
                
            customer_key = quote_dict['customer_name']
            grouped_quotes[customer_key].append(quote_dict)
        
        all_quotes_for_js = [quote for customer_quotes in grouped_quotes.values() for quote in customer_quotes]
        quotes_json_list = []
        for quote_data_dict in all_quotes_for_js:
            temp_quote = quote_data_dict.copy()
            if temp_quote.get('timestamp') and not isinstance(temp_quote['timestamp'], str):
                try:
                    temp_quote['timestamp'] = temp_quote['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                except AttributeError: # Should not happen if previous logic is correct, but as a safeguard
                    temp_quote['timestamp'] = str(temp_quote['timestamp'])
            quotes_json_list.append(temp_quote)
        all_quotes_json = json.dumps(quotes_json_list)

        return render_template("saved_quotes.html", grouped_quotes=grouped_quotes, all_quotes_json=all_quotes_json)
        
    except Exception as e:
        print(f"!!!!!! ERROR in saved_quotes route: {e}") 
        traceback.print_exc()
        flash("خطایی در بارگذاری قیمت‌دهی‌های ذخیره شده رخ داد.", "error")
        return redirect(url_for("index"))

@app.route("/delete_quote/<int:quote_id>", methods=["POST"])
def delete_quote(quote_id):
    """پاک کردن یک قیمت‌دهی ذخیره شده"""
    try:
        # استفاده از تابع جدید
        if delete_quote_db(quote_id):
            flash("قیمت‌دهی با موفقیت پاک شد.", "success")
        else:
            flash("قیمت‌دهی مورد نظر یافت نشد یا خطا در حذف.", "error")
        return redirect(url_for("saved_quotes"))
        
    except Exception as e:
        print(f"خطا در پاک کردن قیمت‌دهی: {e}")
        traceback.print_exc()
        flash("خطایی در پاک کردن قیمت‌دهی رخ داد.", "error")
        return redirect(url_for("saved_quotes"))

@app.route("/delete_multiple_quotes", methods=["POST"])
def delete_multiple_quotes():
    """پاک کردن چندین قیمت‌دهی انتخاب شده"""
    try:
        # دریافت لیست شناسه‌های انتخاب شده
        selected_ids = request.form.getlist('selected_quotes')
        
        if not selected_ids:
            flash("هیچ قیمت‌دهی‌ای انتخاب نشده است.", "warning")
            return redirect(url_for("saved_quotes"))
        
        conn = None # To avoid UnboundLocalError in finally if used
        
        # تبدیل شناسه‌ها به لیست
        if not selected_ids:
             flash("هیچ موردی انتخاب نشده", "warning")
             return redirect(url_for("saved_quotes"))

        deleted_count = delete_multiple_quotes_db(selected_ids)
        
        if deleted_count > 0:
            flash(f"{deleted_count} قیمت‌دهی با موفقیت پاک شدند.", "success")
        else:
            flash("هیچ قیمت‌دهی‌ای پاک نشد.", "warning")
            
        return redirect(url_for("saved_quotes"))
        
    except Exception as e:
        print(f"خطا در پاک کردن قیمت‌دهی‌های انتخاب شده: {e}")
        traceback.print_exc()
        flash("خطایی در پاک کردن قیمت‌دهی‌ها رخ داد.", "error")
        return redirect(url_for("saved_quotes"))

# افزودن کد راه‌اندازی Flask در انتهای فایل
if __name__ == "__main__":
    print("DEBUG: تلاش برای اجرای ensure_default_custom_columns()")
    ensure_default_custom_columns()
    print("DEBUG: ensure_default_custom_columns() اجرا شد.")
    initialize_inventory_database() # اضافه شده برای مقداردهی اولیه Inventory
    print("DEBUG: initialize_inventory_database() فراخوانی شد.")
    
    # اتصال اولیه برای اجرای مهاجرت‌ها
    conn = get_db_connection()
    if conn:
        conn.close()
        
    app.run(debug=True, host='0.0.0.0', port=5000)
