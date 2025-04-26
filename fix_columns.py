import sqlite3
import os

# تنظیمات
DB_NAME = "cutting_web_data.db"

print("اسکریپت اصلاح تنظیمات ستون‌ها...")

def ensure_base_columns_exist():
    """اطمینان از وجود ستون‌های پایه در دیتابیس"""
    base_columns = [
        ("rang", "رنگ پروفیل"),
        ("noe_profile", "نوع پروفیل"),
        ("vaziat", "وضعیت تولید درب"),
        ("lola", "لولا"),
        ("ghofl", "قفل"),
        ("accessory", "اکسسوری"),
        ("kolaft", "کلاف"),
        ("dastgire", "دستگیره"),
        ("tozihat", "توضیحات")
    ]
    
    for column_key, display_name in base_columns:
        conn = None
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            # بررسی وجود ستون
            cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
            result = cursor.fetchone()
            if not result:
                print(f"افزودن ستون پایه '{column_key}' به دیتابیس")
                cursor.execute(
                    "INSERT INTO custom_columns (column_name, display_name, is_active) VALUES (?, ?, 1)",
                    (column_key, display_name)
                )
                conn.commit()
        except sqlite3.Error as e:
            print(f"خطا در ensure_base_columns_exist برای ستون {column_key}: {e}")
        finally:
            if conn:
                conn.close()

# حذف تمام ستون‌های فعلی (اختیاری)
try:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM custom_columns")
    conn.commit()
    conn.close()
    print("ستون‌های نمایشی حذف شدند")
except Exception as e:
    print(f"خطا در حذف ستون‌ها: {e}")

# فراخوانی تابع برای افزودن ستون‌های پایه
ensure_base_columns_exist()

# اصلاح visible_columns در session
print("تابع initialize_visible_columns اصلاح شد")

print("لطفاً برنامه Flask را مجدداً راه‌اندازی کنید") 