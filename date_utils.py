# date_utils.py
# توابع کمکی برای کار با تاریخ شمسی (جلالی)

import jdatetime
from datetime import datetime, timedelta


def get_shamsi_now():
    """
    دریافت تاریخ و زمان شمسی فعلی
    Returns: jdatetime.datetime object
    """
    return jdatetime.datetime.now()


def get_shamsi_timestamp():
    """
    دریافت timestamp شمسی برای استفاده در نام فایل‌ها
    Format: YYYYMMDD_HHMMSS (مثال: 14031009_153045)
    Returns: str
    """
    return jdatetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def get_shamsi_datetime_str():
    """
    دریافت تاریخ و زمان شمسی به صورت رشته قابل خواندن
    Format: YYYY/MM/DD HH:MM:SS
    Returns: str
    """
    return jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")


def get_shamsi_date_str():
    """
    دریافت فقط تاریخ شمسی به صورت رشته
    Format: YYYY/MM/DD
    Returns: str
    """
    return jdatetime.date.today().strftime("%Y/%m/%d")


def get_shamsi_date_short():
    """
    دریافت تاریخ شمسی کوتاه (بدون خط تیره)
    Format: YYYYMMDD
    Returns: str
    """
    return jdatetime.datetime.now().strftime("%Y%m%d")


def get_shamsi_datetime_iso():
    """
    دریافت تاریخ و زمان شمسی به فرمت ISO-like
    Format: YYYY-MM-DD HH:MM:SS
    Returns: str
    """
    return jdatetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def gregorian_to_shamsi(dt):
    """
    تبدیل تاریخ میلادی به شمسی
    
    Args:
        dt: datetime object یا string
    
    Returns:
        str: تاریخ شمسی به فرمت YYYY/MM/DD HH:MM:SS
    """
    if dt is None:
        return "-"
    
    if isinstance(dt, str):
        # تلاش برای تبدیل string به datetime
        try:
            # فرمت‌های مختلف را امتحان می‌کنیم
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(dt.split('.')[0], fmt)
                    break
                except ValueError:
                    continue
            else:
                # اگر هیچ فرمتی جواب نداد، همان string را برگردان
                return dt
        except:
            return dt
    
    try:
        # تبدیل به شمسی
        shamsi_dt = jdatetime.datetime.fromgregorian(datetime=dt)
        return shamsi_dt.strftime('%Y/%m/%d %H:%M:%S')
    except:
        return str(dt)


def gregorian_to_shamsi_date(dt):
    """
    تبدیل تاریخ میلادی به شمسی (فقط تاریخ بدون ساعت)
    
    Args:
        dt: datetime object یا string
    
    Returns:
        str: تاریخ شمسی به فرمت YYYY/MM/DD
    """
    if dt is None:
        return "-"
    
    if isinstance(dt, str):
        try:
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(dt.split('.')[0], fmt)
                    break
                except ValueError:
                    continue
            else:
                return dt
        except:
            return dt
    
    try:
        shamsi_dt = jdatetime.datetime.fromgregorian(datetime=dt)
        return shamsi_dt.strftime('%Y/%m/%d')
    except:
        return str(dt)


def add_days_shamsi(days):
    """
    اضافه کردن روز به تاریخ شمسی فعلی
    
    Args:
        days: تعداد روز (می‌تواند منفی باشد)
    
    Returns:
        jdatetime.datetime object
    """
    current = jdatetime.datetime.now()
    # تبدیل به میلادی، اضافه کردن روز، و برگشت به شمسی
    gregorian = current.togregorian()
    new_gregorian = gregorian + timedelta(days=days)
    return jdatetime.datetime.fromgregorian(datetime=new_gregorian)


def shamsi_datetime_from_timestamp(timestamp):
    """
    تبدیل Unix timestamp به تاریخ شمسی
    
    Args:
        timestamp: Unix timestamp (seconds)
    
    Returns:
        str: تاریخ شمسی
    """
    try:
        dt = datetime.fromtimestamp(timestamp)
        return gregorian_to_shamsi(dt)
    except:
        return "-"


def format_shamsi_for_display(dt_string):
    """
    فرمت کردن رشته تاریخ شمسی برای نمایش بهتر
    
    Args:
        dt_string: رشته تاریخ (YYYY-MM-DD HH:MM:SS یا YYYY/MM/DD HH:MM:SS)
    
    Returns:
        str: تاریخ فرمت شده
    """
    if not dt_string or dt_string == "-":
        return "-"
    
    # اگر قبلاً فرمت شده، همان را برگردان
    if '/' in dt_string:
        return dt_string
    
    # جایگزینی - با /
    return dt_string.replace('-', '/')
