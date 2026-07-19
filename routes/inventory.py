# Inventory Blueprint - routes/inventory.py
# This module contains all inventory-related routes

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
import traceback

from decorators import manager_or_admin_required, staff_or_admin_required

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
    get_latest_reversible_inventory_operation,
    undo_latest_inventory_operation,
    get_waste_warehouse_data,
    update_waste_item,
    get_profile_colors,
    add_profile_color,
    transfer_inventory_stock_color,
    correct_inventory_stock,
    get_inventory_correction_center_data,
    reactivate_profile_type,
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
        print(f"!!!!!! Unexpected error in inventory dashboard route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه مدیریت انبار رخ داد.", "error")
        return redirect(url_for("index"))


@inventory_bp.route("/waste")
def waste_dashboard():
    """داشبورد مستقل ضایعات با ردیابی پروژه و پروفیل."""
    try:
        profile_id = request.args.get("profile_id", type=int)
        project_id = request.args.get("project_id", type=int)
        status = request.args.get("status", "available")
        data = get_waste_warehouse_data(
            profile_id=profile_id,
            project_id=project_id,
            status=status,
        )
        return render_template(
            "inventory_waste.html",
            waste=data,
            selected_profile_id=profile_id,
            selected_project_id=project_id,
            selected_status=status,
        )
    except Exception as exc:
        print(f"!!!!!! Error in waste_dashboard: {exc}")
        traceback.print_exc()
        flash("خطایی در نمایش انبار ضایعات رخ داد.", "error")
        return redirect(url_for("inventory.dashboard"))


@inventory_bp.route("/waste/<int:item_id>/update", methods=["POST"])
@manager_or_admin_required
def update_waste(item_id):
    """ثبت وزن واقعی یا خروج ضایعات، فقط توسط ادمین."""
    result = update_waste_item(
        item_id=item_id,
        action_type=request.form.get("action_type", ""),
        actor_user_id=current_user.id,
        actual_weight=request.form.get("actual_weight"),
        price_per_kg=request.form.get("price_per_kg"),
        counterparty=request.form.get("counterparty", ""),
        note=request.form.get("note", ""),
    )
    flash(
        result.get("message", "عملیات ضایعات انجام نشد."),
        "success" if result["status"] == "success" else "error",
    )
    redirect_args = {
        key: request.form.get(key)
        for key in ("profile_id", "project_id", "status")
        if request.form.get(key)
    }
    return redirect(url_for("inventory.waste_dashboard", **redirect_args))


@inventory_bp.route("/profile_types")
def profile_types():
    """صفحه مدیریت انواع پروفیل"""
    try:
        profile_types_list = get_all_profile_types(include_inactive=True)
        response = render_template("profile_types.html", profile_types=profile_types_list)
        return response
    except UnicodeEncodeError as e:
        print(f"!!!!!! Unicode encoding error in profile_types route: {e}")
        traceback.print_exc()
        flash("خطایی در نمایش صفحه انواع پروفیل رخ داد.", "error")
        return redirect(url_for("inventory.dashboard"))
    except Exception as e:
        print(f"!!!!!! Unexpected error in profile_types route: {e}")
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
                # result already contains a user-friendly Persian message
                flash(result, "error")
        
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
@manager_or_admin_required
def delete_profile_type_route(profile_id):
    """Delete an unused profile or archive a referenced one."""
    try:
        result = delete_profile_type(
            profile_id,
            actor_user_id=current_user.id,
            reason=request.form.get("reason", ""),
        )
        flash(
            result.get("message", "عملیات انجام نشد."),
            "success" if result.get("status") in ("deleted", "archived") else "error",
        )
        return redirect(url_for("inventory.profile_types"))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت delete_profile_type: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات حذف رخ داد.", "error")
        return redirect(url_for("inventory.profile_types"))


@inventory_bp.route("/profile_types/reactivate/<int:profile_id>", methods=["POST"])
@manager_or_admin_required
def reactivate_profile(profile_id):
    success = reactivate_profile_type(profile_id)
    flash(
        "پروفیل دوباره فعال شد." if success else "فعال‌سازی پروفیل انجام نشد.",
        "success" if success else "error",
    )
    return redirect(url_for("inventory.profile_types"))


@inventory_bp.route("/corrections")
@manager_or_admin_required
def corrections():
    data = get_inventory_correction_center_data()
    return render_template(
        "inventory_corrections.html",
        correction=data,
        latest_operation=get_latest_reversible_inventory_operation(),
    )


@inventory_bp.route("/corrections/stock", methods=["POST"])
@manager_or_admin_required
def correct_stock():
    quantity = request.form.get("quantity", type=int) or 0
    if request.form.get("direction") == "decrease":
        quantity = -quantity
    result = correct_inventory_stock(
        request.form.get("profile_id", type=int),
        request.form.get("color_id", type=int),
        quantity,
        request.form.get("reason", ""),
        actor_user_id=current_user.id,
    )
    flash(result["message"], "success" if result["status"] == "success" else "error")
    return redirect(url_for("inventory.corrections"))


@inventory_bp.route("/corrections/color", methods=["POST"])
@manager_or_admin_required
def correct_color():
    reason = str(request.form.get("reason", "")).strip()
    if len(reason) < 3:
        flash("ثبت دلیل اصلاح رنگ الزامی است.", "error")
    else:
        success, message = transfer_inventory_stock_color(
            request.form.get("profile_id", type=int),
            request.form.get("source_color_id", type=int),
            request.form.get("target_color_id", type=int),
            request.form.get("quantity", type=int),
            actor_user_id=current_user.id,
            reason=reason,
        )
        flash("رنگ موجودی اصلاح شد." if success else message,
              "success" if success else "error")
    return redirect(url_for("inventory.corrections"))


@inventory_bp.route("/corrections/piece/add", methods=["POST"])
@manager_or_admin_required
def correct_piece_add():
    reason = str(request.form.get("reason", "")).strip()
    if len(reason) < 3:
        flash("ثبت دلیل اصلاح قطعه الزامی است.", "error")
    else:
        success = add_inventory_piece(
            request.form.get("profile_id", type=int),
            request.form.get("length", type=float),
            f"اصلاح ادمین: {reason}",
            actor_user_id=current_user.id,
            color_id=request.form.get("color_id", type=int),
        )
        flash("قطعه اصلاحی ثبت شد." if success else "ثبت قطعه انجام نشد.",
              "success" if success else "error")
    return redirect(url_for("inventory.corrections"))


@inventory_bp.route("/corrections/piece/remove", methods=["POST"])
@manager_or_admin_required
def correct_piece_remove():
    reason = str(request.form.get("reason", "")).strip()
    if len(reason) < 3:
        flash("ثبت دلیل حذف اصلاحی قطعه الزامی است.", "error")
    else:
        success, message = remove_inventory_piece(
            request.form.get("piece_id", type=int),
            f"اصلاح ادمین: {reason}",
            actor_user_id=current_user.id,
        )
        flash("قطعه با ثبت سابقه حذف شد." if success else message,
              "success" if success else "error")
    return redirect(url_for("inventory.corrections"))
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
        # Allow filtering by query param too (template uses ?profile_id=...)
        profile_id_from_qs = request.args.get("profile_id")
        if profile_id_from_qs:
            try:
                profile_id = int(profile_id_from_qs)
            except ValueError:
                profile_id = None

        logs_list = get_inventory_logs(limit=100, profile_id=profile_id)
        profiles = get_all_profile_types()
        latest_operation = get_latest_reversible_inventory_operation()
        
        change_type_map = {
            "add_stock": "افزایش موجودی",
            "remove_stock": "کاهش موجودی",
            "add_piece": "افزودن تکه",
            "remove_piece": "حذف تکه",
            "undo_stock": "بازگردانی موجودی",
            "undo_add_piece": "بازگردانی افزودن تکه",
            "undo_remove_piece": "بازگردانی حذف تکه",
            "stock_correction": "اصلاح ادمین موجودی",
            "transfer_color": "اصلاح رنگ موجودی",
        }
        
        logs_with_translation = []
        for log in logs_list:
            log_dict = dict(log)
            log_dict["change_type_fa"] = change_type_map.get(log_dict["change_type"], log_dict["change_type"])
            logs_with_translation.append(log_dict)
            
        return render_template(
            "inventory_logs.html",
            logs=logs_with_translation,
            profiles=profiles,
            profile_id=profile_id,
            latest_operation=latest_operation,
        )
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
            "logs": details_data["logs"],
            "stock_by_color": details_data["stock_by_color"],
            "colors": details_data["colors"],
        }
        
        change_type_map = {
            "add_stock": "افزایش موجودی",
            "remove_stock": "کاهش موجودی",
            "add_piece": "افزودن تکه",
            "remove_piece": "حذف تکه",
            "undo_stock": "بازگردانی موجودی",
            "undo_add_piece": "بازگردانی افزودن تکه",
            "undo_remove_piece": "بازگردانی حذف تکه",
            "stock_correction": "اصلاح ادمین موجودی",
            "transfer_color": "اصلاح رنگ موجودی",
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
@staff_or_admin_required
def add_items(profile_id):
    """افزودن شاخه کامل به انبار"""
    try:
        quantity = int(request.form.get("quantity", 0))
        description = request.form.get("description", "")
        color_id = request.form.get("color_id", type=int)
        
        if not color_id:
            flash("انتخاب رنگ پروفیل الزامی است.", "error")
        elif quantity <= 0:
            flash("تعداد باید بزرگتر از صفر باشد.", "error")
        else:
            if add_inventory_stock(
                profile_id, quantity, description, actor_user_id=current_user.id,
                color_id=color_id,
            ):
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
@staff_or_admin_required
def remove_items(profile_id):
    """کاهش شاخه کامل از انبار"""
    try:
        quantity = int(request.form.get("quantity", 0))
        description = request.form.get("description", "")
        color_id = request.form.get("color_id", type=int)
        
        if not color_id:
            flash("انتخاب رنگ پروفیل الزامی است.", "error")
        elif quantity <= 0:
            flash("تعداد باید بزرگتر از صفر باشد.", "error")
        else:
            success, msg = remove_inventory_stock(
                profile_id, quantity, description, actor_user_id=current_user.id,
                color_id=color_id,
            )
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
@staff_or_admin_required
def add_piece(profile_id):
    """افزودن تکه شاخه به انبار"""
    try:
        length = float(request.form.get("length", 0))
        description = request.form.get("description", "")
        color_id = request.form.get("color_id", type=int)
        
        if not color_id:
            flash("انتخاب رنگ پروفیل الزامی است.", "error")
        elif length <= 0:
            flash("طول باید بزرگتر از صفر باشد.", "error")
        else:
            if add_inventory_piece(
                profile_id, length, description, actor_user_id=current_user.id,
                color_id=color_id,
            ):
                flash("تکه شاخه با موفقیت اضافه شد.", "success")
            else:
                flash("خطا در افزودن تکه شاخه.", "error")
                
        return redirect(url_for("inventory.details", profile_id=profile_id))
    except Exception as e:
        print(f"!!!!!! خطای غیرمنتظره در روت add_inventory_piece: {e}")
        traceback.print_exc()
        flash("خطایی در انجام عملیات رخ داد.", "error")
        return redirect(url_for("inventory.details", profile_id=profile_id))


@inventory_bp.route("/colors/add", methods=["POST"])
@staff_or_admin_required
def add_color():
    """Add a new physical profile color without a deployment or code change."""
    profile_id = request.form.get("profile_id", type=int)
    success, result = add_profile_color(
        request.form.get("name", ""), request.form.get("hex_code", "#9ca3af")
    )
    flash("رنگ جدید با موفقیت اضافه شد." if success else result,
          "success" if success else "error")
    if profile_id:
        return redirect(url_for("inventory.details", profile_id=profile_id))
    return redirect(url_for("inventory.dashboard"))


@inventory_bp.route("/pieces/remove/<int:piece_id>", methods=["POST"])
@staff_or_admin_required
def remove_piece(piece_id):
    """حذف تکه شاخه از انبار"""
    try:
        profile_id = request.form.get("profile_id")
        
        success, msg = remove_inventory_piece(
            piece_id,
            description="حذف دستی توسط کاربر",
            actor_user_id=current_user.id,
        )
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


@inventory_bp.route("/operations/<int:operation_id>/undo", methods=["POST"])
@manager_or_admin_required
def undo_operation(operation_id):
    """بازگردانی آخرین عملیات کامل انبار، فقط توسط ادمین."""
    result = undo_latest_inventory_operation(
        operation_id,
        admin_user_id=current_user.id,
        reason=request.form.get("reason", ""),
    )
    category = "success" if result["status"] == "success" else "error"
    message = result.get("message", "بازگردانی انجام نشد.")
    if result["status"] == "success" and result.get("summary"):
        message += "\n" + "\n".join(f"• {item}" for item in result["summary"])
    flash(message, category)
    return redirect(url_for("inventory.logs"))
