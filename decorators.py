# Custom decorators for access control
from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user, login_required


def roles_required(*roles):
    """
    Decorator برای محدود کردن دسترسی به نقش‌های خاص
    
    استفاده:
        @roles_required('admin')
        @roles_required('admin', 'staff')
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('لطفاً وارد سیستم شوید.', 'warning')
                return redirect(url_for('auth.login'))
            
            if current_user.role not in roles:
                flash('شما به این بخش دسترسی ندارید.', 'error')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Decorator برای محدود کردن دسترسی به ادمین"""
    return roles_required('admin')(f)


def staff_or_admin_required(f):
    """Decorator برای محدود کردن دسترسی به staff و admin (نه read_only)"""
    return roles_required('admin', 'staff')(f)


def prevent_read_only(f):
    """
    Decorator برای جلوگیری از دسترسی کاربران read_only به POST/DELETE
    فقط برای routeهای تغییر دهنده (POST, PUT, DELETE)
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.role == 'read_only':
            flash('شما فقط دسترسی مشاهده دارید و نمی‌توانید تغییرات ایجاد کنید.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function
