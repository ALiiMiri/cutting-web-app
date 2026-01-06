
from flask import Flask, render_template, request, redirect, url_for, flash, session, render_template_string, get_flashed_messages
from flask_login import LoginManager, login_required, current_user
import os
import sqlite3
import traceback  # برای نمایش خطای کامل
from flask import send_file, jsonify
import time
import arabic_reshaper
from bidi.algorithm import get_display
from weasyprint import HTML, CSS
from datetime import datetime, date
import jdatetime
import random

# Import date utilities
from date_utils import (
    get_shamsi_timestamp, 
    get_shamsi_datetime_str, 
    get_shamsi_datetime_iso,
    gregorian_to_shamsi,
    gregorian_to_shamsi_date
)

from math import ceil
import json
from collections import defaultdict
from config import Config
from database import (
    get_db_connection,
    check_table_exists,
    get_all_projects,
    get_projects_paginated,
    get_unique_customers,
    add_project_db,
    get_project_details_db,
    generate_unique_project_code,
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
    update_custom_column_option,
    get_non_empty_custom_columns_for_project,
    get_price_settings_db,
    save_quote_db,
    get_all_saved_quotes_db,
    delete_quote_db,
    delete_multiple_quotes_db,
    save_doors_batch_db,
    batch_update_doors_db,
    get_column_type_db,
    get_column_id_from_option_db,
    initialize_inventory_tables,
    get_all_profile_types,
    add_profile_type,
    get_profile_details,
    get_inventory_settings,
    update_inventory_settings,
    get_inventory_stats,
    delete_profile_type,
    update_profile_type,
    get_profile_stock_details,
    add_inventory_stock,
    remove_inventory_stock,
    add_inventory_piece,
    remove_inventory_piece,
    get_inventory_logs,
    get_project_deductions,
    check_if_already_deducted,
    init_db,
    get_available_inventory_pieces
)

# Import blueprints
from routes import register_blueprints

# Import backup manager
import backup_manager

# Import auth utilities
from auth_utils import get_user_by_id

# Import decorators
from decorators import admin_required, staff_or_admin_required, prevent_read_only

# --- تنظیمات اولیه ---
DB_NAME = Config.DB_NAME


# --- تابع کمکی برای بررسی وجود جدول ---





# --- Flask App Setup ---
app = Flask(__name__, template_folder='templates')
app.secret_key = Config.SECRET_KEY

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'لطفاً برای دسترسی به این صفحه وارد شوید.'
login_manager.login_message_category = 'warning'

# Configure Flask to use UTF-8 encoding
@app.after_request
def set_charset(response):
    """Ensure all responses use UTF-8 encoding"""
    if 'Content-Type' in response.headers:
        content_type = response.headers['Content-Type']
        if 'charset=' not in content_type:
            response.headers['Content-Type'] = content_type + '; charset=utf-8'
    else:
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

# Configure Jinja2 to use UTF-8
app.jinja_env.autoescape = True
app.jinja_env.auto_reload = True

# اضافه کردن فیلتر شمسی به Jinja2
@app.template_filter('shamsi')
def shamsi_filter(dt):
    """تبدیل تاریخ میلادی به شمسی برای استفاده در template ها"""
    return gregorian_to_shamsi(dt)

@app.template_filter('shamsi_date')
def shamsi_date_filter(dt):
    """تبدیل تاریخ میلادی به شمسی (فقط تاریخ) برای استفاده در template ها"""
    return gregorian_to_shamsi_date(dt)

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

# Global before_request to protect all routes
@app.before_request
def require_login():
    """نیاز به لاگین برای همه routeها به جز login و static"""
    # مسیرهای استثنا (که نیاز به لاگین ندارند)
    allowed_endpoints = ['auth.login', 'static']
    
    # در حالت اضطراری (وقتی جدول users وجود ندارد)، اجازه دسترسی به backup restore
    emergency_endpoints = ['backup_restore', 'backup_management']
    if request.endpoint in emergency_endpoints:
        try:
            from database import check_table_exists
            if not check_table_exists('users'):
                # در حالت اضطراری، اجازه دسترسی به backup restore
                allowed_endpoints.extend(emergency_endpoints)
        except:
            pass  # در صورت خطا، از احراز هویت استفاده می‌کنیم
    
    # اگر کاربر لاگین نیست و مسیر جاری در لیست استثنا نیست
    if not current_user.is_authenticated:
        if request.endpoint not in allowed_endpoints:
            flash('لطفاً برای دسترسی به سیستم وارد شوید.', 'warning')
            return redirect(url_for('auth.login'))
    
    # اگر کاربر لاگین است ولی باید رمز تغییر دهد
    if current_user.is_authenticated and hasattr(current_user, 'must_change_password') and current_user.must_change_password:
        # فقط به صفحات change_password و logout اجازه دسترسی
        if request.endpoint not in ['auth.change_password', 'auth.logout', 'static']:
            flash('لطفاً ابتدا رمز عبور خود را تغییر دهید.', 'warning')
            return redirect(url_for('auth.change_password'))

# --- مقداردهی اولیه دیتابیس ---
# فراخوانی تابع ایجاد جداول انبار در شروع برنامه
# فراخوانی تابع ایجاد جداول انبار در شروع برنامه
print("DEBUG: Initializing database tables...")
init_db()

# Register blueprints
register_blueprints(app)

# --- بررسی وجود جداول بعد از مقداردهی اولیه ---
print("\n--- Starting table checks ---")
check_table_exists("projects")
check_table_exists("doors")
check_table_exists("custom_columns")
check_table_exists("custom_column_options")
check_table_exists("door_custom_values")
print("--- Table checks completed ---\n")


# --- Routes (آدرس‌های وب) ---


@app.route("/")
def index():
    print("DEBUG: Route / (index) called.")
    try:
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '', type=str).strip()
        sort_by = request.args.get('sort_by', 'id', type=str)
        sort_order = request.args.get('sort_order', 'DESC', type=str)
        date_from = request.args.get('date_from', '', type=str).strip()
        date_to = request.args.get('date_to', '', type=str).strip()
        customer_filter = request.args.get('customer_filter', '', type=str).strip()
        per_page = request.args.get('per_page', 15, type=int)
        
        # Validate per_page
        if per_page not in [10, 15, 20, 30, 50]:
            per_page = 15
        
        # Get paginated projects
        result = get_projects_paginated(
            page=page,
            per_page=per_page,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            date_from=date_from,
            date_to=date_to,
            customer_filter=customer_filter
        )
        
        # Get unique customers for filter dropdown
        unique_customers = get_unique_customers()
        
        return render_template(
            "index.html",
            projects=result['projects'],
            pagination=result,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            date_from=date_from,
            date_to=date_to,
            customer_filter=customer_filter,
            per_page=per_page,
            unique_customers=unique_customers
        )
    except Exception as e:
        print(f"!!!!!! Unexpected error in index route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش لیست پروژه‌ها رخ داد.", "error")
        return render_template(
            "index.html",
            projects=[],
            pagination={"total": 0, "page": 1, "pages": 1, "per_page": 15},
            search="",
            sort_by="id",
            sort_order="DESC",
            date_from="",
            date_to="",
            customer_filter="",
            per_page=15,
            unique_customers=[]
        )


@app.route("/home")
def home():
    """نام دیگر برای صفحه اصلی (برای سازگاری با تمپلیت‌ها)"""
    return index()


@app.route("/project/add", methods=["GET"])
def add_project_form():
    print("DEBUG: Route /project/add (GET - add_project_form) called.")
    order_ref = generate_unique_project_code()
    print(f"DEBUG: Generated order_ref (project code): {order_ref}")
    return render_template("add_project.html", order_ref=order_ref)


@app.route("/project/add", methods=["POST"])
@staff_or_admin_required
def add_project_route():
    print("DEBUG: Route /project/add (POST - add_project_route) called.")
    customer_name = request.form.get("customer_name")
    order_ref = request.form.get("order_ref", "").strip()
    date_shamsi = request.form.get("date_shamsi", "").strip()
    
    # Validate date is required
    if not date_shamsi:
        flash("لطفاً تاریخ را انتخاب کنید. انتخاب تاریخ اجباری است.", "error")
        return render_template("add_project.html", order_ref=order_ref or generate_unique_project_code())
    
    if not customer_name:
        flash("لطفاً نام مشتری را وارد کنید.", "error")
        return render_template("add_project.html", order_ref=order_ref or generate_unique_project_code())
    
    # If order_ref is empty, generate a new one
    if not order_ref:
        order_ref = generate_unique_project_code()
    
    # Use order_ref as project_code (they are the same)
    project_code = order_ref
    
    new_id = add_project_db(customer_name, order_ref, date_shamsi, project_code)
    if new_id:
        flash(
            f"پروژه جدید برای مشتری '{customer_name}' (شماره سفارش: {order_ref}) با موفقیت اضافه شد.",
            "success",
        )
        print(f"DEBUG: Project ID {new_id} added with order_ref/project_code {order_ref}, name: '{customer_name}', date: {date_shamsi}, redirecting to index.")
        return redirect(url_for("index"))
    else:
        flash("خطایی در ذخیره پروژه رخ داد.", "error")
        return render_template("add_project.html", order_ref=order_ref or generate_unique_project_code())


@app.route("/project/<int:project_id>/update", methods=["POST"])
@staff_or_admin_required
def update_project_route(project_id):
    """ویرایش پروژه از صفحه خانه (فرم مودال)"""
    try:
        customer_name = request.form.get("customer_name")
        order_ref = request.form.get("order_ref")
        date_shamsi = request.form.get("date_shamsi", "")

        if not customer_name and not order_ref:
            flash("لطفاً حداقل نام مشتری یا شماره سفارش را وارد کنید.", "error")
            return redirect(url_for("index"))

        success = update_project_db(project_id, customer_name, order_ref, date_shamsi)
        if success:
            flash("پروژه با موفقیت ویرایش شد.", "success")
        else:
            flash("خطا در ویرایش پروژه.", "error")
        return redirect(url_for("index"))
    except Exception as e:
        print(f"!!!!!! Unexpected error in update_project_route: {e}")
        traceback.print_exc()
        flash("خطایی در ویرایش پروژه رخ داد.", "error")
        return redirect(url_for("index"))


@app.route("/project/<int:project_id>/delete", methods=["POST", "GET"])
@admin_required
def delete_project_route(project_id):
    """حذف پروژه (از صفحه خانه). GET فقط ریدایرکت می‌کند؛ حذف واقعی با POST انجام می‌شود."""
    try:
        if request.method == "GET":
            flash("برای حذف پروژه، از دکمه حذف در صفحه خانه استفاده کنید.", "warning")
            return redirect(url_for("index"))

        # 🔄 بکاپ خودکار قبل از حذف پروژه
        print(f"ایجاد بکاپ خودکار قبل از حذف پروژه {project_id}...")
        backup_success, backup_result = backup_manager.create_backup(
            reason=f"before_delete_project",
            user="system",
            metadata={"project_id": project_id, "action": "delete_project"}
        )
        if backup_success:
            print(f"✓ بکاپ قبل از حذف پروژه ایجاد شد: {backup_result}")
        else:
            print(f"⚠ خطا در ایجاد بکاپ (ادامه می‌دهیم): {backup_result}")

        success = delete_project_db(project_id)
        if success:
            flash("پروژه با موفقیت حذف شد.", "success")
        else:
            flash("خطا در حذف پروژه.", "error")
        return redirect(url_for("index"))
    except Exception as e:
        print(f"!!!!!! Unexpected error in delete_project_route: {e}")
        traceback.print_exc()
        flash("خطایی در حذف پروژه رخ داد.", "error")
        return redirect(url_for("index"))


@app.route("/project/<int:project_id>")
def view_project(project_id):
    print(f"DEBUG: >>>>>>> Entering route /project/{project_id} (view_project) <<<<<<<")
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
    
    saved_count, error_count = save_doors_batch_db(project_id, pending_doors)

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
    
    # تنظیم ستون‌های پیش‌فرض با استفاده از ستون‌های فعال در دیتابیس
    visible_columns = [col['key'] for col in active_columns]
    
    # اگر لیست خالی بود (هیچ ستون سفارشی فعال نبود)، لیست خالی برمی‌گردانیم
    # ستون‌های پایه در توابع دیگر (مثل export_to_excel) اضافه می‌شوند
    if not visible_columns:
        visible_columns = []
    
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
        conn = get_db_connection()
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
@staff_or_admin_required
def delete_door(project_id, door_id):
    """حذف یک درب از پروژه"""
    print(f"DEBUG: درخواست برای حذف درب با ID {door_id} از پروژه {project_id}")
    
    # اتصال به دیتابیس
    conn = None
    try:
        conn = get_db_connection()
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
        # فرمت تاریخ شمسی به فارسی
        now_jalali = jdatetime.datetime.now()
        # نام ماه‌های فارسی
        persian_months = {
            1: 'فروردین', 2: 'اردیبهشت', 3: 'خرداد', 4: 'تیر', 5: 'مرداد', 6: 'شهریور',
            7: 'مهر', 8: 'آبان', 9: 'آذر', 10: 'دی', 11: 'بهمن', 12: 'اسفند'
        }
        # نام روزهای هفته فارسی
        persian_weekdays = {
            0: 'شنبه', 1: 'یکشنبه', 2: 'دوشنبه', 3: 'سه‌شنبه', 
            4: 'چهارشنبه', 5: 'پنج‌شنبه', 6: 'جمعه'
        }
        weekday_name = persian_weekdays.get(now_jalali.weekday(), '')
        month_name = persian_months.get(now_jalali.month, '')
        today_jalali = f"{weekday_name}، {now_jalali.day} {month_name} {now_jalali.year}"
        
        # دریافت اطلاعات پروژه
        customer_name = project_info.get("customer_name", "")
        order_ref = project_info.get("order_ref", "")
        
        # ردیف 1: تاریخ
        ws['A1'] = "تاریخ"
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws['A1'].font = Font(bold=True, size=12)
        ws['A1'].fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        ws.merge_cells('A1:B1')
        
        ws['C1'] = today_jalali
        ws['C1'].alignment = Alignment(horizontal='center', vertical='center')
        ws['C1'].font = Font(bold=True, size=11)
        ws['C1'].fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
        ws.merge_cells('C1:E1')
        
        # ردیف 2: نام پروژه
        ws['A2'] = "نام پروژه"
        ws['A2'].alignment = Alignment(horizontal='center', vertical='center')
        ws['A2'].font = Font(bold=True, size=12)
        ws['A2'].fill = PatternFill(start_color="E6F0FF", end_color="E6F0FF", fill_type="solid")
        ws.merge_cells('A2:B2')
        
        ws['C2'] = customer_name if customer_name else "نامشخص"
        ws['C2'].alignment = Alignment(horizontal='center', vertical='center')
        ws['C2'].font = Font(bold=True, size=11)
        ws['C2'].fill = PatternFill(start_color="E6F0FF", end_color="E6F0FF", fill_type="solid")
        ws.merge_cells('C2:E2')
        
        # ردیف 3: شماره سفارش و کد پروژه
        ws['A3'] = "شماره سفارش"
        ws['A3'].alignment = Alignment(horizontal='center', vertical='center')
        ws['A3'].font = Font(bold=True, size=12)
        ws['A3'].fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        ws.merge_cells('A3:B3')
        
        ws['C3'] = order_ref if order_ref else "ندارد"
        ws['C3'].alignment = Alignment(horizontal='center', vertical='center')
        ws['C3'].font = Font(bold=True, size=11)
        ws['C3'].fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
        ws.merge_cells('C3:E3')
        
        # فاصله بین جدول اصلی و هدر
        row_offset = 4
        
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
        
        # ========== ایجاد شیت نتایج برش ==========
        try:
            # محاسبه برش (منطق مشابه calculate_cutting)
            STOCK_LENGTH = 600
            WEIGHT_PER_METER = 1.9
            
            # جمع‌آوری قطعات مورد نیاز به تفکیک نوع پروفیل
            profile_requirements = {}
            for door in doors:
                try:
                    width = float(door["width"])
                    height = float(door["height"])
                    quantity = int(door["quantity"])
                    profile_type = door.get("noe_profile", "پیش‌فرض")
                    
                    if width <= 0 or height <= 0 or quantity <= 0:
                        continue
                    
                    if profile_type not in profile_requirements:
                        profile_requirements[profile_type] = []
                    
                    profile_requirements[profile_type].append((height, quantity * 2))
                    profile_requirements[profile_type].append((width, quantity * 1))
                except (ValueError, TypeError, KeyError):
                    continue
            
            if profile_requirements:
                # دریافت تنظیمات
                settings = get_inventory_settings()
                use_inventory = settings.get('use_inventory_for_cutting', False)
                prefer_pieces = settings.get('prefer_inventory_pieces', False)
                
                # دریافت min_waste برای هر پروفیل
                profiles = get_all_profile_types()
                profile_min_waste = {}
                for p in profiles:
                    profile_min_waste[p['name']] = float(p.get('min_waste', 70))
                
                # محاسبه برش برای هر نوع پروفیل
                all_new_bins = []  # شاخه‌های جدید 6 متری
                all_inventory_bins = []  # شاخه‌های برش‌خورده از انبار
                
                for profile_type, required_pieces in profile_requirements.items():
                    bins = []
                    used_pieces_for_profile = []
                    
                    # دریافت قطعات برش‌خورده موجود
                    available_inventory_pieces = []
                    if use_inventory:
                        available_inventory_pieces = get_available_inventory_pieces(profile_type)
                        available_inventory_pieces = available_inventory_pieces.copy()
                    
                    # تبدیل به لیست صاف
                    flat_pieces = []
                    for length, count in required_pieces:
                        flat_pieces.extend([length] * count)
                    
                    sorted_pieces = sorted(flat_pieces, reverse=True)
                    
                    for piece_length in sorted_pieces:
                        if piece_length > STOCK_LENGTH:
                            continue
                        
                        placed = False
                        
                        # اولویت با قطعات برش‌خورده
                        if use_inventory and prefer_pieces and available_inventory_pieces:
                            for idx, inv_piece in enumerate(available_inventory_pieces):
                                if inv_piece['length'] >= piece_length:
                                    remaining = inv_piece['length'] - piece_length
                                    used_pieces_for_profile.append(inv_piece['id'])
                                    available_inventory_pieces.pop(idx)
                                    
                                    bins.append({
                                        "pieces": [piece_length],
                                        "remaining": remaining,
                                        "profile_type": profile_type,
                                        "from_inventory_piece": True,
                                        "inventory_piece_id": inv_piece['id'],
                                        "initial_length": inv_piece['length']
                                    })
                                    placed = True
                                    break
                        
                        # قرار دادن در شاخه‌های موجود (هم جدید و هم برش‌خورده)
                        if not placed:
                            for bin_data in bins:
                                if bin_data["remaining"] >= piece_length:
                                    bin_data["pieces"].append(piece_length)
                                    bin_data["remaining"] -= piece_length
                                    placed = True
                                    break
                        
                        # شاخه جدید
                        if not placed:
                            bins.append({
                                "pieces": [piece_length],
                                "remaining": STOCK_LENGTH - piece_length,
                                "profile_type": profile_type,
                                "from_inventory_piece": False,
                                "initial_length": STOCK_LENGTH
                            })
                    
                    # تفکیک شاخه‌های جدید و برش‌خورده
                    for bin_data in bins:
                        if bin_data["from_inventory_piece"]:
                            all_inventory_bins.append(bin_data)
                        else:
                            all_new_bins.append(bin_data)
                
                # ایجاد شیت نتایج برش
                ws_cutting = wb.create_sheet("نتایج برش")
                
                # استایل‌ها
                title_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                header_fill_new = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")  # سبز برای شاخه‌های جدید
                header_fill_inv = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")  # زرد برای برش‌خورده
                data_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                
                # عنوان
                ws_cutting['A1'] = "نتایج محاسبه برش"
                ws_cutting['A1'].font = Font(bold=True, size=16, color="FFFFFF")
                ws_cutting['A1'].fill = title_fill
                ws_cutting['A1'].alignment = Alignment(horizontal='center', vertical='center')
                ws_cutting.merge_cells('A1:E1')
                ws_cutting.row_dimensions[1].height = 30
                
                current_row = 3
                
                # بخش شاخه‌های جدید 6 متری
                if all_new_bins:
                    ws_cutting[f'A{current_row}'] = f"شاخه‌های جدید 6 متری ({len(all_new_bins)} عدد)"
                    ws_cutting[f'A{current_row}'].font = Font(bold=True, size=14, color="FFFFFF")
                    ws_cutting[f'A{current_row}'].fill = header_fill_new
                    ws_cutting[f'A{current_row}'].alignment = Alignment(horizontal='center', vertical='center')
                    ws_cutting.merge_cells(f'A{current_row}:E{current_row}')
                    current_row += 1
                    
                    # هدر جدول
                    headers = ["شاخه", "نوع پروفیل", "قطعات برش (cm)", "باقی‌مانده (cm)", "نوع برش"]
                    for col_idx, header in enumerate(headers, 1):
                        cell = ws_cutting.cell(row=current_row, column=col_idx, value=header)
                        cell.font = Font(bold=True, size=11, color="000000")
                        cell.fill = header_fill_new
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                        cell.border = thin_border
                    current_row += 1
                    
                    # داده‌های شاخه‌های جدید
                    for idx, bin_data in enumerate(all_new_bins, 1):
                        profile_type = bin_data.get("profile_type", "پیش‌فرض")
                        pieces = bin_data["pieces"]
                        remaining = round(bin_data["remaining"], 1)
                        min_waste = profile_min_waste.get(profile_type, 70)
                        
                        # تعیین نوع برش
                        if remaining < min_waste:
                            cut_type = "ضایعات کوچک"
                        elif remaining < (STOCK_LENGTH / 2):
                            cut_type = "قطعه متوسط"
                        else:
                            cut_type = "قطعه بزرگ"
                        
                        pieces_str = " + ".join([f"{p:.1f}" for p in pieces])
                        
                        ws_cutting.cell(row=current_row, column=1, value=idx).border = thin_border
                        ws_cutting.cell(row=current_row, column=2, value=profile_type).border = thin_border
                        ws_cutting.cell(row=current_row, column=3, value=pieces_str).border = thin_border
                        ws_cutting.cell(row=current_row, column=4, value=remaining).border = thin_border
                        ws_cutting.cell(row=current_row, column=5, value=cut_type).border = thin_border
                        
                        # رنگ پس‌زمینه برای ردیف‌های زوج
                        if idx % 2 == 0:
                            for col in range(1, 6):
                                ws_cutting.cell(row=current_row, column=col).fill = data_fill
                        
                        # تراز وسط برای همه سلول‌ها
                        for col in range(1, 6):
                            ws_cutting.cell(row=current_row, column=col).alignment = Alignment(horizontal='center', vertical='center')
                        
                        current_row += 1
                    
                    current_row += 2
                
                # بخش شاخه‌های برش‌خورده از انبار
                if all_inventory_bins:
                    ws_cutting[f'A{current_row}'] = f"شاخه‌های برش‌خورده از پروژه‌های قبلی ({len(all_inventory_bins)} عدد)"
                    ws_cutting[f'A{current_row}'].font = Font(bold=True, size=14, color="000000")
                    ws_cutting[f'A{current_row}'].fill = header_fill_inv
                    ws_cutting[f'A{current_row}'].alignment = Alignment(horizontal='center', vertical='center')
                    ws_cutting.merge_cells(f'A{current_row}:E{current_row}')
                    current_row += 1
                    
                    # هدر جدول
                    for col_idx, header in enumerate(headers, 1):
                        cell = ws_cutting.cell(row=current_row, column=col_idx, value=header)
                        cell.font = Font(bold=True, size=11, color="000000")
                        cell.fill = header_fill_inv
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                        cell.border = thin_border
                    current_row += 1
                    
                    # داده‌های شاخه‌های برش‌خورده
                    for idx, bin_data in enumerate(all_inventory_bins, 1):
                        profile_type = bin_data.get("profile_type", "پیش‌فرض")
                        pieces = bin_data["pieces"]
                        remaining = round(bin_data["remaining"], 1)
                        initial_length = bin_data.get("initial_length", STOCK_LENGTH)
                        min_waste = profile_min_waste.get(profile_type, 70)
                        
                        # تعیین نوع برش
                        if remaining < min_waste:
                            cut_type = "ضایعات کوچک"
                        elif remaining < (initial_length / 2):
                            cut_type = "قطعه متوسط"
                        else:
                            cut_type = "قطعه بزرگ"
                        
                        pieces_str = " + ".join([f"{p:.1f}" for p in pieces])
                        
                        ws_cutting.cell(row=current_row, column=1, value=idx).border = thin_border
                        ws_cutting.cell(row=current_row, column=2, value=profile_type).border = thin_border
                        ws_cutting.cell(row=current_row, column=3, value=pieces_str).border = thin_border
                        ws_cutting.cell(row=current_row, column=4, value=remaining).border = thin_border
                        ws_cutting.cell(row=current_row, column=5, value=cut_type).border = thin_border
                        
                        # رنگ پس‌زمینه برای ردیف‌های زوج
                        if idx % 2 == 0:
                            for col in range(1, 6):
                                ws_cutting.cell(row=current_row, column=col).fill = data_fill
                        
                        # تراز وسط برای همه سلول‌ها
                        for col in range(1, 6):
                            ws_cutting.cell(row=current_row, column=col).alignment = Alignment(horizontal='center', vertical='center')
                        
                        current_row += 1
                
                # تنظیم عرض ستون‌ها
                ws_cutting.column_dimensions['A'].width = 10
                ws_cutting.column_dimensions['B'].width = 25
                ws_cutting.column_dimensions['C'].width = 30
                ws_cutting.column_dimensions['D'].width = 18
                ws_cutting.column_dimensions['E'].width = 18
                
        except Exception as e:
            print(f"خطا در ایجاد شیت نتایج برش: {e}")
            traceback.print_exc()
        
        # تنظیم مسیر فایل خروجی
        export_dir = "static/exports"
        if not os.path.exists(export_dir):
            os.makedirs(export_dir)
        
        timestamp = get_shamsi_timestamp()  # تاریخ شمسی
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

    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("پروژه مورد نظر یافت نشد.", "error")
        return redirect(url_for("index"))

    doors = get_doors_for_project_db(project_id)
    if not doors:
        flash("هیچ دربی برای این پروژه ثبت نشده است.", "warning")
        return redirect(url_for("view_project", project_id=project_id))

    # --- جمع‌آوری قطعات مورد نیاز به تفکیک نوع پروفیل ---
    profile_requirements = {}  # {profile_name: [(length, count), ...]}

    valid_rows = 0
    for door in doors:
        try:
            width = float(door["width"])
            height = float(door["height"])
            quantity = int(door["quantity"])
            profile_type = door.get("noe_profile", "پیش‌فرض")  # نوع پروفیل از ستون سفارشی

            if width <= 0 or height <= 0 or quantity <= 0:
                continue  # رد کردن داده‌های نامعتبر

            if profile_type not in profile_requirements:
                profile_requirements[profile_type] = []

            # دو قطعه عمودی برای هر درب
            profile_requirements[profile_type].append((height, quantity * 2))
            # یک قطعه افقی برای هر درب
            profile_requirements[profile_type].append((width, quantity * 1))

            valid_rows += 1

        except (ValueError, TypeError, KeyError) as e:
            print(f"خطا در پردازش درب {door.get('id')}: {e}")
            continue

    if not profile_requirements:
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

    # --- دریافت تنظیمات استفاده از انبار ---
    settings = get_inventory_settings()
    use_inventory = settings.get('use_inventory_for_cutting', False)
    prefer_pieces = settings.get('prefer_inventory_pieces', False)
    
    # --- دریافت min_waste برای هر پروفیل ---
    profiles = get_all_profile_types()
    profile_min_waste = {}  # {profile_name: min_waste}
    for p in profiles:
        profile_min_waste[p['name']] = float(p.get('min_waste', 70))
    
    # --- محاسبه برش برای هر نوع پروفیل ---
    results_by_profile = {}
    all_bins = []  # برای نمایش کلی (سازگاری با template فعلی)
    used_inventory_pieces = {}  # {profile_type: [piece_ids]} برای ردیابی قطعات استفاده شده
    
    for profile_type, required_pieces in profile_requirements.items():
        bins = []
        used_pieces_for_profile = []  # لیست ID قطعات برش‌خورده استفاده شده برای این پروفیل
        
        # دریافت قطعات برش‌خورده موجود در انبار (اگر تنظیمات فعال باشد)
        available_inventory_pieces = []
        if use_inventory:
            available_inventory_pieces = get_available_inventory_pieces(profile_type)
            # ایجاد یک کپی برای استفاده (تا بتوانیم از آن کم کنیم)
            available_inventory_pieces = available_inventory_pieces.copy()
        
        # تبدیل به لیست صاف
        flat_pieces = []
        for length, count in required_pieces:
            flat_pieces.extend([length] * count)
        
        # مرتب‌سازی نزولی براساس طول
        sorted_pieces = sorted(flat_pieces, reverse=True)
        
        for piece_length in sorted_pieces:
            if piece_length > STOCK_LENGTH:
                flash(
                    f"امکان برش قطعه‌ای به طول {piece_length}cm از شاخه {STOCK_LENGTH}cm وجود ندارد! (پروفیل: {profile_type})",
                    "error",
                )
                return redirect(url_for("view_project", project_id=project_id))
            
            placed = False
            
            # اگر تنظیمات استفاده از قطعات برش‌خورده فعال باشد و اولویت با آن‌ها باشد
            if use_inventory and prefer_pieces and available_inventory_pieces:
                # جستجو در قطعات برش‌خورده موجود
                for idx, inv_piece in enumerate(available_inventory_pieces):
                    if inv_piece['length'] >= piece_length:
                        # استفاده از قطعه برش‌خورده موجود
                        remaining = inv_piece['length'] - piece_length
                        used_pieces_for_profile.append(inv_piece['id'])
                        # حذف این قطعه از لیست موجود (تا دوباره استفاده نشود)
                        available_inventory_pieces.pop(idx)
                        
                        # اضافه کردن bin با قطعه استفاده شده
                        bins.append({
                            "pieces": [piece_length],
                            "remaining": remaining,
                            "profile_type": profile_type,
                            "from_inventory_piece": True,
                            "inventory_piece_id": inv_piece['id'],
                            "initial_length": inv_piece['length']  # طول اولیه برای محاسبات
                        })
                        
                        placed = True
                        break
            
            # اگر هنوز جای داده نشده، سعی در قرار دادن در شاخه‌های موجود (bins)
            if not placed:
                for bin_data in bins:
                    if bin_data["remaining"] >= piece_length:
                        bin_data["pieces"].append(piece_length)
                        bin_data["remaining"] -= piece_length
                        placed = True
                        break
            
            # اگر در هیچ شاخه‌ای جا نشد، یک شاخه جدید ایجاد کن
            if not placed:
                bins.append({
                    "pieces": [piece_length],
                    "remaining": STOCK_LENGTH - piece_length,
                    "profile_type": profile_type,
                    "from_inventory_piece": False,
                    "initial_length": STOCK_LENGTH  # طول اولیه برای محاسبات
                })
        
        # ذخیره لیست قطعات استفاده شده برای این پروفیل
        if used_pieces_for_profile:
            used_inventory_pieces[profile_type] = used_pieces_for_profile
        
        results_by_profile[profile_type] = {
            "bins": bins,
            "total_bins": len(bins)
        }
        
        # اضافه کردن min_waste به هر bin برای استفاده در محاسبات بعدی
        min_waste_for_profile = profile_min_waste.get(profile_type, 70)
        for bin_data in bins:
            bin_data["min_waste"] = min_waste_for_profile
        
        # اضافه کردن به لیست کلی برای نمایش
        all_bins.extend(bins)

    # --- محاسبه آمار کلی ---
    bins = all_bins  # برای سازگاری با کد بعدی
    total_bins_used = len(bins)

    # اطلاعات قطعات کوچک (ضایعات) - استفاده از min_waste هر پروفیل
    small_pieces_info = []
    for i, bin_data in enumerate(bins):
        min_waste_threshold = bin_data.get("min_waste", 70)
        remaining = bin_data["remaining"]
        if 0 < remaining < min_waste_threshold:
            small_pieces_info.append((i + 1, remaining))
    
    small_pieces_count = len(small_pieces_info)
    total_small_waste_length = sum(rem for _, rem in small_pieces_info)
    total_small_waste_weight = (
        total_small_waste_length / 100
    ) * WEIGHT_PER_METER  # تبدیل سانتی‌متر به متر

    # مشاهده اطلاعات ضایعات متوسط و بزرگ برای تحلیل بیشتر - استفاده از min_waste هر پروفیل
    medium_pieces_info = []
    for i, bin_data in enumerate(bins):
        min_waste_threshold = bin_data.get("min_waste", 70)
        remaining = bin_data["remaining"]
        if min_waste_threshold <= remaining < (STOCK_LENGTH / 2):
            medium_pieces_info.append((i + 1, remaining))
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
    # محاسبه طول کل اولیه (با در نظر گرفتن bins برش‌خورده)
    total_initial_length = sum(
        bin_data.get('initial_length', STOCK_LENGTH) for bin_data in bins
    )
    total_waste_percentage = (
        (total_waste_length / total_initial_length) * 100
    ) if total_initial_length > 0 else 0

    # ---------- پیش‌پردازش داده‌ها برای قالب ----------
    # این بخش به منظور جلوگیری از خطای سینتکسی در قالب اضافه شده است

    # گرد کردن مقادیر اصلی
    small_waste_length_rounded = round(total_small_waste_length, 1)
    small_waste_weight_rounded = round(total_small_waste_weight, 2)
    total_waste_percentage_rounded = round(total_waste_percentage, 1)

    # پیش‌پردازش داده‌های شاخه‌ها
    processed_bins = []
    for i, bin_data in enumerate(bins):
        # استفاده از طول اولیه برای محاسبات (STOCK_LENGTH برای bins جدید، initial_length برای bins برش‌خورده)
        initial_length = bin_data.get('initial_length', STOCK_LENGTH)
        used_length = initial_length - bin_data["remaining"]
        used_percent = int((used_length / initial_length) * 100) if initial_length > 0 else 0
        waste_percent = int((bin_data["remaining"] / initial_length) * 100) if initial_length > 0 else 0
        # فرمت‌بندی درصدها به صورت رشته‌ای با % برای CSS
        used_percent_style = f"{used_percent}%"
        waste_percent_style = f"{waste_percent}%"
        # گرد کردن اعداد قطعات
        rounded_pieces = [round(piece, 1) for piece in bin_data["pieces"]]
        
        # استفاده از min_waste پروفیل برای تعیین نوع ضایعات
        min_waste_threshold = bin_data.get("min_waste", 70)
        remaining = bin_data["remaining"]

        # تعیین منبع شاخه
        from_inventory = bin_data.get("from_inventory_piece", False)
        source_text = "از قطعه برش‌خورده موجود در انبار" if from_inventory else "از شاخه جدید 6 متری"
        source_class = "source-inventory" if from_inventory else "source-new"
        
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
                    if remaining < min_waste_threshold
                    else (
                        "medium"
                        if remaining < (STOCK_LENGTH / 2)
                        else "large"
                    )
                ),
                "from_inventory_piece": from_inventory,
                "source_text": source_text,
                "source_class": source_class,
                "initial_length": round(initial_length, 1),  # طول اولیه برای نمایش
            }
        )
    # محاسبه waste_threshold برای نمایش (میانگین min_waste پروفیل‌های استفاده شده)
    if profile_requirements:
        avg_min_waste = sum(profile_min_waste.get(name, 70) for name in profile_requirements.keys()) / len(profile_requirements)
        display_waste_threshold = round(avg_min_waste, 1)
    else:
        display_waste_threshold = 70  # پیش‌فرض
    
    # ذخیره نتایج در session برای استفاده در کسر از انبار
    session[f'cutting_result_{project_id}'] = {
        'profile_requirements': results_by_profile,  # {profile_name: {bins: [], total_bins: X}}
        'stock_length': STOCK_LENGTH,
        'timestamp': get_shamsi_datetime_iso(),  # تاریخ شمسی
        'used_inventory_pieces': used_inventory_pieces  # {profile_name: [piece_ids]} - قطعات برش‌خورده استفاده شده
    }
    
    # رندر نتیجه در قالب HTML با مقادیر از پیش محاسبه شده
    return render_template(
        "cutting_result.html",
        project=project_info,
        bins=processed_bins,
        total_bins=total_bins_used,
        stock_length=STOCK_LENGTH,
        waste_threshold=display_waste_threshold,
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


@app.route("/project/<int:project_id>/apply_cutting_plan", methods=["POST"])
def apply_cutting_plan(project_id):
    """
    اعمال طرح برش در انبار - کسر خودکار بر اساس نوع پروفیل درب‌ها
    """
    # دریافت اطلاعات پروژه
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("پروژه مورد نظر یافت نشد.", "error")
        return redirect(url_for("index"))
    
    # ⭐ بررسی اینکه آیا این پروژه قبلاً کسر شده یا نه
    if check_if_already_deducted(project_id):
        existing_deductions = get_project_deductions(project_id)
        deduction_details = "<br>".join([
            f"• {d['profile_name']}: {d['quantity_deducted']} شاخه در تاریخ {d['deduction_date']}"
            for d in existing_deductions
        ])
        flash(
            f"⚠️ این پروژه قبلاً از انبار کسر شده است!<br><br><strong>جزئیات کسرهای قبلی:</strong><br>{deduction_details}",
            "warning"
        )
        return redirect(url_for("view_project", project_id=project_id))
    
    # بررسی وجود نتایج محاسبه در session
    cutting_data = session.get(f'cutting_result_{project_id}')
    if not cutting_data:
        flash("ابتدا باید محاسبه برش را انجام دهید.", "warning")
        return redirect(url_for("calculate_cutting", project_id=project_id))
    
    profile_requirements = cutting_data.get('profile_requirements', {})
    used_inventory_pieces = cutting_data.get('used_inventory_pieces', {})  # {profile_name: [piece_ids]}
    
    if not profile_requirements:
        flash("اطلاعات پروفیل‌های مورد نیاز یافت نشد.", "error")
        return redirect(url_for("calculate_cutting", project_id=project_id))
    
    # لیست خطاها و موفقیت‌ها
    errors = []
    success_messages = []
    total_deducted = {}
    
    try:
        # برای هر نوع پروفیل
        for profile_name, profile_data in profile_requirements.items():
            bins_data = profile_data.get('bins', [])
            
            # پیدا کردن profile_id و min_waste از انبار بر اساس نام
            profiles = get_all_profile_types()
            profile_id = None
            min_waste_threshold = 70  # پیش‌فرض در صورت عدم دسترسی
            
            for p in profiles:
                if p['name'] == profile_name:
                    profile_id = p['id']
                    # خواندن حداقل ضایعات از تنظیمات پروفیل
                    min_waste_threshold = float(p.get('min_waste', 70))
                    break
            
            # اگر پروفیل در انبار تعریف نشده
            if not profile_id:
                errors.append(f"⚠️ پروفیل '{profile_name}' در انبار تعریف نشده است. لطفاً ابتدا آن را در مدیریت انبار اضافه کنید.")
                continue
            
            # حذف قطعات برش‌خورده استفاده شده از انبار
            pieces_removed = 0
            if profile_name in used_inventory_pieces:
                # دریافت نام و کد پروژه فعلی برای استفاده در description
                current_project_name = project_info.get('customer_name', f'پروژه {project_id}')
                current_project_code = project_info.get('project_code', None)
                current_project_display = f"{current_project_name} ({current_project_code})" if current_project_code else current_project_name
                
                for piece_id in used_inventory_pieces[profile_name]:
                    # تلاش برای یافتن نام پروژه قبلی که این قطعه از آن آمده
                    source_project_name = None
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        # یافتن آخرین لاگ add_piece برای این قطعه و دریافت project_id و نام پروژه
                        cursor.execute("""
                            SELECT il.project_id, p.customer_name, p.project_code, il.description
                            FROM inventory_logs il
                            LEFT JOIN projects p ON il.project_id = p.id
                            WHERE il.piece_id = ? AND il.change_type = 'add_piece'
                            ORDER BY il.timestamp DESC
                            LIMIT 1
                        """, (piece_id,))
                        row = cursor.fetchone()
                        if row:
                            # اولویت با نام پروژه از جدول projects (با کد)
                            source_project_code = row['project_code'] if row['project_code'] else None
                            if row['customer_name']:
                                source_project_name = f"{row['customer_name']} ({source_project_code})" if source_project_code else row['customer_name']
                            elif row['project_id']:
                                source_project_name = f'پروژه {row["project_id"]}' + (f" ({source_project_code})" if source_project_code else "")
                            # اگر project_id نداشت، از description استخراج کن
                            elif row['description']:
                                desc = row['description']
                                if "از پروژه '" in desc:
                                    try:
                                        start = desc.index("از پروژه '") + len("از پروژه '")
                                        end = desc.index("'", start)
                                        source_project_name = desc[start:end]
                                    except ValueError:
                                        pass
                        conn.close()
                    except Exception as e:
                        print(f"خطا در یافتن نام پروژه قبلی برای قطعه {piece_id}: {e}")
                    
                    # ایجاد description با نام پروژه‌ها
                    if source_project_name:
                        description = f"استفاده شده در پروژه '{current_project_display}' - قبلاً از پروژه '{source_project_name}'"
                    else:
                        description = f"استفاده شده در پروژه '{current_project_display}'"
                    
                    success_remove, msg_remove = remove_inventory_piece(
                        piece_id,
                        description=description,
                        project_id=project_id
                    )
                    if success_remove:
                        pieces_removed += 1
                    else:
                        errors.append(f"⚠️ خطا در حذف قطعه برش‌خورده {piece_id} از '{profile_name}': {msg_remove}")
            
            # محاسبه تعداد bins جدید (نه bins هایی که از قطعات برش‌خورده استفاده کرده‌اند)
            new_bins_count = sum(
                1 for bin_data in bins_data
                if not bin_data.get('from_inventory_piece', False)
            )
            
            if new_bins_count == 0:
                # فقط قطعات برش‌خورده استفاده شده، نیاز به کسر شاخه جدید نیست
                if pieces_removed > 0:
                    success_messages.append(
                        f"✓ {profile_name}: {pieces_removed} قطعه برش‌خورده استفاده شد"
                    )
                continue
            
            # بررسی موجودی برای شاخه‌های جدید
            stock_details = get_profile_stock_details(profile_id)
            current_stock = stock_details.get("complete_pieces", 0)
            
            if current_stock < new_bins_count:
                errors.append(f"⚠️ موجودی '{profile_name}' کافی نیست! نیاز: {new_bins_count} شاخه جدید، موجودی: {current_stock} شاخه")
                continue
            
            # کسر شاخه‌های جدید از انبار
            description = f"کسر بابت پروژه: {project_info.get('customer_name', 'نامشخص')} - محاسبه برش"
            success, msg = remove_inventory_stock(
                profile_id, 
                new_bins_count, 
                description=description,
                project_id=project_id
            )
            
            if success:
                total_deducted[profile_name] = new_bins_count
                
                # افزودن تکه‌های باقی‌مانده از شاخه‌های جدید به انبار بر اساس min_waste پروفیل
                added_pieces = 0
                discarded_pieces = 0
                for bin_data in bins_data:
                    # فقط bins جدید (نه bins هایی که از قطعات برش‌خورده استفاده کرده‌اند)
                    if not bin_data.get('from_inventory_piece', False):
                        remaining = bin_data.get('remaining', 0)
                        # استفاده از حداقل ضایعات تعریف‌شده برای این پروفیل
                        if remaining > min_waste_threshold:
                            # استفاده از نام پروژه در description
                            project_name = project_info.get('customer_name', f'پروژه {project_id}')
                            if add_inventory_piece(profile_id, remaining, f"باقی‌مانده از پروژه '{project_name}'", project_id=project_id):
                                added_pieces += 1
                        elif remaining > 0:
                            discarded_pieces += 1
                
                msg_parts = []
                if new_bins_count > 0:
                    msg_parts.append(f"{new_bins_count} شاخه کسر شد")
                if pieces_removed > 0:
                    msg_parts.append(f"{pieces_removed} قطعه برش‌خورده استفاده شد")
                if added_pieces > 0:
                    msg_parts.append(f"{added_pieces} تکه (>{min_waste_threshold:.0f}cm) به انبار برگشت")
                if discarded_pieces > 0:
                    msg_parts.append(f"{discarded_pieces} تکه پرت شد")
                
                success_messages.append(f"✓ {profile_name}: {', '.join(msg_parts)}")
            else:
                errors.append(f"⚠️ خطا در کسر '{profile_name}': {msg}")
        
        # نمایش نتایج
        if success_messages:
            flash("<br>".join(success_messages), "success")
        
        if errors:
            flash("<br>".join(errors), "error")
        
        # اگر حداقل یک پروفیل موفق کسر شد، session رو پاک کن
        if total_deducted:
            session.pop(f'cutting_result_{project_id}', None)
        
        return redirect(url_for("view_project", project_id=project_id))
        
    except Exception as e:
        print(f"!!!!!! Error in apply_cutting_plan: {e}")
        traceback.print_exc()
        flash(f"خطا در اعمال طرح برش: {str(e)}", "error")
        return redirect(url_for("calculate_cutting", project_id=project_id))





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
    
    # تابع ensure_default_custom_columns() حذف شد - مایگریشن 002 این کار را انجام می‌دهد
    
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
@staff_or_admin_required
def apply_batch_edit(project_id):
    """اعمال تغییرات گروهی روی درب‌های انتخاب شده"""
    
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

    # 🔄 بکاپ خودکار قبل از ویرایش گروهی
    print(f"ایجاد بکاپ خودکار قبل از ویرایش گروهی پروژه {project_id}...")
    backup_success, backup_result = backup_manager.create_backup(
        reason=f"before_batch_edit",
        user="system",
        metadata={"project_id": project_id, "action": "batch_edit", "door_count": len(door_ids)}
    )
    if backup_success:
        print(f"✓ بکاپ قبل از ویرایش گروهی ایجاد شد: {backup_result}")
    else:
        print(f"⚠ خطا در ایجاد بکاپ (ادامه می‌دهیم): {backup_result}")

    # اعمال تغییرات روی درب‌های انتخاب شده
    successful_updates, failed_updates, success_messages, error_messages = batch_update_doors_db(
        door_ids, base_fields_to_update, columns_to_update
    )
    
    # به‌روزرسانی ستون‌های قابل مشاهده بر اساس داده‌های جدید
    if successful_updates > 0:
        refresh_project_visible_columns(project_id)

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
        # دریافت آمار واقعی از دیتابیس
        stats = get_inventory_stats()
        
        # دریافت لیست پروفیل‌ها برای نمایش در داشبورد
        profiles = get_all_profile_types()
        
        return render_template("inventory_dashboard.html", stats=stats, profiles=profiles)
    except Exception as e:
        print(f"!!!!!! Unexpected error in inventory_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه مدیریت انبار رخ داد.", "error")
        return redirect(url_for("index"))


@app.route("/inventory/profile_types")
def profile_types_route():
    """صفحه مدیریت انواع پروفیل"""
    try:
        # دریافت لیست انواع پروفیل از دیتابیس
        profile_types = get_all_profile_types()
        
        return render_template("profile_types.html", profile_types=profile_types)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت profile_types_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه انواع پروفیل رخ داد.", "error")
        return redirect(url_for("inventory_route"))

@app.route("/inventory/profile_types/add", methods=["GET", "POST"])
def add_profile_type_route():
    """افزودن نوع پروفیل جدید"""
    try:
        if request.method == "POST":
            name = request.form.get("name")
            color = request.form.get("color_hex") or request.form.get("color")
            default_length = float(request.form.get("default_length") or 600)
            weight_per_meter = float(request.form.get("weight_per_meter") or 1.9)
            min_waste = float(request.form.get("min_waste") or 20)
            description = request.form.get("description")
            
            if not name:
                flash("نام پروفیل الزامی است.", "error")
                return render_template("add_profile_type.html")
            
            success, result = add_profile_type(name, description, default_length, weight_per_meter, color, min_waste)
            
            if success:
                flash("نوع پروفیل با موفقیت اضافه شد.", "success")
                return redirect(url_for("profile_types_route"))
            else:
                # result already contains a user-friendly Persian message
                flash(result, "error")
        
        return render_template("add_profile_type.html")
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت add_profile_type_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه افزودن پروفیل رخ داد.", "error")
        return redirect(url_for("profile_types_route"))

@app.route("/inventory/profile_types/edit/<int:profile_id>", methods=["GET", "POST"])
def edit_profile_type_route(profile_id):
    """ویرایش نوع پروفیل"""
    try:
        profile = get_profile_details(profile_id)
        if not profile:
            flash("پروفیل مورد نظر یافت نشد.", "error")
            return redirect(url_for("profile_types_route"))

        if request.method == "POST":
            name = request.form.get("name")
            color = request.form.get("color_hex") or request.form.get("color")
            default_length = float(request.form.get("default_length") or 600)
            weight_per_meter = float(request.form.get("weight_per_meter") or 1.9)
            min_waste = float(request.form.get("min_waste") or 20)
            description = request.form.get("description")
            
            if not name:
                flash("نام پروفیل الزامی است.", "error")
                return render_template("edit_profile_type.html", profile=profile)
            
            # در اینجا باید تابع ویرایش را فراخوانی کنیم
            success = update_profile_type(profile_id, name, description, default_length, weight_per_meter, color, min_waste)
            
            if success:
                flash("پروفیل با موفقیت ویرایش شد.", "success")
                return redirect(url_for("profile_types_route"))
            else:
                flash("خطا در ویرایش پروفیل.", "error")
        
        return render_template("edit_profile_type.html", profile=profile)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت edit_profile_type_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه ویرایش پروفیل رخ داد.", "error")
        return redirect(url_for("profile_types_route"))

@app.route("/inventory/profile_types/delete/<int:profile_id>", methods=["POST"])
def delete_profile_type_route(profile_id):
    """حذف نوع پروفیل"""
    try:
        success = delete_profile_type(profile_id)
        if success:
            flash("پروفیل با موفقیت حذف شد.", "success")
        else:
            flash("خطا در حذف پروفیل.", "error")
        return redirect(url_for("profile_types_route"))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت delete_profile_type_route: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات حذف رخ داد.", "error")
        return redirect(url_for("profile_types_route"))


@app.route("/inventory/settings", methods=["GET", "POST"])
def inventory_settings_route():
    """صفحه تنظیمات انبار"""
    try:
        if request.method == "POST":
            # دریافت تنظیمات از فرم و ذخیره در دیتابیس
            new_settings = {
                "default_wastage": request.form.get("default_wastage", 20),
                "min_remaining_length": request.form.get("min_remaining_length", 20),
                "use_inventory_for_cutting": request.form.get("use_inventory_for_cutting") == "on",
                "prefer_inventory_pieces": request.form.get("prefer_inventory_pieces") == "on",
                "inventory_optimization_strategy": request.form.get("inventory_optimization_strategy", "minimize_waste"),
                "show_inventory_warnings": request.form.get("show_inventory_warnings") == "on",
                "low_inventory_threshold": request.form.get("low_inventory_threshold", 5)
            }
            
            if update_inventory_settings(new_settings):
                flash("تنظیمات انبار با موفقیت ذخیره شد.", "success")
            else:
                flash("خطا در ذخیره تنظیمات.", "error")
            
            return redirect(url_for("inventory_settings_route"))

        # دریافت تنظیمات فعلی از دیتابیس
        settings = get_inventory_settings()
        
        # اگر تنظیمات خالی بود (هنوز ست نشده)، مقادیر پیش‌فرض را نمایش بده
        if not settings:
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
@app.route("/inventory/logs/<int:profile_id>")
def inventory_logs_route(profile_id=None):
    """صفحه تاریخچه تغییرات انبار"""
    try:
        logs = get_inventory_logs(limit=100, profile_id=profile_id)
        
        # افزودن ترجمه نوع تغییر
        change_type_map = {
            "add_stock": "افزایش موجودی",
            "remove_stock": "کاهش موجودی",
            "add_piece": "افزودن تکه",
            "remove_piece": "حذف تکه"
        }
        
        logs_with_translation = []
        for log in logs:
            log_dict = dict(log)
            log_dict["change_type_fa"] = change_type_map.get(log_dict["change_type"], log_dict["change_type"])
            logs_with_translation.append(log_dict)
            
        return render_template("inventory_logs.html", logs=logs_with_translation, profile_id=profile_id)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory_logs_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش تاریخچه رخ داد.", "error")
        return redirect(url_for("inventory_route"))

@app.route("/inventory/details/<int:profile_id>")
def inventory_details_route(profile_id):
    """صفحه جزئیات موجودی یک پروفیل"""
    try:
        profile = get_profile_details(profile_id)
        if not profile:
            flash("پروفیل مورد نظر یافت نشد.", "error")
            return redirect(url_for("inventory_route"))
            
        details = get_profile_stock_details(profile_id)
        
        # سازماندهی داده‌ها برای قالب
        template_details = {
            "profile": profile,
            "full_items": details["complete_pieces"],
            "pieces": details["pieces"],
            "logs": details["logs"]
        }
        
        # افزودن ترجمه نوع تغییر به لاگ‌ها
        change_type_map = {
            "add_stock": "افزایش موجودی",
            "remove_stock": "کاهش موجودی",
            "add_piece": "افزودن تکه",
            "remove_piece": "حذف تکه"
        }
        
        logs_with_translation = []
        for log in details["logs"]:
            log_dict = dict(log)
            log_dict["change_type_fa"] = change_type_map.get(log_dict["change_type"], log_dict["change_type"])
            logs_with_translation.append(log_dict)
            
        return render_template("profile_inventory_details.html", details=template_details, logs=logs_with_translation)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory_details_route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه جزئیات انبار رخ داد.", "error")
        return redirect(url_for("profile_types_route"))

@app.route("/inventory/items/add/<int:profile_id>", methods=["POST"])
def add_inventory_items_route(profile_id):
    """افزودن شاخه کامل به انبار"""
    try:
        quantity = int(request.form.get("quantity", 0))
        description = request.form.get("description", "")
        
        if quantity <= 0:
            flash("تعداد باید بزرگتر از صفر باشد.", "error")
        else:
            if add_inventory_stock(profile_id, quantity, description):
                flash("موجودی با موفقیت اضافه شد.", "success")
            else:
                flash("خطا در افزودن موجودی.", "error")
                
        return redirect(url_for("inventory_details_route", profile_id=profile_id))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت add_inventory_items_route: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات رخ داد.", "error")
        return redirect(url_for("inventory_details_route", profile_id=profile_id))

@app.route("/inventory/items/remove/<int:profile_id>", methods=["POST"])
def remove_inventory_items_route(profile_id):
    """کاهش شاخه کامل از انبار"""
    try:
        quantity = int(request.form.get("quantity", 0))
        description = request.form.get("description", "")
        
        if quantity <= 0:
            flash("تعداد باید بزرگتر از صفر باشد.", "error")
        else:
            # 🔄 بکاپ خودکار قبل از کسر موجودی انبار
            print(f"ایجاد بکاپ خودکار قبل از کسر موجودی انبار (profile_id={profile_id})...")
            backup_success, backup_result = backup_manager.create_backup(
                reason=f"before_inventory_deduction",
                user="system",
                metadata={"profile_id": profile_id, "action": "remove_stock", "quantity": quantity}
            )
            if backup_success:
                print(f"✓ بکاپ قبل از کسر موجودی ایجاد شد: {backup_result}")
            else:
                print(f"⚠ خطا در ایجاد بکاپ (ادامه می‌دهیم): {backup_result}")
            
            success, msg = remove_inventory_stock(profile_id, quantity, description)
            if success:
                flash("موجودی با موفقیت کسر شد.", "success")
            else:
                flash(f"خطا در کسر موجودی: {msg}", "error")
                
        return redirect(url_for("inventory_details_route", profile_id=profile_id))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت remove_inventory_items_route: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات رخ داد.", "error")
        return redirect(url_for("inventory_details_route", profile_id=profile_id))

@app.route("/inventory/pieces/add/<int:profile_id>", methods=["POST"])
def add_inventory_piece_route(profile_id):
    """افزودن تکه شاخه به انبار"""
    try:
        length = float(request.form.get("length", 0))
        description = request.form.get("description", "")
        
        if length <= 0:
            flash("طول باید بزرگتر از صفر باشد.", "error")
        else:
            if add_inventory_piece(profile_id, length, description):
                flash("تکه شاخه با موفقیت اضافه شد.", "success")
            else:
                flash("خطا در افزودن تکه شاخه.", "error")
                
        return redirect(url_for("inventory_details_route", profile_id=profile_id))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت add_inventory_piece_route: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات رخ داد.", "error")
        return redirect(url_for("inventory_details_route", profile_id=profile_id))

@app.route("/inventory/pieces/remove/<int:piece_id>", methods=["POST"])
def remove_inventory_piece_route(piece_id):
    """حذف تکه شاخه از انبار"""
    try:
        profile_id = request.form.get("profile_id")
        
        success, msg = remove_inventory_piece(piece_id, description="حذف دستی توسط کاربر")
        if success:
            flash("تکه شاخه با موفقیت حذف شد.", "success")
        else:
            flash(f"خطا در حذف تکه شاخه: {msg}", "error")
            
        if profile_id:
            return redirect(url_for("inventory_details_route", profile_id=profile_id))
        return redirect(url_for("inventory_route"))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت remove_inventory_piece_route: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات رخ داد.", "error")
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
    return redirect(url_for("manage_custom_columns", project_id=project_id))

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
    return redirect(url_for("manage_custom_columns", project_id=project_id))


@app.route("/project/<int:project_id>/update_column_display", methods=["POST"])
def update_column_display(project_id):
    """به‌روزرسانی تنظیمات نمایش ستون‌ها (برای سازگاری با قبل)"""
    # ریدایرکت به روت جدید
    return redirect(url_for("manage_custom_columns", project_id=project_id))


@app.route("/column/<int:column_id>/delete/<int:project_id>", methods=["GET"])
def delete_column_route(column_id, project_id):
    """حذف ستون سفارشی (برای سازگاری با قبل)"""
    # ذخیره اطلاعات در session برای انتقال به روت جدید
    session['temp_column_data'] = {
        'column_id': column_id,
        'action': 'delete_column'
    }
    
    # ریدایرکت به روت جدید
    return redirect(url_for("manage_custom_columns", project_id=project_id))


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
        conn = get_db_connection()
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
        # دریافت شناسه پروژه برای بازگشت (در صورت وجود)
        # ممکن است در query string یا form data باشد
        project_id = request.args.get("project_id") or request.form.get("project_id")
        
        # بررسی وجود اطلاعات در session (برای سازگاری با روت‌های قدیمی)
        temp_data = session.pop('temp_column_data', None)
        
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
                return redirect(url_for("manage_custom_columns", project_id=project_id))
            
            if column_type not in ['text', 'dropdown']:
                flash("نوع ستون انتخاب شده نامعتبر است. لطفاً 'متنی' یا 'دراپ‌داون' را انتخاب کنید.", "error")
                return redirect(url_for("manage_custom_columns", project_id=project_id))
            
            # چک کردن اینکه آیا ستون با این کلید قبلاً وجود دارد
            existing_column_id = get_column_id_by_key(column_key)
            if existing_column_id:
                flash("ستونی با این کلید قبلاً وجود دارد.", "error")
                return redirect(url_for("manage_custom_columns", project_id=project_id))
            
            # افزودن ستون جدید
            new_column_id = add_custom_column(column_key, display_name, column_type)
            if new_column_id:
                flash(f"ستون '{display_name}' با موفقیت اضافه شد.", "success")
            else:
                flash("خطا در افزودن ستون جدید.", "error")
            return redirect(url_for("manage_custom_columns", project_id=project_id))
        
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
                    conn = get_db_connection()
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
            return redirect(url_for("manage_custom_columns", project_id=project_id))
        
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
            return redirect(url_for("manage_custom_columns", project_id=project_id))
        
        # پردازش درخواست GET (نمایش صفحه)
        all_columns = get_all_custom_columns()
        
        column_type_display_map = {
            'text': 'متنی',
            'dropdown': 'دراپ‌داون'
        }
        processed_columns = []
        for col in all_columns:
            col_copy = col.copy() 
            col_copy['type_display'] = column_type_display_map.get(col_copy.get('type'), col_copy.get('type', 'نامشخص'))
            if col_copy.get('type') == 'dropdown':
                col_copy['options'] = get_custom_column_options(col_copy['id'])
            else:
                col_copy['options'] = []
            processed_columns.append(col_copy)
        
        return render_template(
            "column_settings.html",
            all_columns=processed_columns,
            project_id=project_id
        )
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت manage_custom_columns: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه تنظیمات ستون‌ها رخ داد.", "error")
        return redirect(url_for("index"))

@app.route("/project/<int:project_id>/settings_combos", methods=["GET"])
def settings_combos(project_id):
    """صفحه مدیریت گزینه‌های کمبوباکس (dropdown) برای پروژه"""
    try:
        # دریافت اطلاعات پروژه
        project_info = get_project_details_db(project_id)
        if not project_info:
            flash("پروژه مورد نظر یافت نشد.", "error")
            return redirect(url_for("index"))
        
        # دریافت تمام ستون‌های dropdown
        all_columns = get_all_custom_columns()
        dropdown_columns = [col for col in all_columns if col.get('type') == 'dropdown']
        
        return render_template(
            "settings_combos.html",
            project=project_info,
            columns=dropdown_columns
        )
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت settings_combos: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه مدیریت گزینه‌ها رخ داد.", "error")
        return redirect(url_for("project_treeview", project_id=project_id))

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
        column_type = get_column_type_db(column_id)
        
        if not column_type:
            return jsonify({"success": False, "error": "ستون مورد نظر یافت نشد"}), 404
        
        if column_type != 'dropdown':
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
        column_id = get_column_id_from_option_db(option_id)
        
        if not column_id:
            return jsonify({"success": False, "error": "گزینه مورد نظر یافت نشد"}), 404
            
        # حذف گزینه با استفاده از تابع موجود
        success = delete_column_option(option_id)
        
        if success:
            return jsonify({"success": True, "message": "گزینه با موفقیت حذف شد", "column_id": column_id})
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
        column_id = get_column_id_from_option_db(option_id)
        
        if not column_id:
            return jsonify({"success": False, "error": "گزینه مورد نظر یافت نشد"}), 404
        
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
@admin_required
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
                # price_settings table is created by migration 003_create_price_settings
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
            # price_settings table is created by migration 003_create_price_settings
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

# ============================================================================
# مدیریت بکاپ (Backup Management Routes)
# ============================================================================

@app.route("/backup")
def backup_management():
    """صفحه مدیریت بکاپ"""
    try:
        backups = backup_manager.list_backups()
        stats = backup_manager.get_backup_stats()
        
        return render_template(
            "backup_manager.html",
            backups=backups,
            stats=stats,
            message=session.pop('backup_message', None),
            message_type=session.pop('backup_message_type', None)
        )
    except Exception as e:
        print(f"خطا در صفحه مدیریت بکاپ: {e}")
        traceback.print_exc()
        flash("خطا در بارگذاری صفحه مدیریت بکاپ", "error")
        return redirect(url_for("index"))

@app.route("/backup/create")
def backup_create():
    """ایجاد بکاپ دستی"""
    try:
        success, result = backup_manager.create_backup(
            reason="manual_backup",
            user="admin",
            metadata={"source": "web_interface"}
        )
        
        if success:
            session['backup_message'] = f"بکاپ با موفقیت ایجاد شد."
            session['backup_message_type'] = "success"
        else:
            session['backup_message'] = f"خطا در ایجاد بکاپ: {result}"
            session['backup_message_type'] = "error"
            
    except Exception as e:
        print(f"خطا در ایجاد بکاپ: {e}")
        traceback.print_exc()
        session['backup_message'] = f"خطا در ایجاد بکاپ: {str(e)}"
        session['backup_message_type'] = "error"
    
    return redirect(url_for("backup_management"))

@app.route("/backup/restore/<filename>")
def backup_restore(filename):
    """بازگردانی از بکاپ"""
    try:
        success, message = backup_manager.restore_backup(filename, create_pre_restore_backup=True)
        
        if success:
            session['backup_message'] = "دیتابیس با موفقیت بازگردانی شد. رمز عبور admin به 'admin' بازنشانی شد. لطفاً برنامه را مجدداً راه‌اندازی کنید."
            session['backup_message_type'] = "success"
        else:
            session['backup_message'] = f"خطا در بازگردانی: {message}"
            session['backup_message_type'] = "error"
            
    except Exception as e:
        print(f"خطا در بازگردانی بکاپ: {e}")
        traceback.print_exc()
        session['backup_message'] = f"خطا در بازگردانی: {str(e)}"
        session['backup_message_type'] = "error"
    
    return redirect(url_for("backup_management"))

@app.route("/backup/delete/<filename>")
def backup_delete(filename):
    """حذف بکاپ"""
    try:
        success, message = backup_manager.delete_backup(filename)
        
        if success:
            session['backup_message'] = "بکاپ با موفقیت حذف شد."
            session['backup_message_type'] = "success"
        else:
            session['backup_message'] = f"خطا در حذف بکاپ: {message}"
            session['backup_message_type'] = "error"
            
    except Exception as e:
        print(f"خطا در حذف بکاپ: {e}")
        traceback.print_exc()
        session['backup_message'] = f"خطا در حذف: {str(e)}"
        session['backup_message_type'] = "error"
    
    return redirect(url_for("backup_management"))

@app.route("/backup/download/<filename>")
def backup_download(filename):
    """دانلود فایل بکاپ"""
    try:
        success, file_path = backup_manager.download_backup(filename)
        
        if success:
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            session['backup_message'] = file_path  # error message
            session['backup_message_type'] = "error"
            return redirect(url_for("backup_management"))
            
    except Exception as e:
        print(f"خطا در دانلود بکاپ: {e}")
        traceback.print_exc()
        session['backup_message'] = f"خطا در دانلود: {str(e)}"
        session['backup_message_type'] = "error"
        return redirect(url_for("backup_management"))

@app.route("/backup/cleanup")
def backup_cleanup():
    """پاکسازی بکاپ‌های قدیمی (بیشتر از 7 روز)"""
    try:
        deleted_count = backup_manager.cleanup_old_backups(retention_days=7)
        
        if deleted_count > 0:
            session['backup_message'] = f"{deleted_count} بکاپ قدیمی حذف شد."
            session['backup_message_type'] = "success"
        else:
            session['backup_message'] = "هیچ بکاپ قدیمی برای حذف وجود ندارد."
            session['backup_message_type'] = "warning"
            
    except Exception as e:
        print(f"خطا در پاکسازی بکاپ‌ها: {e}")
        traceback.print_exc()
        session['backup_message'] = f"خطا در پاکسازی: {str(e)}"
        session['backup_message_type'] = "error"
    
    return redirect(url_for("backup_management"))

# افزودن کد راه‌اندازی Flask در انتهای فایل
if __name__ == "__main__":
    # Set UTF-8 encoding for Windows
    import sys
    import io
    if sys.platform == 'win32':
        # Try to set UTF-8 for stdout/stderr
        try:
            if hasattr(sys.stdout, 'buffer'):
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'buffer'):
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except:
            pass
    
    # Set environment variable for Werkzeug
    import os
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    # تابع ensure_default_custom_columns() حذف شد چون مایگریشن 002 این کار را انجام می‌دهد
    # اگر این تابع قبل از مایگریشن اجرا شود، ستون‌ها را بدون column_type اضافه می‌کند
    # همه ستون‌های پیش‌فرض اکنون به درستی به عنوان dropdown تنظیم شده‌اند
    
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=True)
