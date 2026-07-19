#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت برای اصلاح ستون‌های سفارشی
این اسکریپت ستون‌های سفارشی پایه را بررسی و در صورت نیاز اصلاح می‌کند.
"""

import sqlite3
import sys
import io

# تنظیم encoding برای Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from config import Config

DB_NAME = Config.DB_NAME

def fix_custom_columns():
    """اصلاح ستون‌های سفارشی پایه"""
    base_columns = [
        ("rang", "رنگ پروفیل", "dropdown"),
        ("noe_profile", "نوع پروفیل", "dropdown"),
        ("vaziat", "وضعیت تولید درب", "dropdown"),
        ("lola", "لولا", "dropdown"),
        ("ghofl", "قفل", "dropdown"),
        ("accessory", "اکسسوری", "dropdown"),
        ("kolaft", "نوع چارچوب", "dropdown"),
        ("dastgire", "دستگیره", "dropdown"),
        ("tozihat", "توضیحات", "text")
    ]
    
    default_options_map = {
        "rang": ["سفید", "آنادایز", "مشکی", "شامپاینی", "طلایی", "نقره‌ای", "قهوه‌ای"],
        "vaziat": ["همزمان با تولید چهارچوب", "تولید درب در آینده", "بدون درب", "درب دار", "نصب شده"],
        "lola": ["OTLAV", "HTH", "NHN", "سه تیکه", "مخفی", "متفرقه"],
        "ghofl": ["STV", "ایزدو", "NHN", "HTN", "یونی", "مگنتی", "بدون قفل"],
        "accessory": ["آلومینیوم آستانه فاق و زبانه", "آرامبند مرونی", "قفل برق سارو با فنر", "آینه", "دستگیره پشت درب"],
        "kolaft": ["سه طرفه", "دو طرفه"],
        "dastgire": ["دو تیکه", "ایزدو", "گریف ورک", "گریف تو کار", "متفرقه"]
    }
    
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        print("در حال بررسی و اصلاح ستون‌های سفارشی...")
        
        # بررسی و افزودن/اصلاح ستون‌ها
        for column_key, display_name, col_type in base_columns:
            try:
                cursor.execute("SELECT id, column_type FROM custom_columns WHERE column_name = ?", (column_key,))
                existing = cursor.fetchone()
                
                if not existing:
                    print(f"  افزودن ستون '{display_name}' ({column_key})...")
                    cursor.execute(
                        "INSERT INTO custom_columns (column_name, display_name, is_active, column_type) VALUES (?, ?, 1, ?)",
                        (column_key, display_name, col_type)
                    )
                else:
                    existing_id = existing[0]
                    existing_type = existing[1] if len(existing) > 1 else None
                    
                    if existing_type != col_type:
                        print(f"  ✗ اصلاح نوع ستون '{display_name}' از '{existing_type}' به '{col_type}'...")
                        cursor.execute(
                            "UPDATE custom_columns SET column_type = ?, display_name = ? WHERE column_name = ?",
                            (col_type, display_name, column_key)
                        )
                        print(f"  ✓ نوع ستون '{display_name}' اصلاح شد.")
                    else:
                        print(f"  ✓ ستون '{display_name}' درست است.")
                    
                    # افزودن گزینه‌های پیش‌فرض برای ستون‌های dropdown
                    if col_type == "dropdown" and column_key in default_options_map:
                        # بعد از update، column_id را دوباره بگیریم
                        cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
                        column_id_result = cursor.fetchone()
                        column_id = column_id_result[0] if column_id_result else existing_id
                        
                        cursor.execute("SELECT COUNT(*) FROM custom_column_options WHERE column_id = ?", (column_id,))
                        option_count = cursor.fetchone()[0]
                        
                        if option_count == 0:
                            print(f"    افزودن گزینه‌های پیش‌فرض برای '{display_name}'...")
                            for option_value in default_options_map[column_key]:
                                cursor.execute(
                                    "INSERT INTO custom_column_options (column_id, option_value) VALUES (?, ?)",
                                    (column_id, option_value)
                                )
                            print(f"    ✓ {len(default_options_map[column_key])} گزینه برای '{display_name}' اضافه شد.")
                        else:
                            print(f"    ✓ گزینه‌های '{display_name}' موجود است ({option_count} گزینه).")
            
            except sqlite3.Error as e:
                print(f"  خطا در پردازش ستون '{column_key}': {e}")
                continue
        
        conn.commit()
        print("\n✅ ستون‌های سفارشی با موفقیت بررسی و اصلاح شدند.")
        
        # نمایش خلاصه
        cursor.execute("SELECT column_name, display_name, column_type, is_active FROM custom_columns ORDER BY id")
        all_columns = cursor.fetchall()
        print(f"\n📊 تعداد کل ستون‌های سفارشی: {len(all_columns)}")
        for col in all_columns:
            status = "فعال" if col[3] else "غیرفعال"
            print(f"  - {col[1]} ({col[0]}): {col[2]} - {status}")
        
    except Exception as e:
        print(f"❌ خطا: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("=" * 50)
    print("اسکریپت اصلاح ستون‌های سفارشی")
    print("=" * 50)
    fix_custom_columns()
    print("=" * 50)
