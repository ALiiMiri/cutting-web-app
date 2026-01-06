# Admin Blueprint - routes/admin.py
# Panel for user management (admin only)

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
import traceback

from auth_utils import (
    get_all_users,
    create_user,
    update_user_role,
    toggle_user_active,
    reset_user_password,
    delete_user
)

# Create Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator برای محدود کردن دسترسی به ادمین"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('شما به این بخش دسترسی ندارید.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/users')
@admin_required
def users_list():
    """لیست کاربران (فقط ادمین)"""
    try:
        users = get_all_users()
        
        # ترجمه نقش‌ها برای نمایش
        role_translations = {
            'admin': 'مدیر',
            'staff': 'کارمند',
            'read_only': 'فقط مشاهده'
        }
        
        for user in users:
            user['role_display'] = role_translations.get(user['role'], user['role'])
        
        return render_template('admin/users.html', users=users, role_translations=role_translations)
        
    except Exception as e:
        print(f"خطا در نمایش لیست کاربران: {e}")
        traceback.print_exc()
        flash('خطایی در نمایش لیست کاربران رخ داد.', 'error')
        return redirect(url_for('index'))


@admin_bp.route('/users/create', methods=['POST'])
@admin_required
def create_user_route():
    """ایجاد کاربر جدید (فقط ادمین)"""
    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'staff')
        
        # اعتبارسنجی
        if not username or not password:
            flash('نام کاربری و رمز عبور الزامی است.', 'error')
            return redirect(url_for('admin.users_list'))
        
        if len(password) < 6:
            flash('رمز عبور باید حداقل ۶ کاراکتر باشد.', 'error')
            return redirect(url_for('admin.users_list'))
        
        if role not in ['admin', 'staff', 'read_only']:
            flash('نقش انتخاب شده معتبر نیست.', 'error')
            return redirect(url_for('admin.users_list'))
        
        # ایجاد کاربر (با must_change_password = True)
        success, result = create_user(username, password, role, must_change_password=True)
        
        if success:
            flash(f'کاربر "{username}" با موفقیت ایجاد شد. کاربر باید در اولین ورود رمز عبور را تغییر دهد.', 'success')
        else:
            flash(f'خطا در ایجاد کاربر: {result}', 'error')
        
        return redirect(url_for('admin.users_list'))
        
    except Exception as e:
        print(f"خطا در ایجاد کاربر: {e}")
        traceback.print_exc()
        flash('خطایی در ایجاد کاربر رخ داد.', 'error')
        return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/role', methods=['POST'])
@admin_required
def change_user_role(user_id):
    """تغییر نقش کاربر (فقط ادمین)"""
    try:
        new_role = request.form.get('role')
        
        if new_role not in ['admin', 'staff', 'read_only']:
            flash('نقش انتخاب شده معتبر نیست.', 'error')
            return redirect(url_for('admin.users_list'))
        
        # جلوگیری از تغییر نقش خود
        if user_id == current_user.id:
            flash('شما نمی‌توانید نقش خود را تغییر دهید.', 'warning')
            return redirect(url_for('admin.users_list'))
        
        if update_user_role(user_id, new_role):
            flash('نقش کاربر با موفقیت تغییر کرد.', 'success')
        else:
            flash('خطا در تغییر نقش کاربر.', 'error')
        
        return redirect(url_for('admin.users_list'))
        
    except Exception as e:
        print(f"خطا در تغییر نقش: {e}")
        traceback.print_exc()
        flash('خطایی در تغییر نقش رخ داد.', 'error')
        return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/toggle_active', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    """فعال/غیرفعال کردن کاربر (فقط ادمین)"""
    try:
        # جلوگیری از غیرفعال کردن خود
        if user_id == current_user.id:
            flash('شما نمی‌توانید خود را غیرفعال کنید.', 'warning')
            return redirect(url_for('admin.users_list'))
        
        if toggle_user_active(user_id):
            flash('وضعیت کاربر با موفقیت تغییر کرد.', 'success')
        else:
            flash('خطا در تغییر وضعیت کاربر.', 'error')
        
        return redirect(url_for('admin.users_list'))
        
    except Exception as e:
        print(f"خطا در تغییر وضعیت: {e}")
        traceback.print_exc()
        flash('خطایی در تغییر وضعیت رخ داد.', 'error')
        return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/reset_password', methods=['POST'])
@admin_required
def reset_password(user_id):
    """ریست رمز عبور کاربر (فقط ادمین)"""
    try:
        new_password = request.form.get('new_password', '')
        
        if not new_password:
            flash('رمز عبور جدید الزامی است.', 'error')
            return redirect(url_for('admin.users_list'))
        
        if len(new_password) < 6:
            flash('رمز عبور باید حداقل ۶ کاراکتر باشد.', 'error')
            return redirect(url_for('admin.users_list'))
        
        if reset_user_password(user_id, new_password):
            flash('رمز عبور با موفقیت بازنشانی شد. کاربر باید در اولین ورود رمز عبور را تغییر دهد.', 'success')
        else:
            flash('خطا در بازنشانی رمز عبور.', 'error')
        
        return redirect(url_for('admin.users_list'))
        
    except Exception as e:
        print(f"خطا در ریست رمز: {e}")
        traceback.print_exc()
        flash('خطایی در بازنشانی رمز عبور رخ داد.', 'error')
        return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user_route(user_id):
    """حذف کاربر (فقط ادمین)"""
    try:
        # جلوگیری از حذف خود
        if user_id == current_user.id:
            flash('شما نمی‌توانید خود را حذف کنید.', 'warning')
            return redirect(url_for('admin.users_list'))
        
        success, message = delete_user(user_id)
        
        if success:
            flash('کاربر با موفقیت حذف شد.', 'success')
        else:
            flash(f'خطا در حذف کاربر: {message}', 'error')
        
        return redirect(url_for('admin.users_list'))
        
    except Exception as e:
        print(f"خطا در حذف کاربر: {e}")
        traceback.print_exc()
        flash('خطایی در حذف کاربر رخ داد.', 'error')
        return redirect(url_for('admin.users_list'))
