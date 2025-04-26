import sqlite3
import traceback

DB_NAME = 'cutting_web_data.db'

def initialize_inventory_database():
    """ایجاد جداول مورد نیاز برای سیستم انبار"""
    print("DEBUG: ایجاد جداول سیستم انبارداری...")
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # جدول انواع پروفیل
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS profile_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            default_length REAL DEFAULT 600,
            weight_per_meter REAL DEFAULT 1.9,
            color TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # جدول موجودی شاخه‌های کامل
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_type_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE
        )
        ''')
        
        # جدول شاخه‌های برش‌خورده
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_pieces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_type_id INTEGER NOT NULL,
            length REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE
        )
        ''')
        
        # جدول سوابق تغییرات انبار
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_type_id INTEGER NOT NULL,
            change_type TEXT NOT NULL,
            quantity INTEGER,
            length REAL,
            piece_id INTEGER,
            project_id INTEGER,
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL
        )
        ''')
        
        # جدول تنظیمات محاسبه برش
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS cutting_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            value TEXT,
            description TEXT
        )
        ''')
        
        # داده‌های پیش‌فرض برای تنظیمات
        cursor.execute('''
        INSERT OR IGNORE INTO cutting_settings (name, value, description) 
        VALUES 
            ('waste_threshold', '70', 'آستانه اندازه ضایعات کوچک (سانتی‌متر)'),
            ('use_inventory', 'true', 'استفاده از سیستم انبار در محاسبات'),
            ('prefer_pieces', 'true', 'اولویت استفاده از شاخه‌های نیمه بر کامل')
        ''')
        
        conn.commit()
        print("DEBUG: تغییرات سایت به دیتابیس با موفقیت Commit شد.")
    except sqlite3.Error as e:
        print(f"!!!!!! خطا در initialize_inventory_database: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# ایجاد توابع مربوط به انبار 