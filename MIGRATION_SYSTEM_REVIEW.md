# بررسی سیستم مایگریشن - Migration System Review

## تاریخ بررسی
این بررسی در تاریخ انجام شده است تا اطمینان حاصل شود که تمام تغییرات اسکیما از طریق سیستم مایگریشن انجام می‌شوند.

## مشکلات یافت شده و اصلاح شده

### 1. ✅ CREATE TABLE مستقیم برای price_settings
**مکان:** `cutting_web_app.py` خطوط 3473 و 3505  
**مشکل:** ایجاد مستقیم جدول `price_settings` بدون استفاده از سیستم مایگریشن  
**راه حل:** حذف شد - مایگریشن `003_create_price_settings` این کار را انجام می‌دهد  
**وضعیت:** ✅ اصلاح شده

### 2. ✅ CREATE TABLE مستقیم برای users در backup_manager
**مکان:** `backup_manager.py` خط 334  
**مشکل:** ایجاد مستقیم جدول `users` هنگام restore بکاپ  
**راه حل:** توضیح اضافه شد که این برای restore بکاپ‌های قدیمی است و مایگریشن `005_create_users_table` در حالت عادی این کار را انجام می‌دهد  
**وضعیت:** ✅ توضیح اضافه شده (این مورد برای restore بکاپ‌های قدیمی ضروری است)

### 3. ✅ جداول انبار بدون استفاده از مایگریشن
**مکان:** `database.py` تابع `initialize_inventory_tables()`  
**مشکل:** ایجاد مستقیم جداول انبار (`profile_types`, `inventory_items`, `inventory_pieces`, `inventory_logs`, `cutting_settings`) و ستون `min_waste`  
**راه حل:** 
- ایجاد مایگریشن `010_create_inventory_tables` برای جداول اصلی
- ایجاد مایگریشن `011_add_min_waste_to_profile_types` برای ستون `min_waste`
- تبدیل `initialize_inventory_tables()` به یک تابع خالی (فقط برای سازگاری)
**وضعیت:** ✅ اصلاح شده

## مایگریشن‌های موجود

سیستم مایگریشن شامل مایگریشن‌های زیر است:

1. **000_create_initial_tables** - ایجاد جداول پایه (projects, doors, custom_columns, ...)
2. **001_add_row_color_tag_to_doors** - افزودن ستون `row_color_tag` به جدول `doors`
3. **002_seed_base_custom_columns** - ایجاد ستون‌های سفارشی پایه
4. **003_create_price_settings** - ایجاد جدول `price_settings`
5. **004_create_inventory_deductions** - ایجاد جدول `inventory_deductions`
6. **005_create_users_table** - ایجاد جدول `users` برای احراز هویت
7. **006_fix_inventory_items_unique** - افزودن UNIQUE constraint به `inventory_items.profile_type_id`
8. **007_remove_noe_profile_defaults** - حذف گزینه‌های پیش‌فرض از `noe_profile`
9. **008_create_default_admin** - ایجاد کاربر پیش‌فرض admin
10. **009_add_project_code** - افزودن ستون `project_code` به جدول `projects`
11. **010_create_inventory_tables** - ایجاد جداول سیستم انبار (جدید)
12. **011_add_min_waste_to_profile_types** - افزودن ستون `min_waste` به `profile_types` (جدید)

## نحوه اجرای مایگریشن‌ها

مایگریشن‌ها به صورت خودکار در موارد زیر اجرا می‌شوند:

1. **شروع برنامه:** تابع `init_db()` در `cutting_web_app.py` خط 186 فراخوانی می‌شود
2. **تابع `init_db()`:** در `database.py` خط 26 تعریف شده و:
   - ابتدا `apply_migrations()` را فراخوانی می‌کند
   - سپس `initialize_inventory_tables()` را فراخوانی می‌کند (که اکنون فقط برای سازگاری است)

## ساختار سیستم مایگریشن

### فایل اصلی
- `db_migrations.py`: شامل لیست تمام مایگریشن‌ها و منطق اجرای آن‌ها

### فایل‌های مایگریشن Python
- `migrations/002_seed_base_custom_columns.py`
- `migrations/008_create_default_admin.py`
- `migrations/010_create_inventory_tables.py` (جدید)
- `migrations/011_add_min_waste_to_profile_types.py` (جدید)

### جدول ردیابی
- `schema_migrations`: جدولی که نام مایگریشن‌های اعمال شده را ذخیره می‌کند

## نتیجه‌گیری

✅ **همه تغییرات اسکیما اکنون از طریق سیستم مایگریشن انجام می‌شوند.**

- تمام CREATE TABLE مستقیم حذف یا توضیح داده شده‌اند
- جداول انبار به مایگریشن تبدیل شده‌اند
- سیستم مایگریشن به درستی پیاده‌سازی شده و در شروع برنامه اجرا می‌شود

## نکات مهم

1. **backup_manager.py:** CREATE TABLE برای `users` در این فایل فقط برای restore بکاپ‌های قدیمی است و در حالت عادی استفاده نمی‌شود.

2. **initialize_inventory_tables():** این تابع اکنون خالی است و فقط برای سازگاری با کدهای قدیمی نگه داشته شده است. جداول انبار توسط مایگریشن‌های 010 و 011 ایجاد می‌شوند.

3. **ترتیب مایگریشن‌ها:** مایگریشن‌ها به ترتیب شماره اجرا می‌شوند و هر مایگریشن فقط یک بار اجرا می‌شود (بر اساس جدول `schema_migrations`).
