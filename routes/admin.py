# Admin Blueprint - routes/admin.py
# Panel for user management (admin only)

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import current_user
import traceback

from decorators import manager_or_admin_required
from security_utils import csrf_protected

from auth_utils import (
    get_all_users,
    create_user,
    update_user_role,
    toggle_user_active,
    reset_user_password,
    delete_user,
    get_user_by_id,
    get_user_activity_logs,
    record_user_activity,
    count_active_admins,
    validate_password_strength,
    ROLE_LABELS,
    VALID_ROLES,
)

# Create Blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _can_manage_target(target):
    if not target:
        return False
    if current_user.role == 'admin':
        return True
    return target.role in ('staff', 'read_only')


def _available_roles():
    if current_user.role == 'admin':
        return VALID_ROLES
    return ('staff', 'read_only')


def _render_users_page(shown_credentials=None):
    users = get_all_users()
    for user in users:
        user['role_display'] = ROLE_LABELS.get(user['role'], user['role'])
    action_translations = {
        'create_user': 'ساخت کاربر',
        'change_role': 'تغییر نقش',
        'activate_user': 'فعال‌کردن کاربر',
        'deactivate_user': 'غیرفعال‌کردن کاربر',
        'reset_password': 'بازنشانی رمز',
        'delete_user': 'حذف کاربر',
    }
    return render_template(
        'admin/users.html',
        users=users,
        role_translations=ROLE_LABELS,
        shown_credentials=shown_credentials,
        available_roles=_available_roles(),
        activity_logs=get_user_activity_logs(),
        action_translations=action_translations,
    )


@admin_bp.route('/users')
@manager_or_admin_required
def users_list():
    """لیست کاربران (فقط ادمین)"""
    try:
        # پاک‌کردن داده قدیمی احتمالی؛ رمز موقت دیگر داخل کوکی نگهداری نمی‌شود.
        session.pop('shown_credentials', None)
        return _render_users_page()

    except Exception as e:
        print(f"خطا در نمایش لیست کاربران: {e}")
        traceback.print_exc()
        flash('خطایی در نمایش لیست کاربران رخ داد.', 'error')
        return redirect(url_for('index'))


@admin_bp.route('/users/create', methods=['POST'])
@manager_or_admin_required
@csrf_protected
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

        password_error = validate_password_strength(password, username)
        if password_error:
            flash(password_error, 'error')
            return redirect(url_for('admin.users_list'))

        if role not in _available_roles():
            flash('شما اجازه ساخت کاربر با این نقش را ندارید.', 'error')
            return redirect(url_for('admin.users_list'))

        # ایجاد کاربر (با must_change_password = True)
        success, result = create_user(username, password, role, must_change_password=True)

        if success:
            record_user_activity(
                current_user.id, 'create_user', result,
                {'username': username, 'role': role},
            )
            shown_credentials = {
                'username': username,
                'password': password,
                'action': 'create'
            }
            flash(f'کاربر "{username}" با موفقیت ایجاد شد. رمز موقت را از پنجره زیر کپی کنید.', 'success')
            return _render_users_page(shown_credentials)
        else:
            flash(f'خطا در ایجاد کاربر: {result}', 'error')

        return redirect(url_for('admin.users_list'))

    except Exception as e:
        print(f"خطا در ایجاد کاربر: {e}")
        traceback.print_exc()
        flash('خطایی در ایجاد کاربر رخ داد.', 'error')
        return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/role', methods=['POST'])
@manager_or_admin_required
@csrf_protected
def change_user_role(user_id):
    """تغییر نقش کاربر (فقط ادمین)"""
    try:
        new_role = request.form.get('role')

        if new_role not in _available_roles():
            flash('شما اجازه انتخاب این نقش را ندارید.', 'error')
            return redirect(url_for('admin.users_list'))

        # جلوگیری از تغییر نقش خود
        if user_id == current_user.id:
            flash('شما نمی‌توانید نقش خود را تغییر دهید.', 'warning')
            return redirect(url_for('admin.users_list'))

        target = get_user_by_id(user_id)
        if not _can_manage_target(target):
            flash('شما اجازه تغییر این کاربر را ندارید.', 'error')
            return redirect(url_for('admin.users_list'))

        if target.role == 'admin' and target.is_active and new_role != 'admin' and count_active_admins() <= 1:
            flash('نقش آخرین مدیر سیستم فعال را نمی‌توان تغییر داد.', 'warning')
            return redirect(url_for('admin.users_list'))

        if update_user_role(user_id, new_role):
            record_user_activity(
                current_user.id, 'change_role', user_id,
                {'username': target.username, 'old_role': target.role, 'new_role': new_role},
            )
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
@manager_or_admin_required
@csrf_protected
def toggle_user_status(user_id):
    """فعال/غیرفعال کردن کاربر (فقط ادمین)"""
    try:
        # جلوگیری از غیرفعال کردن خود
        if user_id == current_user.id:
            flash('شما نمی‌توانید خود را غیرفعال کنید.', 'warning')
            return redirect(url_for('admin.users_list'))

        target = get_user_by_id(user_id)
        if not _can_manage_target(target):
            flash('شما اجازه تغییر وضعیت این کاربر را ندارید.', 'error')
            return redirect(url_for('admin.users_list'))

        if target.role == 'admin' and target.is_active and count_active_admins() <= 1:
            flash('آخرین مدیر سیستم فعال را نمی‌توان غیرفعال کرد.', 'warning')
            return redirect(url_for('admin.users_list'))

        if toggle_user_active(user_id):
            record_user_activity(
                current_user.id, 'activate_user' if not target.is_active else 'deactivate_user',
                user_id, {'username': target.username},
            )
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
@manager_or_admin_required
@csrf_protected
def reset_password(user_id):
    """ریست رمز عبور کاربر (فقط ادمین)"""
    try:
        new_password = request.form.get('new_password', '')

        if not new_password:
            flash('رمز عبور جدید الزامی است.', 'error')
            return redirect(url_for('admin.users_list'))

        if user_id == current_user.id:
            flash('برای تغییر رمز خودتان از گزینه «تغییر رمز» استفاده کنید.', 'warning')
            return redirect(url_for('admin.users_list'))

        target = get_user_by_id(user_id)
        if not _can_manage_target(target):
            flash('شما اجازه تغییر رمز این کاربر را ندارید.', 'error')
            return redirect(url_for('admin.users_list'))

        password_error = validate_password_strength(new_password, target.username)
        if password_error:
            flash(password_error, 'error')
            return redirect(url_for('admin.users_list'))

        if reset_user_password(user_id, new_password):
            record_user_activity(
                current_user.id, 'reset_password', user_id, {'username': target.username},
            )
            shown_credentials = {
                'username': target.username,
                'password': new_password,
                'action': 'reset'
            }
            flash('رمز عبور با موفقیت بازنشانی شد. رمز جدید را از پنجره زیر کپی کنید.', 'success')
            return _render_users_page(shown_credentials)
        else:
            flash('خطا در بازنشانی رمز عبور.', 'error')

        return redirect(url_for('admin.users_list'))

    except Exception as e:
        print(f"خطا در ریست رمز: {e}")
        traceback.print_exc()
        flash('خطایی در بازنشانی رمز عبور رخ داد.', 'error')
        return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@manager_or_admin_required
@csrf_protected
def delete_user_route(user_id):
    """حذف کاربر (فقط ادمین)"""
    try:
        # جلوگیری از حذف خود
        if user_id == current_user.id:
            flash('شما نمی‌توانید خود را حذف کنید.', 'warning')
            return redirect(url_for('admin.users_list'))

        target = get_user_by_id(user_id)
        if not _can_manage_target(target):
            flash('شما اجازه حذف این کاربر را ندارید.', 'error')
            return redirect(url_for('admin.users_list'))

        if target.role == 'admin' and target.is_active and count_active_admins() <= 1:
            flash('آخرین مدیر سیستم فعال را نمی‌توان حذف کرد.', 'warning')
            return redirect(url_for('admin.users_list'))

        success, message = delete_user(user_id)

        if success:
            record_user_activity(
                current_user.id, 'delete_user', None,
                {'username': target.username, 'role': target.role},
            )
            flash('کاربر با موفقیت حذف شد.', 'success')
        else:
            flash(f'خطا در حذف کاربر: {message}', 'error')

        return redirect(url_for('admin.users_list'))

    except Exception as e:
        print(f"خطا در حذف کاربر: {e}")
        traceback.print_exc()
        flash('خطایی در حذف کاربر رخ داد.', 'error')
        return redirect(url_for('admin.users_list'))
