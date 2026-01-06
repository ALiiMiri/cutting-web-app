# Authentication Blueprint - routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
import traceback
import jdatetime

from auth_utils import (
    get_user_by_username,
    get_user_by_id,
    verify_password,
    check_account_locked,
    record_failed_login,
    record_successful_login,
    change_user_password,
    User
)

# Create Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """صفحه ورود"""
    # اگر کاربر قبلاً لاگین کرده، به صفحه اصلی هدایت شود
    if current_user.is_authenticated:
        # اما اگر باید رمز تغییر دهد، به صفحه تغییر رمز برود
        if current_user.must_change_password:
            return redirect(url_for('auth.change_password'))
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('لطفاً نام کاربری و رمز عبور را وارد کنید.', 'error')
            return render_template('login.html')
        
        try:
            # دریافت اطلاعات کاربر
            user_data = get_user_by_username(username)
            
            if not user_data:
                flash('نام کاربری یا رمز عبور اشتباه است.', 'error')
                return render_template('login.html')
            
            # بررسی قفل بودن حساب
            is_locked, locked_until = check_account_locked(user_data)
            if is_locked:
                # محاسبه دقیقه‌های باقیمانده با استفاده از تاریخ شمسی
                now_shamsi = jdatetime.datetime.now()
                time_diff = locked_until.togregorian() - now_shamsi.togregorian()
                minutes_left = int(time_diff.total_seconds() / 60) + 1
                flash(f'حساب کاربری به دلیل تلاش‌های ناموفق قفل شده است. لطفاً {minutes_left} دقیقه دیگر تلاش کنید.', 'error')
                return render_template('login.html')
            
            # بررسی فعال بودن حساب
            if not user_data['is_active']:
                flash('حساب کاربری غیرفعال است. لطفاً با مدیر سیستم تماس بگیرید.', 'error')
                return render_template('login.html')
            
            # بررسی رمز عبور
            if not verify_password(user_data, password):
                record_failed_login(username)
                flash('نام کاربری یا رمز عبور اشتباه است.', 'error')
                return render_template('login.html')
            
            # ورود موفق
            user = User(
                id=user_data['id'],
                username=user_data['username'],
                role=user_data['role'],
                is_active=user_data['is_active'],
                must_change_password=user_data['must_change_password']
            )
            
            login_user(user, remember=True)
            record_successful_login(user.id)
            
            # اگر باید رمز تغییر دهد
            if user.must_change_password:
                flash('لطفاً رمز عبور خود را تغییر دهید.', 'warning')
                return redirect(url_for('auth.change_password'))
            
            # برگشت به صفحه درخواستی یا صفحه اصلی
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            flash(f'خوش آمدید، {user.username}!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            print(f"خطا در ورود: {e}")
            traceback.print_exc()
            flash('خطایی در فرآیند ورود رخ داد. لطفاً دوباره تلاش کنید.', 'error')
            return render_template('login.html')
    
    # GET request
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """خروج از سیستم"""
    logout_user()
    flash('با موفقیت از سیستم خارج شدید.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """تغییر رمز عبور"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # اعتبارسنجی
        if not current_password or not new_password or not confirm_password:
            flash('لطفاً تمام فیلدها را پر کنید.', 'error')
            return render_template('change_password.html', force_change=current_user.must_change_password)
        
        if new_password != confirm_password:
            flash('رمز عبور جدید و تکرار آن مطابقت ندارند.', 'error')
            return render_template('change_password.html', force_change=current_user.must_change_password)
        
        if len(new_password) < 6:
            flash('رمز عبور باید حداقل ۶ کاراکتر باشد.', 'error')
            return render_template('change_password.html', force_change=current_user.must_change_password)
        
        # بررسی رمز فعلی
        user_data = get_user_by_username(current_user.username)
        if not user_data or not verify_password(user_data, current_password):
            flash('رمز عبور فعلی اشتباه است.', 'error')
            return render_template('change_password.html', force_change=current_user.must_change_password)
        
        # تغییر رمز
        if change_user_password(current_user.id, new_password, clear_must_change=True):
            flash('رمز عبور با موفقیت تغییر کرد.', 'success')
            
            # بروزرسانی وضعیت کاربر جاری
            updated_user = get_user_by_id(current_user.id)
            if updated_user:
                current_user.must_change_password = False
            
            return redirect(url_for('index'))
        else:
            flash('خطا در تغییر رمز عبور. لطفاً دوباره تلاش کنید.', 'error')
            return render_template('change_password.html', force_change=current_user.must_change_password)
    
    # GET request
    return render_template('change_password.html', force_change=current_user.must_change_password)
