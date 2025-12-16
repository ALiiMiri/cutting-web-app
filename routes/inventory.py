# Inventory Blueprint - routes/inventory.py
# This module contains all inventory-related routes

from flask import Blueprint, render_template, request, redirect, url_for, flash
import traceback

from database import (
    get_inventory_stats,
    get_all_profile_types,
    add_profile_type,
    get_profile_details,
    update_profile_type,
    delete_profile_type,
    get_inventory_settings,
    update_inventory_settings,
    get_inventory_logs,
    get_profile_stock_details,
    add_inventory_stock,
    remove_inventory_stock,
    add_inventory_piece,
    remove_inventory_piece,
)

# Create Blueprint
inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')


@inventory_bp.route("")
def dashboard():
    """صفحه اصلی مدیریت انبار"""
    try:
        stats = get_inventory_stats()
        profiles = get_all_profile_types()
        return render_template("inventory_dashboard.html", stats=stats, profiles=profiles)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory dashboard: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه مدیریت انبار رخ داد.", "error")
        return redirect(url_for("index"))


@inventory_bp.route("/profile_types")
def profile_types():
    """صفحه مدیریت انواع پروفیل"""
    try:
        profile_types_list = get_all_profile_types()
        return render_template("profile_types.html", profile_types=profile_types_list)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت profile_types: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه انواع پروفیل رخ داد.", "error")
        return redirect(url_for("inventory.dashboard"))


@inventory_bp.route("/profile_types/add", methods=["GET", "POST"])
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
                return redirect(url_for("inventory.profile_types"))
            else:
                flash(f"خطا در افزودن پروفیل: {result}", "error")
        
        return render_template("add_profile_type.html")
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت add_profile_type: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه افزودن پروفیل رخ داد.", "error")
        return redirect(url_for("inventory.profile_types"))


@inventory_bp.route("/profile_types/edit/<int:profile_id>", methods=["GET", "POST"])
def edit_profile_type_route(profile_id):
    """ویرایش نوع پروفیل"""
    try:
        profile = get_profile_details(profile_id)
        if not profile:
            flash("پروفیل مورد نظر یافت نشد.", "error")
            return redirect(url_for("inventory.profile_types"))

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
            
            success = update_profile_type(profile_id, name, description, default_length, weight_per_meter, color, min_waste)
            
            if success:
                flash("پروفیل با موفقیت ویرایش شد.", "success")
                return redirect(url_for("inventory.profile_types"))
            else:
                flash("خطا در ویرایش پروفیل.", "error")
        
        return render_template("edit_profile_type.html", profile=profile)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت edit_profile_type: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه ویرایش پروفیل رخ داد.", "error")
        return redirect(url_for("inventory.profile_types"))


@inventory_bp.route("/profile_types/delete/<int:profile_id>", methods=["POST"])
def delete_profile_type_route(profile_id):
    """حذف نوع پروفیل"""
    try:
        success = delete_profile_type(profile_id)
        if success:
            flash("پروفیل با موفقیت حذف شد.", "success")
        else:
            flash("خطا در حذف پروفیل.", "error")
        return redirect(url_for("inventory.profile_types"))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت delete_profile_type: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات حذف رخ داد.", "error")
        return redirect(url_for("inventory.profile_types"))


@inventory_bp.route("/settings", methods=["GET", "POST"])
def settings():
    """صفحه تنظیمات انبار"""
    try:
        if request.method == "POST":
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
            
            return redirect(url_for("inventory.settings"))

        settings_data = get_inventory_settings()
        
        if not settings_data:
            settings_data = {
                "waste_threshold": 70,
                "use_inventory": True,
                "prefer_pieces": True
            }
        
        return render_template("inventory_settings.html", settings=settings_data)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory_settings: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه تنظیمات انبار رخ داد.", "error")
        return redirect(url_for("inventory.dashboard"))


@inventory_bp.route("/logs")
@inventory_bp.route("/logs/<int:profile_id>")
def logs(profile_id=None):
    """صفحه تاریخچه تغییرات انبار"""
    try:
        logs_list = get_inventory_logs(limit=100, profile_id=profile_id)
        
        change_type_map = {
            "add_stock": "افزایش موجودی",
            "remove_stock": "کاهش موجودی",
            "add_piece": "افزودن تکه",
            "remove_piece": "حذف تکه"
        }
        
        logs_with_translation = []
        for log in logs_list:
            log_dict = dict(log)
            log_dict["change_type_fa"] = change_type_map.get(log_dict["change_type"], log_dict["change_type"])
            logs_with_translation.append(log_dict)
            
        return render_template("inventory_logs.html", logs=logs_with_translation, profile_id=profile_id)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory_logs: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش تاریخچه رخ داد.", "error")
        return redirect(url_for("inventory.dashboard"))


@inventory_bp.route("/details/<int:profile_id>")
def details(profile_id):
    """صفحه جزئیات موجودی یک پروفیل"""
    try:
        profile = get_profile_details(profile_id)
        if not profile:
            flash("پروفیل مورد نظر یافت نشد.", "error")
            return redirect(url_for("inventory.dashboard"))
            
        details_data = get_profile_stock_details(profile_id)
        
        template_details = {
            "profile": profile,
            "full_items": details_data["complete_pieces"],
            "pieces": details_data["pieces"],
            "logs": details_data["logs"]
        }
        
        change_type_map = {
            "add_stock": "افزایش موجودی",
            "remove_stock": "کاهش موجودی",
            "add_piece": "افزودن تکه",
            "remove_piece": "حذف تکه"
        }
        
        logs_with_translation = []
        for log in details_data["logs"]:
            log_dict = dict(log)
            log_dict["change_type_fa"] = change_type_map.get(log_dict["change_type"], log_dict["change_type"])
            logs_with_translation.append(log_dict)
            
        return render_template("profile_inventory_details.html", details=template_details, logs=logs_with_translation)
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت inventory_details: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه جزئیات انبار رخ داد.", "error")
        return redirect(url_for("inventory.profile_types"))


@inventory_bp.route("/items/add/<int:profile_id>", methods=["POST"])
def add_items(profile_id):
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
                
        return redirect(url_for("inventory.details", profile_id=profile_id))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت add_inventory_items: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات رخ داد.", "error")
        return redirect(url_for("inventory.details", profile_id=profile_id))


@inventory_bp.route("/items/remove/<int:profile_id>", methods=["POST"])
def remove_items(profile_id):
    """کاهش شاخه کامل از انبار"""
    try:
        quantity = int(request.form.get("quantity", 0))
        description = request.form.get("description", "")
        
        if quantity <= 0:
            flash("تعداد باید بزرگتر از صفر باشد.", "error")
        else:
            success, msg = remove_inventory_stock(profile_id, quantity, description)
            if success:
                flash("موجودی با موفقیت کسر شد.", "success")
            else:
                flash(f"خطا در کسر موجودی: {msg}", "error")
                
        return redirect(url_for("inventory.details", profile_id=profile_id))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت remove_inventory_items: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات رخ داد.", "error")
        return redirect(url_for("inventory.details", profile_id=profile_id))


@inventory_bp.route("/pieces/add/<int:profile_id>", methods=["POST"])
def add_piece(profile_id):
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
                
        return redirect(url_for("inventory.details", profile_id=profile_id))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت add_inventory_piece: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات رخ داد.", "error")
        return redirect(url_for("inventory.details", profile_id=profile_id))


@inventory_bp.route("/pieces/remove/<int:piece_id>", methods=["POST"])
def remove_piece(piece_id):
    """حذف تکه شاخه از انبار"""
    try:
        profile_id = request.form.get("profile_id")
        
        success, msg = remove_inventory_piece(piece_id, description="حذف دستی توسط کاربر")
        if success:
            flash("تکه شاخه با موفقیت حذف شد.", "success")
        else:
            flash(f"خطا در حذف تکه شاخه: {msg}", "error")
            
        if profile_id:
            return redirect(url_for("inventory.details", profile_id=profile_id))
        return redirect(url_for("inventory.dashboard"))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت remove_inventory_piece: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات رخ داد.", "error")
        return redirect(url_for("inventory.dashboard"))
