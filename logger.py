# --- logger.py ---
"""
سیستم مدیریت لاگینگ برای برنامه مدیریت پروفیل درب
این ماژول یک سیستم لاگینگ ساختارمند با قابلیت تنظیم سطوح مختلف و ذخیره در فایل فراهم می‌کند.
"""

import logging
import os
import sys
from datetime import datetime


class ProgramLogger:
    """سیستم مدیریت لاگ برای برنامه مدیریت پروفیل درب"""

    # سطوح لاگینگ
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    def __init__(self, log_level=logging.INFO, log_to_file=True, log_dir="logs"):
        """راه‌اندازی سیستم لاگینگ

        Args:
            log_level: سطح لاگینگ (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_to_file: آیا لاگ‌ها در فایل ذخیره شوند
            log_dir: پوشه ذخیره فایل‌های لاگ
        """
        self.logger = logging.getLogger('ProfileManager')
        self.logger.setLevel(log_level)
        self.logger.propagate = False

        # پاک کردن هندلرهای قبلی
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # فرمت لاگ
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] - %(message)s')

        # هندلر کنسول
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # هندلر فایل (اختیاری)
        if log_to_file:
            try:
                if not os.path.exists(log_dir):
                    os.makedirs(log_dir)

                now = datetime.now()
                log_file = os.path.join(
                    log_dir, f"profile_manager_{now.strftime('%Y%m%d_%H%M')}.log")

                file_handler = logging.FileHandler(log_file, encoding='utf-8')
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            except Exception as e:
                self.logger.error(f"خطا در ایجاد فایل لاگ: {e}")

    # --- زیرسیستم‌های لاگینگ ---
    def get_module_logger(self, module_name):
        """ایجاد یک لاگر مخصوص برای زیرسیستم‌های مختلف

        Args:
            module_name: نام ماژول یا بخش برنامه

        Returns:
            ModuleLogger: لاگر مخصوص آن بخش
        """
        return ModuleLogger(self.logger, module_name)


class ModuleLogger:
    """لاگر برای بخش‌های مختلف برنامه"""

    def __init__(self, main_logger, module_name):
        """
        Args:
            main_logger: لاگر اصلی برنامه
            module_name: نام بخش برنامه
        """
        self.logger = main_logger
        self.module_name = module_name

    def debug(self, message):
        """ثبت پیام سطح دیباگ"""
        self.logger.debug(f"[{self.module_name}] {message}")

    def info(self, message):
        """ثبت پیام سطح اطلاعات"""
        self.logger.info(f"[{self.module_name}] {message}")

    def warning(self, message):
        """ثبت پیام سطح هشدار"""
        self.logger.warning(f"[{self.module_name}] {message}")

    def error(self, message):
        """ثبت پیام سطح خطا"""
        self.logger.error(f"[{self.module_name}] {message}")

    def critical(self, message):
        """ثبت پیام سطح بحرانی"""
        self.logger.critical(f"[{self.module_name}] {message}")
