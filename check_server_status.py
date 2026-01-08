#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت بررسی وضعیت دیتابیس روی سرور
این اسکریپت را روی سرور اجرا کنید و خروجی را برای من بفرستید
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import sqlite3
from config import Config

DB_NAME = Config.DB_NAME

print("=" * 60)
print("بررسی وضعیت دیتابیس روی سرور")
print("=" * 60)

try:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. بررسی migration های اجرا شده
    print("\n1. Migration های اجرا شده:")
    print("-" * 60)
    try:
        cursor.execute("SELECT name FROM schema_migrations ORDER BY name")
        migrations = cursor.fetchall()
        if migrations:
            for mig in migrations:
                print(f"  ✓ {mig[0]}")
        else:
            print("  ⚠️  هیچ migration ای یافت نشد!")
    except sqlite3.Error as e:
        print(f"  ✗ خطا در بررسی migrations: {e}")
    
    # 2. بررسی ستون‌های سفارشی
    print("\n2. ستون‌های سفارشی موجود:")
    print("-" * 60)
    try:
        cursor.execute("SELECT column_name, display_name, column_type, is_active FROM custom_columns ORDER BY id")
        cols = cursor.fetchall()
        if cols:
            print(f"  تعداد کل: {len(cols)}\n")
            for col in cols:
                status = "فعال" if col[3] else "غیرفعال"
                print(f"  - {col[1]} ({col[0]})")
                print(f"    نوع: {col[2]} | وضعیت: {status}")
        else:
            print("  ⚠️  هیچ ستونی یافت نشد!")
    except sqlite3.Error as e:
        print(f"  ✗ خطا در بررسی ستون‌ها: {e}")
    
    # 3. بررسی نوع ستون‌های پایه (مشکل اصلی)
    print("\n3. بررسی نوع ستون‌های پایه:")
    print("-" * 60)
    base_columns = {
        "rang": "dropdown",
        "noe_profile": "dropdown",
        "vaziat": "dropdown",
        "lola": "dropdown",
        "ghofl": "dropdown",
        "accessory": "dropdown",
        "kolaft": "dropdown",
        "dastgire": "dropdown",
        "tozihat": "text"
    }
    
    errors = []
    for col_key, expected_type in base_columns.items():
        try:
            cursor.execute("SELECT column_type FROM custom_columns WHERE column_name = ?", (col_key,))
            result = cursor.fetchone()
            if result:
                actual_type = result[0]
                if actual_type != expected_type:
                    print(f"  ✗ {col_key}: نوع اشتباه! (انتظار: {expected_type}, موجود: {actual_type})")
                    errors.append((col_key, expected_type, actual_type))
                else:
                    print(f"  ✓ {col_key}: نوع درست ({actual_type})")
            else:
                print(f"  ✗ {col_key}: یافت نشد!")
                errors.append((col_key, expected_type, None))
        except sqlite3.Error as e:
            print(f"  ✗ {col_key}: خطا - {e}")
    
    # 4. بررسی جدول schema_migrations
    print("\n4. بررسی جدول schema_migrations:")
    print("-" * 60)
    try:
        cursor.execute("SELECT COUNT(*) FROM schema_migrations")
        count = cursor.fetchone()[0]
        print(f"  تعداد migration های ثبت شده: {count}")
        
        # بررسی اینکه migration 002 اجرا شده یا نه
        cursor.execute("SELECT name FROM schema_migrations WHERE name = '002_seed_base_custom_columns'")
        if cursor.fetchone():
            print("  ✓ Migration 002 اجرا شده است")
        else:
            print("  ✗ Migration 002 اجرا نشده است!")
    except sqlite3.Error as e:
        print(f"  ✗ خطا: {e}")
    
    # 5. خلاصه
    print("\n" + "=" * 60)
    print("خلاصه:")
    print("-" * 60)
    if errors:
        print(f"  ⚠️  {len(errors)} مشکل یافت شد!")
        print("\n  مشکلات:")
        for col_key, expected, actual in errors:
            if actual:
                print(f"    - {col_key}: باید {expected} باشد ولی {actual} است")
            else:
                print(f"    - {col_key}: وجود ندارد")
    else:
        print("  ✅ همه چیز درست است!")
    
    conn.close()
    
except Exception as e:
    print(f"\n❌ خطای کلی: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("پایان بررسی")
print("=" * 60)
