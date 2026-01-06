#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
اسکریپت برای ساخت کاربر ادمین اولیه

استفاده:
    python create_admin.py

یا با متغیرهای محیطی:
    set ADMIN_USERNAME=admin
    set ADMIN_PASSWORD=your_password
    python create_admin.py
"""

import sys
import os
import getpass

# اضافه کردن مسیر پروژه به sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth_utils import create_user, get_user_by_username
from database import init_db


def create_admin_user():
    """ایجاد کاربر ادمین اولیه"""
    
    print("=" * 60)
    print("اسکریپت ساخت کاربر ادمین اولیه")
    print("=" * 60)
    print()
    
    # مقداردهی اولیه دیتابیس (اطمینان از وجود جدول users)
    print("در حال بررسی و ایجاد جداول دیتابیس...")
    init_db()
    print("✓ جداول دیتابیس آماده است.")
    print()
    
    # دریافت اطلاعات از متغیرهای محیطی یا ورودی کاربر
    username = os.getenv('ADMIN_USERNAME')
    password = os.getenv('ADMIN_PASSWORD')
    
    if not username:
        print("لطفاً نام کاربری برای ادمین را وارد کنید:")
        username = input("نام کاربری (پیش‌فرض: admin): ").strip()
        if not username:
            username = "admin"
    
    # بررسی وجود کاربر
    existing_user = get_user_by_username(username)
    if existing_user:
        print()
        print(f"⚠ کاربر '{username}' از قبل وجود دارد.")
        print()
        overwrite = input("آیا می‌خواهید رمز این کاربر را بازنشانی کنید؟ (y/n): ").lower()
        if overwrite != 'y':
            print("عملیات لغو شد.")
            return
    
    if not password:
        print()
        print("لطفاً رمز عبور برای ادمین را وارد کنید:")
        while True:
            password = getpass.getpass("رمز عبور (حداقل 6 کاراکتر): ")
            if len(password) < 6:
                print("⚠ رمز عبور باید حداقل 6 کاراکتر باشد.")
                continue
            
            password_confirm = getpass.getpass("تکرار رمز عبور: ")
            if password != password_confirm:
                print("⚠ رمز عبور و تکرار آن مطابقت ندارند.")
                continue
            
            break
    
    # ایجاد یا بروزرسانی کاربر
    print()
    print(f"در حال ایجاد کاربر ادمین '{username}'...")
    
    # اگر کاربر وجود دارد، فقط رمز را بازنشانی می‌کنیم
    if existing_user:
        from auth_utils import reset_user_password
        success = reset_user_password(existing_user['id'], password)
        if success:
            print()
            print("=" * 60)
            print("✓ رمز عبور با موفقیت بازنشانی شد!")
            print()
            print(f"  نام کاربری: {username}")
            print(f"  رمز عبور: [تنظیم شده]")
            print(f"  نقش: {existing_user['role']}")
            print()
            print("توجه: کاربر در اولین ورود مجبور به تغییر رمز عبور خواهد بود.")
            print("=" * 60)
        else:
            print()
            print("✗ خطا در بازنشانی رمز عبور.")
            sys.exit(1)
    else:
        # ایجاد کاربر جدید (بدون تغییر اجباری رمز برای ادمین اولیه)
        success, result = create_user(username, password, role='admin', must_change_password=False)
        
        if success:
            print()
            print("=" * 60)
            print("✓ کاربر ادمین با موفقیت ایجاد شد!")
            print()
            print(f"  نام کاربری: {username}")
            print(f"  رمز عبور: [تنظیم شده]")
            print(f"  نقش: admin (مدیر)")
            print()
            print("اکنون می‌توانید با این اطلاعات وارد سیستم شوید.")
            print("=" * 60)
        else:
            print()
            print(f"✗ خطا در ایجاد کاربر: {result}")
            sys.exit(1)


if __name__ == "__main__":
    try:
        create_admin_user()
    except KeyboardInterrupt:
        print()
        print()
        print("عملیات توسط کاربر لغو شد.")
        sys.exit(0)
    except Exception as e:
        print()
        print(f"✗ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
