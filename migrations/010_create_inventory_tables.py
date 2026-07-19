import sqlite3

def apply(conn):
    """
    Creates inventory-related tables:
    - profile_types: انواع پروفیل
    - inventory_items: موجودی شاخه‌های کامل
    - inventory_pieces: شاخه‌های برش‌خورده
    - inventory_logs: سوابق تغییرات انبار
    - cutting_settings: تنظیمات محاسبه برش
    """
    print("--- Applying migration: 010_create_inventory_tables ---")
    cursor = conn.cursor()
    try:
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
            profile_type_id INTEGER NOT NULL UNIQUE,
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
            ('prefer_pieces', 'true', 'اولویت استفاده از شاخه‌های نیمه بر کامل'),
            ('inventory_optimization_strategy', 'minimize_waste', 'استراتژی بهینه‌سازی'),
            ('show_inventory_warnings', 'true', 'نمایش هشدارهای موجودی'),
            ('low_inventory_threshold', '5', 'آستانه هشدار موجودی کم')
        ''')
        
        print("--- Migration 010_create_inventory_tables applied successfully. ---")
    except Exception as e:
        print(f"!!! FAILED to apply migration 010_create_inventory_tables: {e}")
        raise
