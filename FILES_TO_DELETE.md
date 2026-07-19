# لیست فایل‌ها و پوشه‌های قابل حذف

## ✅ فایل‌های قابل حذف (بدون خطر)

### 1. فایل‌های تست و دیباگ (Test & Debug Files)
این فایل‌ها فقط برای تست و دیباگ بودند و در برنامه اصلی استفاده نمی‌شوند:

- `check_db.py` - اسکریپت بررسی دیتابیس
- `debug_script.py` - اسکریپت دیباگ
- `fix_columns.py` - اسکریپت تعمیر ستون‌ها (موقت)
- `fix_db.py` - اسکریپت تعمیر دیتابیس (موقت)
- `fix_function.py` - اسکریپت تعمیر تابع (موقت)
- `inspect_db.py` - اسکریپت بررسی دیتابیس
- `test_flask.py` - تست Flask
- `test_inventory.py` - تست سیستم انبار
- `test_script.py` - اسکریپت تست عمومی
- `database_analysis.py` - اسکریپت تحلیل دیتابیس (من ساخته‌ام)

### 2. فایل‌های Utility قدیمی (Old Utility Files)
- `add_base_columns.py` - اضافه کردن ستون‌های پایه (احتمالاً دیگر لازم نیست)
- `add_customer.py` - اضافه کردن مشتری (احتمالاً دیگر لازم نیست)

### 3. فایل‌های بکاپ HTML
- `templates/project_details.html.backup`
- `templates/project_details.html.backup2.html`
- `templates/pdf_template.orig.html`

### 4. فایل‌های ZIP اضافی
- `zip2.zip`
- `zipzip.zip`
- `templates/pdf_template_optimized.zip` (اگر نسخه unzip شده دارید)

### 5. فایل‌های دیتابیس اضافی (با احتیاط!)
⚠️ **قبل از حذف، مطمئن شوید که داده‌های مهمی ندارند:**

- `cutting.db` - فایل خالی (0 KB) - **می‌توانید پاک کنید**
- `your_database_file.db` - فایل قدیمی (76 KB) - **قبل از حذف بررسی کنید**

### 6. فایل‌های متنی موقت
- `new_actions.txt` - یادداشت‌های موقت

### 7. گزارش‌های تحلیلی (اختیاری)
- `DATABASE_STATUS_REPORT.md` - گزارش تحلیل دیتابیس (من ساخته‌ام)

---

## 📁 پوشه‌های قابل حذف

### 1. پوشه‌های Python Cache (همیشه قابل حذف)
این پوشه‌ها به صورت خودکار ساخته می‌شوند:

- `__pycache__/` - کش Python در ریشه
- `migrations/__pycache__/` - کش Python در migrations

### 2. پوشه بکاپ
- `bakup/` - پوشه بکاپ قدیمی (دارای نسخه قدیمی cutting_web_app.py)

### 3. لاگ‌های قدیمی (اختیاری)
- `logs/` - می‌توانید همه فایل‌های `.log` قدیمی را پاک کنید
  - یا فقط لاگ‌های قدیمی‌تر از یک تاریخ مشخص

---

## ⚠️ فایل‌های که نباید پاک کنید

### فایل‌های ضروری برنامه:
- ✅ `cutting_web_app.py` - برنامه اصلی Flask
- ✅ `cutting_tool.py` - برنامه اصلی Tkinter (اگر استفاده می‌کنید)
- ✅ `database.py` - کد کار با دیتابیس
- ✅ `config.py` - تنظیمات
- ✅ `db_migrations.py` - مایگریشن‌های دیتابیس
- ✅ `logger.py` - سیستم لاگینگ
- ✅ `price_calculator.py` - محاسبه قیمت
- ✅ `cutting_web_data.db` - دیتابیس اصلی ⚠️ **هرگز پاک نکنید!**

### پوشه‌ها و فایل‌های ضروری:
- ✅ `templates/` - قالب‌های HTML
- ✅ `static/` - فایل‌های استاتیک (CSS، فونت‌ها، ...)
- ✅ `migrations/` - مایگریشن‌های دیتابیس
- ✅ `requirements.txt` - وابستگی‌های Python
- ✅ `.gitignore` - تنظیمات Git

### فایل‌های Export (اختیاری - اگر می‌خواهید نگه دارید):
- `static/exports/*.xlsx` - فایل‌های Excel صادر شده
  - اگر می‌خواهید نگه دارید، می‌توانید نگه دارید
  - یا می‌توانید پاک کنید (احتمالاً بکاپ گرفته‌اید)

---

## 📝 دستورات PowerShell برای حذف

### حذف فایل‌های تست:
```powershell
Remove-Item check_db.py, debug_script.py, fix_columns.py, fix_db.py, fix_function.py, inspect_db.py, test_flask.py, test_inventory.py, test_script.py, database_analysis.py
Remove-Item add_base_columns.py, add_customer.py
Remove-Item new_actions.txt
```

### حذف فایل‌های بکاپ:
```powershell
Remove-Item templates\project_details.html.backup, templates\project_details.html.backup2.html, templates\pdf_template.orig.html
```

### حذف فایل‌های ZIP:
```powershell
Remove-Item zip2.zip, zipzip.zip, templates\pdf_template_optimized.zip
```

### حذف فایل‌های دیتابیس اضافی (با احتیاط!):
```powershell
# فقط cutting.db (خالی است)
Remove-Item cutting.db

# your_database_file.db - قبل از حذف بررسی کنید!
# Remove-Item your_database_file.db  # کامنت شده - خودتان تصمیم بگیرید
```

### حذف پوشه‌ها:
```powershell
# پوشه‌های cache (همیشه قابل حذف)
Remove-Item -Recurse -Force __pycache__
Remove-Item -Recurse -Force migrations\__pycache__

# پوشه بکاپ
Remove-Item -Recurse -Force bakup

# لاگ‌های قدیمی (اختیاری)
# Remove-Item -Recurse -Force logs  # همه لاگ‌ها
# یا فقط لاگ‌های قدیمی:
Get-ChildItem logs\*.log | Where-Object {$_.LastWriteTime -lt (Get-Date).AddMonths(-1)} | Remove-Item
```

---

## ✅ خلاصه: فایل‌های قابل حذف (امن)

### فایل‌ها (21 فایل):
1. check_db.py
2. debug_script.py
3. fix_columns.py
4. fix_db.py
5. fix_function.py
6. inspect_db.py
7. test_flask.py
8. test_inventory.py
9. test_script.py
10. database_analysis.py
11. add_base_columns.py
12. add_customer.py
13. new_actions.txt
14. templates/project_details.html.backup
15. templates/project_details.html.backup2.html
16. templates/pdf_template.orig.html
17. zip2.zip
18. zipzip.zip
19. templates/pdf_template_optimized.zip
20. cutting.db (خالی)
21. DATABASE_STATUS_REPORT.md (اختیاری)

### پوشه‌ها (3 پوشه):
1. __pycache__/
2. migrations/__pycache__/
3. bakup/

### فایل‌های لاگ (23 فایل - اختیاری):
- logs/*.log (همه یا فقط قدیمی‌ها)

---

**نکته مهم:** قبل از حذف هر چیزی، مطمئن شوید که بکاپ گرفته‌اید!

