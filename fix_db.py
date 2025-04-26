import sqlite3
import os
import time
import traceback

# تنظیمات
DB_NAME = "cutting_web_data.db"
MAX_RETRIES = 5  # تعداد تلاش‌های مجدد
WAIT_TIME = 2    # زمان انتظار بین تلاش‌ها (ثانیه)

print("=== اسکریپت اصلاح دیتابیس ===")
print(f"پایگاه داده هدف: {DB_NAME}")

def execute_with_retry(func, *args, **kwargs):
    """اجرای یک تابع با سعی مجدد در صورت قفل بودن دیتابیس"""
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < MAX_RETRIES - 1:
                print(f"دیتابیس قفل است. تلاش مجدد در {WAIT_TIME} ثانیه... ({attempt+1}/{MAX_RETRIES})")
                time.sleep(WAIT_TIME)
            else:
                raise
        except Exception as e:
            print(f"خطای غیرمنتظره: {e}")
            raise

def reset_custom_columns():
    """حذف تمام ستون‌های موجود و افزودن ستون‌های پایه"""
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
    
    conn = None
    try:
        print("\nاتصال به پایگاه داده...")
        conn = sqlite3.connect(DB_NAME, timeout=10.0)  # تایم‌اوت طولانی‌تر
        conn.isolation_level = None  # فعال کردن حالت اتوکامیت
        cursor = conn.cursor()
        
        # بررسی وجود جدول
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='custom_columns'")
        if not cursor.fetchone():
            print("جدول custom_columns وجود ندارد! ابتدا جدول را ایجاد می‌کنیم...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS custom_columns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    column_name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
            """)
        
        # حذف ستون‌های موجود
        print("در حال حذف تمام ستون‌های موجود...")
        cursor.execute("DELETE FROM custom_columns")
        print("ستون‌های قبلی با موفقیت حذف شدند.")
        
        # افزودن ستون‌های پایه
        print("\nافزودن ستون‌های پایه...")
        for column_key, display_name in base_columns:
            try:
                cursor.execute(
                    "INSERT INTO custom_columns (column_name, display_name, is_active) VALUES (?, ?, 1)",
                    (column_key, display_name)
                )
                print(f"✓ ستون '{display_name}' ({column_key}) با موفقیت اضافه شد.")
            except sqlite3.IntegrityError:
                print(f"! ستون '{column_key}' قبلاً وجود دارد.")
            except Exception as e:
                print(f"! خطا در افزودن ستون '{column_key}': {e}")
        
        # بررسی نتیجه
        cursor.execute("SELECT id, column_name, display_name, is_active FROM custom_columns")
        columns = cursor.fetchall()
        
        print(f"\nتعداد {len(columns)} ستون در جدول custom_columns:")
        for col in columns:
            print(f" - ID: {col[0]}, کلید: {col[1]}, نام نمایشی: {col[2]}, وضعیت: {'فعال' if col[3] else 'غیرفعال'}")
            
        print("\nعملیات با موفقیت انجام شد.")
        return True
        
    except Exception as e:
        print(f"\n!!! خطا در اصلاح دیتابیس: {e}")
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()

# اجرای اصلی با مکانیزم سعی مجدد
if __name__ == "__main__":
    try:
        # بررسی وجود فایل دیتابیس
        if not os.path.exists(DB_NAME):
            print(f"خطا: فایل دیتابیس '{DB_NAME}' یافت نشد!")
            exit(1)
            
        print("\n--- شروع عملیات اصلاح دیتابیس ---")
        success = execute_with_retry(reset_custom_columns)
        
        if success:
            print("\n=== فرآیند با موفقیت انجام شد ===")
            print("موارد زیر را انجام دهید:")
            print("1. برنامه فلسک را مجدداً راه‌اندازی کنید")
            print("2. به صفحه تنظیمات ستون‌ها بروید")
            print("3. ستون‌های مورد نظر را فعال کنید")
            print("4. تغییرات را ذخیره کنید")
            print("5. حالا صفحه ویرایش گروهی باید به درستی کار کند")
        else:
            print("\n!!! فرآیند با خطا مواجه شد !!!")
            print("لطفاً تمام برنامه‌های پایتون را ببندید و مجدداً تلاش کنید.")
            
    except Exception as e:
        print(f"خطای کلی در اجرای برنامه: {e}")
        traceback.print_exc() 