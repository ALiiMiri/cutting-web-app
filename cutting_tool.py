# --- START OF REFACTORED FILE gui_cutting_refactored.py ---

import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import os
import sqlite3
import pandas as pd
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display
import textwrap
import webbrowser
from xhtml2pdf import pisa
import jdatetime  # برای تبدیل تاریخ میلادی به شمسی

# Assuming this might be needed later, kept import
from subprocess import check_call
import logging
from logger import ProgramLogger

# Assuming database.py contains necessary functions like:
# init_db, init_custom_columns_table, init_custom_column_options_table,
# get_all_custom_columns, update_custom_column, DB_NAME
# Make sure database.py is in the same directory or accessible
# --- START OF REPLACEMENT for the import block ---
# --- START OF REPLACEMENT for the import block ---
try:
    print("DEBUG: Attempting to import from database...")
    from database import (
        # Core Initialization
        initialize_database,  # <<-- به این تغییر بده
        # اینها رو نگه دار فعلا، هرچند initialize_database خودش صداشون میزنه
        init_custom_columns_table,
        init_custom_column_options_table,  # اینها رو نگه دار فعلا
        DB_NAME,
        # ... بقیه import ها ...
        # --- ADD/ENSURE THESE ARE PRESENT FOR PROJECT MANAGEMENT ---
        add_project,
        update_project,
        get_all_projects,
        get_project_details,
        delete_project,
        add_door_to_project,
        get_doors_for_project,
        delete_all_doors_for_project,
        add_custom_column,
        # ... (keep other imports like column/option functions) ...
        get_active_custom_columns_data,  # مطمئن شو اینها هم هستن
        get_manageable_columns_data,
        get_all_configurable_columns_data,
        update_custom_column_status,
        update_custom_column_display_name,
        delete_custom_column,
        get_column_id_by_key,
        get_custom_column_options,
        add_option_to_column,
        delete_column_option,
    )

    # Add other necessary standard library imports if used in new code
    import time
    from tkinter import simpledialog

    print("DEBUG: Import from database successful.")
except ImportError as e:
    print(f"DEBUG: Import from database FAILED: {e}")
    import traceback

    traceback.print_exc()
    messagebox.showerror(
        "خطای وابستگی",
        f"فایل database.py یافت نشد یا توابع لازم در آن وجود ندارد.\n\nجزئیات خطا:\n{e}",
    )
    # Decide how to handle this, maybe exit?
    # root.quit() # Example exit

# --- END OF REPLACEMENT for the import block ---

# --- Constants ---
WEIGHT_PER_METER = 1.9
STOCK_LENGTH = 600
PROJECTS_DIR = "Projects"
DEFAULT_ROW_TAG = "white"  # Default tag for coloring rows

# Base column definitions (internal key, display name)
BASE_COLUMNS_DATA = [
    ("makan", "مکان نصب"),
    ("arz", "عرض"),
    ("ertefa", "ارتفاع"),
    ("tedad", "تعداد درب"),
    ("jeht", "جهت درب"),
    ("rang", "رنگ پروفیل"),
    ("noe_profile", "نوع پروفیل"),
    ("vaziat", "وضعیت تولید درب"),
    ("lola", "لولا"),
    ("ghofl", "قفل"),
    ("accessory", "اکسسوری"),
    ("kolaft", "کلاف"),
    ("dastgire", "دستگیره"),
    ("tozihat", "توضیحات"),
]
BASE_COLUMN_KEYS = [key for key, _ in BASE_COLUMNS_DATA]


# --- Helper Functions (Could be moved to a utils.py) ---


def color_map(color_name):
    """Maps color names to RGB tuples for FPDF."""
    color_dict = {
        "yellow": (255, 255, 0),
        "lightgreen": (144, 238, 144),
        "lightblue": (173, 216, 230),
        "white": (255, 255, 255),
    }
    return color_dict.get(color_name, (255, 255, 255))  # Default to white


def fix_persian_text(text):
    """Reshapes and applies bidi algorithm for correct Persian display."""
    if not isinstance(text, str):
        text = str(text)
    reshaped_text = arabic_reshaper.reshape(text)
    return get_display(reshaped_text)


def open_file_externally(file_path):
    """Opens a file using the default system application."""
    try:
        if os.name == "nt":  # Windows
            os.startfile(file_path)
        elif sys.platform == "darwin":  # macOS
            check_call(["open", file_path])
        else:  # Linux and other Unix-like
            check_call(["xdg-open", file_path])
        return True
    except Exception as e:
        print(f"Error opening file {file_path}: {e}")
        messagebox.showerror(
            "خطا در باز کردن فایل",
            f"امکان باز کردن فایل وجود نداشت:\n{file_path}\n\n{e}",
        )
        return False


# --- Main Application Class ---


class CuttingApp:
    def __init__(self, root_window, logger=None):

        self.root = root_window
        self.root.title("برنامه برش پروفیل درب (نسخه بازنویسی شده)")
        self.root.geometry("1200x800")
        # تنظیم لاگرها
        self.logger = logger or ProgramLogger(
            log_level=logging.INFO
        )  # لاگر پیش‌فرض اگر ارسال نشده باشد
        self.db_logger = self.logger.get_module_logger("DATABASE")
        self.ui_logger = self.logger.get_module_logger("UI")
        self.tree_logger = self.logger.get_module_logger("TREEVIEW")
        self.project_logger = self.logger.get_module_logger("PROJECT")
        self.current_project_id = None
        self.has_unsaved_changes = False

        # --- Initialize State Variables ---
        self.tooltip_label = None
        self.settings_win = None
        self.door_entries_buffer = []  # Temporary storage for adding multiple doors
        # Remember checked items in batch edit
        self.previous_checked_labels_batch_edit = set()
        self.output_visible = False

        # --- Setup Database and Directories ---
        self._initialize_database()
        self._ensure_projects_directory()

        # --- Build UI ---
        self._create_main_widgets()
        self._create_order_tab()
        self._load_initial_tree_columns()  # Load columns after treeview is created

    def _debug_find_entry_fields(self):
        """Prints all attributes with 'entry' or 'customer' or 'order' in their names."""
        print("--- DEBUG: Searching for entry fields ---")
        for attr_name in dir(self):
            if any(
                keyword in attr_name.lower()
                for keyword in ["entry", "customer", "order", "input", "field"]
            ):
                print(f"Found attribute: {attr_name}")
        print("--- DEBUG: Search complete ---")

    def _initialize_database(self):
        """Initializes the database tables using the main function from database.py."""
        try:
            self.db_logger.info("شروع مقداردهی اولیه پایگاه داده...")
            initialize_database()
            
            # Create hidden_columns table if it doesn't exist
            conn = sqlite3.connect('cutting.db')
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS hidden_columns (
                    column_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    is_hidden INTEGER DEFAULT 1,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
            
            self.db_logger.info("مقداردهی اولیه پایگاه داده با موفقیت انجام شد")
        except Exception as e:
            self.db_logger.error(f"خطا در مقداردهی اولیه پایگاه داده: {e}")
            import traceback

            self.db_logger.error(traceback.format_exc())
            messagebox.showerror(
                "خطای پایگاه داده", f"خطا در هنگام مقداردهی اولیه پایگاه داده:\n{e}"
            )
            self.root.quit()

    def _ensure_projects_directory(self):
        """Creates the 'Projects' directory if it doesn't exist."""
        if not os.path.exists(PROJECTS_DIR):
            try:
                os.makedirs(PROJECTS_DIR)
            except OSError as e:
                messagebox.showerror(
                    "خطای ایجاد پوشه",
                    f"امکان ایجاد پوشه '{PROJECTS_DIR}' وجود نداشت:\n{e}",
                )
                self.root.quit()

    def _create_main_widgets(self):
        """Creates the main notebook for tabs."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

    def _create_order_tab(self):
        """Creates the content of the 'Order Form' tab."""
        self.tab_order = tk.Frame(self.notebook)
        self.notebook.add(self.tab_order, text="فرم سفارش مشتری")

        # --- Grid Configuration ---
        # --- Grid Configuration ---
        self.tab_order.columnconfigure(0, weight=1)
        self.tab_order.rowconfigure(0, weight=0)  # Top Buttons
        self.tab_order.rowconfigure(1, weight=0)  # Customer Info
        # <<-- NEW: Project Controls (Doesn't expand vertically)
        self.tab_order.rowconfigure(2, weight=0)
        # <<-- CHANGED: TreeView Frame (Expands vertically)
        self.tab_order.rowconfigure(3, weight=1)
        # --- Create UI Sections ---
        self._create_top_buttons(self.tab_order)
        self._create_customer_info_frame(self.tab_order)
        self._create_treeview_frame(self.tab_order)
        self._configure_row_tags()  # اطمینان از تنظیم اولیه تگ‌ها
        self._create_project_controls(self.tab_order)
        # Includes TreeView and Result Frame

    # --- START OF CODE TO ADD INSIDE CuttingApp CLASS ---

    def _create_project_controls(self, parent):
        """Creates the project selection, load, save buttons."""
        frame = tk.LabelFrame(parent, text="📂 مدیریت پروژه / سفارش")
        # Place this frame below customer info, so change grid row number
        frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        frame.columnconfigure(1, weight=1)  # Let combobox expand

        # Label for Combobox
        tk.Label(frame, text="انتخاب پروژه:").grid(
            row=0, column=0, padx=(10, 2), pady=5, sticky="w"
        )

        # Project Combobox
        self.project_combo = ttk.Combobox(frame, state="readonly", width=40)
        self.project_combo.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.project_combo.bind(
            "<<ComboboxSelected>>", self._on_project_selected
        )  # Add this event later

        # New Project Button
        btn_new = tk.Button(
            frame,
            text="➕ جدید",
            command=self._create_new_project_dialog,
            bg="#5cb85c",
            fg="white",
        )
        btn_new.grid(row=0, column=2, padx=5, pady=5)

        # Load Project Button (Maybe combine with selection? Or keep explicit)
        # btn_load = tk.Button(frame, text="🔄 بارگذاری", command=self._load_selected_project, bg="#0275d8", fg="white")
        # btn_load.grid(row=0, column=3, padx=5, pady=5)

        # Save Project Button
        btn_save = tk.Button(
            frame,
            text="💾 ذخیره پروژه",
            command=self._save_current_project,
            bg="#f0ad4e",
            fg="white",
        )
        btn_save.grid(row=0, column=4, padx=5, pady=5)

        # (Optional) Delete Button
        btn_delete = tk.Button(
            frame,
            text="🗑 حذف پروژه",
            command=self._delete_selected_project,
            bg="#d9534f",
            fg="white",
        )
        btn_delete.grid(row=0, column=5, padx=(10, 5), pady=5)

        # Variable to store the currently active project ID
        self.current_project_id = None

        # Load project list initially
        self._load_project_list()

    # --- Function to load project names into the combobox ---

    def _load_project_list(self):
        """Fetches projects from DB and populates the combobox."""
        try:
            self.project_logger.info("بارگذاری لیست پروژه‌ها")
            projects = get_all_projects()  # Function from database.py

            # ذخیره وضعیت انتخاب فعلی برای بازیابی بعدی
            current_selection = self.project_combo.get()
            current_project_id = self.current_project_id

            self.project_combo["values"] = [p["name"] for p in projects]
            # Store a mapping from name to ID for easy lookup
            self.project_id_map = {p["name"]: p["id"] for p in projects}

            self.project_logger.info(f"تعداد {len(projects)} پروژه بازیابی شد")

            # سعی در بازیابی انتخاب قبلی
            if current_selection and current_selection in self.project_id_map:
                self.project_combo.set(current_selection)
                self.project_logger.info(
                    f"انتخاب قبلی '{current_selection}' بازیابی شد"
                )
            else:
                self.project_combo.set("")

                # اگر هنوز یک پروژه‌ی فعال داریم اما نام آن در کمبوباکس نیست
                if current_project_id is not None:
                    # سعی در یافتن نام پروژه براساس ID
                    for name, pid in self.project_id_map.items():
                        if pid == current_project_id:
                            self.project_combo.set(name)
                            self.project_logger.info(
                                f"انتخاب براساس ID بازیابی شد: {name}"
                            )
                            break

            # اگر هیچ پروژه‌ای انتخاب نشده بود، پاکسازی داده‌ها
            if not self.project_combo.get():
                self.current_project_id = None
                self._clear_order_data()
                self.project_logger.info(
                    "هیچ پروژه‌ای انتخاب نشده - داده‌ها پاکسازی شدند"
                )

        except Exception as e:
            self.project_logger.error(f"خطا در بارگذاری لیست پروژه‌ها: {e}")
            import traceback

            traceback.print_exc()
            messagebox.showerror("خطا", f"خطا در بارگذاری لیست پروژه‌ها:\n{e}")

        # بروزرسانی وضعیت دکمه افزودن درب
        self._update_add_door_button_state()

    # --- Function to handle project selection change ---

    def _on_project_selected(self, event=None):
        """تابع مدیریت انتخاب پروژه از کمبوباکس"""
        print("Project selected:", self.project_combo.get())

        # بررسی اینکه پروژه فعلی تغییرات ذخیره نشده دارد
        selected_project_name = self.project_combo.get()

        # اگر پروژه جدیدی انتخاب نشده (کلیک روی همان پروژه فعلی)، کاری انجام نده
        if self.current_project_id is not None:
            current_project_name = None
            # پیدا کردن نام پروژه فعلی از روی آیدی
            for name, pid in self.project_id_map.items():
                if pid == self.current_project_id:
                    current_project_name = name
                    break

            # اگر روی همان پروژه فعلی کلیک شده، کاری نکن
            if current_project_name == selected_project_name:
                return

        # اگر تغییرات ذخیره نشده داریم، سؤال کن
        if self.has_unsaved_changes:
            response = messagebox.askyesnocancel(
                "ذخیره تغییرات",
                f"آیا می‌خواهید تغییرات پروژه فعلی را قبل از بارگذاری پروژه '{selected_project_name}' ذخیره کنید؟",
                icon="question",
            )

            if response is None:  # کاربر کنسل کرده
                # برگرداندن کمبوباکس به پروژه قبلی
                if self.current_project_id is not None:
                    for name, pid in self.project_id_map.items():
                        if pid == self.current_project_id:
                            self.project_combo.set(name)
                            break
                return

            elif response:  # کاربر بله را انتخاب کرده
                self._save_current_project()

        # ادامه روند بارگذاری پروژه جدید
        if not selected_project_name:
            self.current_project_id = None
            self._clear_order_data()
            return

        project_id = self.project_id_map.get(selected_project_name)
        if project_id:
            self.current_project_id = project_id
            self._update_add_door_button_state()

            # دریافت اطلاعات پروژه از دیتابیس
            project_data = get_project_details(project_id)
            self.project_logger.info(f"اطلاعات پروژه دریافت شد: {project_data}")

            try:
                # به‌روزرسانی برچسب‌های اطلاعات مشتری
                self.label_customer_name.config(text=project_data.get("cust_name", ""))
                self.label_customer_id.config(text=project_data.get("cust_id", ""))
                self.label_order_id.config(text=project_data.get("order_ref", ""))
                self.label_project_name.config(
                    text=project_data.get("name", "")
                )  # نام پروژه

                # اجبار به بروزرسانی رابط کاربری
                self.root.update_idletasks()

                # به‌روزرسانی عنوان پنجره
                self.root.title(f"برنامه برش - پروژه: {selected_project_name}")

                # بارگذاری داده‌های پروژه
                self._load_project_data(project_id)

                # بروزرسانی وضعیت تغییرات - پروژه تازه بارگذاری شده، پس تغییرات ندارد
                self.has_unsaved_changes = False

            except Exception as e:
                self.project_logger.error(f"خطا در بروزرسانی اطلاعات پروژه: {e}")
                import traceback

                traceback.print_exc()
        else:
            messagebox.showerror("خطا", "پروژه انتخاب شده معتبر نیست.")
            self.current_project_id = None
            self._clear_order_data()

    def _debug_labels(self):
        """چاپ مقادیر فعلی لیبل‌ها برای اشکال‌زدایی"""
        try:
            print("=== DEBUG LABELS VALUES ===")
            name_text = self.label_customer_name.cget("text")
            id_text = self.label_customer_id.cget("text")
            order_text = self.label_order_id.cget("text")

            print(f"Customer Name: '{name_text}'")
            print(f"Customer ID: '{id_text}'")
            print(f"Order ID: '{order_text}'")
            print("=== END DEBUG LABELS ===")
        except Exception as e:
            print(f"Error in debug_labels: {e}")

    def _clear_order_data(self):
        """Clears the main tree and customer info fields."""
        # Clear TreeView
        for item in self.tree.get_children():
            self.tree.delete(item)
        # Clear customer fields
        self.label_customer_name.config(text="")
        self.label_customer_id.config(text="")
        self.label_order_id.config(text="")
        self.label_project_name.config(text="")

        # Clear result display if open
        if self.output_visible:
            self._hide_result_frame()
        # Reset current project ID marker
        self.current_project_id = None
        self._update_add_door_button_state()
        self.root.title("برنامه برش پروفیل درب")  # Reset title

    # --- Function to load data for a specific project ID ---
    def _update_add_door_button_state(self):
        """دکمه افزودن درب را بر اساس وجود پروژه فعال، فعال/غیرفعال می کند."""
        try:
            # اگر self.btn_add_door هنوز ساخته نشده، کاری نکن
            if not hasattr(self, "btn_add_door"):
                return

            if self.current_project_id is None:
                # اگر پروژه ای فعال نیست، دکمه را غیرفعال کن و رنگش را خاکستری کن
                self.btn_add_door.config(state=tk.DISABLED, bg="grey")
                self.root.update_idletasks()  # برای اطمینان از اعمال تغییرات ظاهری
            else:
                # اگر پروژه فعال است، دکمه را فعال کن و رنگ اصلی اش را برگردان
                self.btn_add_door.config(
                    state=tk.NORMAL, bg="blue"
                )  # رنگ آبی اصلی دکمه
                self.root.update_idletasks()  # برای اطمینان از اعمال تغییرات ظاهری
        except tk.TclError:
            # اگر پنجره یا دکمه از بین رفته بود، مشکلی نیست
            pass
        except Exception as e:
            # برای خطاهای غیرمنتظره
            print(f"Error updating add door button state: {e}")

    def ensure_project_saved(self, action_description="انجام این عملیات"):
        """بررسی می‌کند آیا پروژه ذخیره شده و در صورت نیاز از کاربر می‌خواهد پروژه را ذخیره کند.

        Returns:
            bool: True اگر کاربر مایل به ادامه باشد، False اگر عملیات را لغو کند
        """
        if self.current_project_id is None:
            messagebox.showwarning(
                "پروژه انتخاب نشده",
                f"برای {action_description}، ابتدا باید یک پروژه ایجاد کرده و آن را ذخیره کنید.",
            )
            return False

        # بررسی وجود تغییرات ذخیره نشده
        if self.has_unsaved_changes:
            response = messagebox.askyesnocancel(
                "ذخیره پروژه",
                f"آیا مایلید قبل از {action_description} تغییرات فعلی پروژه را ذخیره کنید؟",
                icon="question",
            )

            if response is None:  # کاربر دکمه لغو را زده است
                return False
            elif response:  # کاربر دکمه بله را زده است
                self._save_current_project()

        return True  # ادامه عملیات

    def _load_project_data(self, project_id):
        """Loads project details and door data for the given project ID."""
        self.project_logger.info(f"شروع بارگذاری داده‌های پروژه با ID: {project_id}")

        try:
            # 1. Get Project Details
            project_details = get_project_details(project_id)
            if not project_details:
                messagebox.showerror("خطا", f"پروژه با ID {project_id} یافت نشد.")
                self._load_project_list()  # Refresh list in case it was deleted
                return

            # Update customer info fields
            self.label_customer_name.config(text=project_details.get("cust_name", ""))
            self.label_customer_id.config(text=project_details.get("cust_id", ""))
            self.label_order_id.config(text=project_details.get("order_ref", ""))

            # اجبار به بروزرسانی رابط کاربری
            self.root.update_idletasks()

            # Update window title
            self.root.title(
                f"برنامه برش - پروژه: {project_details.get('name', 'ناشناخته')}"
            )

            # 2. Get Doors for the Project
            doors = get_doors_for_project(project_id)
            self.project_logger.info(f"تعداد درب‌های بازیابی شده: {len(doors)}")

            # 3. Clear existing tree data
            for item in self.tree.get_children():
                self.tree.delete(item)

            # 4. Populate TreeView
            current_tree_keys = list(self.tree["columns"])
            # Handle case where tree isn't built yet
            if not current_tree_keys or current_tree_keys == ("",):
                # Rebuild might reset tags, so configure after population
                self._rebuild_main_tree()
                current_tree_keys = list(self.tree["columns"])

            self.project_logger.info("شروع درج ردیف‌ها در درخت")
            all_inserted_ids = []  # لیستی برای نگهداری ID های واقعی اضافه شده

            for door_data in doors:
                values_tuple = []
                for key in current_tree_keys:
                    values_tuple.append(door_data.get(key, ""))
                while len(values_tuple) < len(current_tree_keys):
                    values_tuple.append("")

                row_tag = door_data.get("row_color_tag", DEFAULT_ROW_TAG)
                db_row_id = door_data.get("db_id")
                # ممکن است db_row_id معتبر نباشد یا برای ردیف‌های جدید خالی باشد
                iid_to_use = str(db_row_id) if db_row_id else None

                try:
                    self.tree.insert(
                        "",
                        "end",
                        iid=iid_to_use,
                        values=tuple(values_tuple),
                        tags=(row_tag,),
                    )

                    # گرفتن ID واقعی که Treeview استفاده کرده
                    actual_item_id = self.tree.get_children()[-1]
                    all_inserted_ids.append(actual_item_id)  # اضافه کردن به لیست
                    self.project_logger.debug(
                        f"ردیف با شناسه {actual_item_id} و تگ {row_tag} افزوده شد"
                    )

                except tk.TclError as e:
                    # اگر iid تکراری بود یا مشکل دیگری بود، بدون iid امتحان کن
                    self.project_logger.warning(
                        f"خطا در درج ردیف ID={iid_to_use}, Tag={row_tag}: {e}"
                    )
                    try:
                        self.tree.insert(
                            "", "end", values=tuple(values_tuple), tags=(row_tag,)
                        )
                        # گرفتن ID واقعی که Treeview استفاده کرده
                        actual_item_id = self.tree.get_children()[-1]
                        all_inserted_ids.append(actual_item_id)  # اضافه کردن به لیست
                        self.project_logger.debug(
                            f"ردیف با شناسه {actual_item_id} (جایگزین) و تگ {row_tag} افزوده شد"
                        )
                    except Exception as final_e:
                        self.project_logger.error(f"خطای نهایی در درج ردیف: {final_e}")

            self.project_logger.info(
                f"تعداد {len(all_inserted_ids)} ردیف با موفقیت درج شد"
            )

            # بررسی تگ‌ها بلافاصله بعد از حلقه
            self.project_logger.debug("بررسی تگ‌ها بلافاصله بعد از درج")
            if not all_inserted_ids:
                self.project_logger.warning("هیچ ردیفی درج نشد.")
            for item_id_check in all_inserted_ids:  # استفاده از ID های واقعی
                try:
                    tags_after_insert = self.tree.item(item_id_check, "tags")
                    self.project_logger.debug(
                        f"تگ‌های آیتم '{item_id_check}' بعد از درج: {tags_after_insert}"
                    )
                except tk.TclError:
                    self.project_logger.warning(
                        f"نمی‌توان تگ‌های آیتم '{item_id_check}' را بلافاصله بعد از درج دریافت کرد."
                    )

            # اطمینان از پیکربندی صحیح رنگ‌های ردیف‌ها - مهم است که بعد از اضافه شدن همه آیتم‌ها باشد
            self.project_logger.info(
                "فراخوانی _configure_row_tags() بعد از بارگذاری همه ردیف‌ها"
            )
            self._configure_row_tags()  # این باید صدا زده شود

            # بررسی مجدد تگ‌ها بعد از configure
            self.project_logger.debug(
                "بررسی مجدد تگ‌ها بعد از فراخوانی _configure_row_tags"
            )
            for item_id_check in all_inserted_ids:  # استفاده از ID های واقعی
                try:
                    tags_after_configure = self.tree.item(item_id_check, "tags")
                    self.project_logger.debug(
                        f"تگ‌های آیتم '{item_id_check}' بعد از تنظیم: {tags_after_configure}"
                    )
                except tk.TclError:
                    self.project_logger.warning(
                        f"نمی‌توان تگ‌های آیتم '{item_id_check}' را بعد از تنظیم دریافت کرد."
                    )

            # نشان دادن پیام موفقیت
            if doors:
                self.project_logger.info(
                    f"پروژه {project_details.get('name')} با {len(doors)} درب با موفقیت بارگذاری شد"
                )
            else:
                self.project_logger.info(
                    f"پروژه {project_details.get('name')} بدون درب بارگذاری شد"
                )

        except Exception as e:
            self.project_logger.error(f"خطا در بارگذاری اطلاعات پروژه: {e}")
            import traceback

            traceback.print_exc()  # چاپ خطای جزئی برای اشکال‌زدایی
            messagebox.showerror("خطا", f"خطا در بارگذاری اطلاعات پروژه:\n{e}")
            self._clear_order_data()

    def _save_current_project(self):
        """Saves the current TreeView data and project details to the database."""
        if self.current_project_id is None:
            # If no project is loaded, maybe prompt to create/select one?
            # For now, try saving based on entered customer info as a *new* project.
            if not messagebox.askyesno(
                "پروژه جدید؟",
                "هیچ پروژه‌ای بارگذاری نشده است. آیا می‌خواهید یک پروژه جدید با اطلاعات مشتری وارد شده ایجاد و ذخیره کنید؟",
            ):
                return
            # Attempt to create a new project first
            project_name = (
                self.label_customer_name.get().strip()
            )  # یا مقدار لیبل را بگیرید
            customer_name = self.label_customer_name.get().strip()
            customer_id = self.label_customer_id.get().strip()
            order_ref = self.label_order_id.get().strip()

            if not project_name:
                # You NEED a project name. You could auto-generate one or prompt the user.
                # Example auto-name
                project_name = (
                    f"پروژه {customer_name}"
                    if customer_name
                    else f"پروژه جدید {int(time.time())}"
                )
                result = tk.simpledialog.askstring(
                    "نام پروژه",
                    "لطفا یک نام منحصر به فرد برای پروژه وارد کنید:",
                    initialvalue=project_name,
                    parent=self.root,
                )
                if not result:
                    return  # User cancelled
                project_name = result.strip()
                if not project_name:
                    messagebox.showerror("خطا", "نام پروژه نمی‌تواند خالی باشد.")
                    return

            try:
                new_project_id = add_project(
                    project_name, customer_name, customer_id, order_ref
                )
                self.current_project_id = new_project_id
                self._load_project_list()  # Refresh the list
                # Select the new project in the combo
                self.project_combo.set(project_name)
                # Update title
                self.root.title(f"برنامه برش - پروژه: {project_name}")
                messagebox.showinfo(
                    "پروژه ایجاد شد",
                    f"پروژه '{project_name}' ایجاد شد. اکنون داده‌های جدول ذخیره می‌شوند.",
                )
                # Now fall through to save the door data...

            except (
                ValueError
            ) as ve:  # Handles duplicate project name error from add_project
                messagebox.showerror("خطا در ایجاد پروژه", str(ve))
                return  # Stop saving
            except Exception as e:
                messagebox.showerror(
                    "خطا در ایجاد پروژه", f"خطا در ایجاد پروژه جدید:\n{e}"
                )
                return  # Stop saving

        # --- Now proceed with saving door data for the current_project_id ---
        try:
            # Optional: Update project details if they changed in the entry fields
            current_project_name_in_combo = self.project_combo.get()

            # 1. Delete existing doors for this project (simple overwrite strategy)
            delete_all_doors_for_project(self.current_project_id)

            # 2. Iterate through TreeView and add each row to the DB
            current_tree_cols_keys = list(self.tree["columns"])
            saved_count = 0
            for item_id in self.tree.get_children():
                try:
                    current_values = list(self.tree.item(item_id, "values"))
                    tags = self.tree.item(item_id, "tags")
                    # Find the color tag (assuming it's the last one or one of the known colors)
                    color_tag = DEFAULT_ROW_TAG  # Default
                    known_colors = ["yellow", "lightgreen", "lightblue", "white"]
                    for tag in reversed(tags):  # Check from the end
                        if tag in known_colors:
                            color_tag = tag
                            break

                    # Create a dictionary of data for this door row
                    door_data = {}
                    for i, key in enumerate(current_tree_cols_keys):
                        if i < len(current_values):
                            door_data[key] = current_values[i]
                        else:
                            door_data[key] = ""  # Ensure all keys exist

                    door_data["row_color_tag"] = color_tag  # Add the color tag

                    # Add this door to the project in the database
                    add_door_to_project(self.current_project_id, door_data)
                    saved_count += 1

                except Exception as e:
                    self.project_logger.error(f"خطا در ذخیره ردیف {item_id}: {e}")
                    import traceback

                    traceback.print_exc()

            messagebox.showinfo(
                "ذخیره موفق",
                f"{saved_count} ردیف درب برای پروژه '{self.project_combo.get()}' با موفقیت ذخیره شد.",
            )
            self.has_unsaved_changes = False  # تغییرات ذخیره شده‌اند

        except Exception as e:
            messagebox.showerror(
                "خطا در ذخیره", f"خطا در هنگام ذخیره اطلاعات پروژه:\n{e}"
            )
            import traceback

            traceback.print_exc()  # Print detailed error for debugging

    # تابع مهم برای ردیابی تغییرات درخت
    def _track_treeview_changes(self, event=None):
        """ردیابی تغییرات در درخت و تنظیم متغیر has_unsaved_changes"""
        self.has_unsaved_changes = True
        self.project_logger.debug("تغییراتی در داده‌ها انجام شد و پرچم تغییرات تنظیم شد")

    def _create_top_buttons(self, parent):
        """Creates the row of buttons at the top."""
        frame = tk.Frame(parent)
        frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 0))
        # Give buttons equal weight to distribute space
        button_specs = [
            ("➕ افزودن درب", self.open_add_door_dialog, "blue"),
            ("\U0001f4ca خروجی Excel", self.export_to_excel, "green"),
            ("📄 PDF جدول", self.export_table_to_pdf, "red"),  # Renamed for clarity
            ("ویرایش گروهی", self.open_batch_edit_dialog, "orange"),
            ("⚙️ تنظیمات", self.open_settings_window, "gray"),
            ("📏 محاسبه برش", self.calculate_cutting_from_orders, "#0066cc"),
            # ("🔽 نمایش نتیجه", self.toggle_result_frame, "gray"), # Toggle button logic added inside calculate
        ]
        for i, (text, command, color) in enumerate(button_specs):
            frame.columnconfigure(i, weight=1)
            btn = tk.Button(frame, text=text, command=command, bg=color, fg="white")
            if text == "➕ افزودن درب":
                self.btn_add_door = btn
                self._update_add_door_button_state()  # تنظیم وضعیت اولیه دکمه
            btn.grid(row=0, column=i, padx=5, pady=5, sticky="nsew")

    def _create_new_project_dialog(self):
        """Opens a simple dialog to get new project details."""
        # اگر پروژه فعلی تغییرات ذخیره نشده دارد، از کاربر سوال شود
        if self.current_project_id is not None and not self.ensure_project_saved(
            "ایجاد پروژه جدید"
        ):
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("ایجاد پروژه جدید")
        dialog.geometry("400x260")
        dialog.transient(self.root)
        dialog.grab_set()

        frame = tk.Frame(dialog, padx=15, pady=15)
        frame.pack(fill="both", expand=True)

        fields = ["نام پروژه*", "نام مشتری", "شماره محک", "شماره سفارش"]
        entries = {}

        for i, label_text in enumerate(fields):
            tk.Label(frame, text=label_text + ":").grid(
                row=i, column=0, padx=5, pady=8, sticky="e"
            )
            entry = tk.Entry(frame, width=35)
            entry.grid(row=i, column=1, padx=5, pady=8, sticky="ew")
            entries[label_text] = entry

        frame.columnconfigure(1, weight=1)
        entries["نام پروژه*"].focus_set()  # Focus on the required field

        def submit_new_project():
            project_name = entries["نام پروژه*"].get().strip()
            if not project_name:
                messagebox.showerror("خطا", "نام پروژه الزامی است.", parent=dialog)
                return

            customer_name = entries["نام مشتری"].get().strip()
            customer_id = entries["شماره محک"].get().strip()
            order_ref = entries["شماره سفارش"].get().strip()

            try:
                new_id = add_project(
                    project_name, customer_name, customer_id, order_ref
                )

                # ذخیره آی‌دی پروژه جدید و بروزرسانی رابط کاربری
                self.current_project_id = new_id
                self.has_unsaved_changes = False

                messagebox.showinfo(
                    "موفق", f"پروژه '{project_name}' با موفقیت ایجاد شد.", parent=dialog
                )

                dialog.destroy()

                # بروزرسانی لیست پروژه‌ها و انتخاب پروژه جدید
                self._load_project_list()

                # پاکسازی داده‌های قبلی از treeview
                for item in self.tree.get_children():
                    self.tree.delete(item)

                # بروزرسانی متغیرهای کلاس برای پروژه جدید
                self.label_customer_name.config(text=customer_name)
                self.label_customer_id.config(text=customer_id)
                self.label_order_id.config(text=order_ref)
                self.label_project_name.config(text=project_name)

                # بروزرسانی عنوان پنجره
                self.root.title(f"برنامه برش - پروژه: {project_name}")

                # بروزرسانی کمبوباکس - اطمینان از انتخاب پروژه جدید
                if project_name in self.project_id_map:
                    self.project_combo.set(project_name)

                # فعال کردن دکمه اضافه کردن درب
                self._update_add_door_button_state()

                # لاگ برای اشکال‌زدایی
                self.project_logger.info(
                    f"پروژه جدید '{project_name}' با ID={new_id} ایجاد شد"
                )

            except ValueError as ve:  # گرفتن خطای تکراری بودن نام پروژه
                messagebox.showerror("خطا", str(ve), parent=dialog)
            except Exception as e:
                self.project_logger.error(f"خطا در ایجاد پروژه: {e}")
                messagebox.showerror("خطا", f"خطا در ایجاد پروژه:\n{e}", parent=dialog)

        # فریم دکمه‌ها
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=10)

        # دکمه ایجاد با رنگ سبز
        btn_ok = tk.Button(
            button_frame,
            text="ایجاد",
            command=submit_new_project,
            bg="green",
            fg="white",
        )
        btn_ok.pack(side=tk.LEFT, padx=10)

        # دکمه انصراف
        btn_cancel = tk.Button(button_frame, text="انصراف", command=dialog.destroy)
        btn_cancel.pack(side=tk.LEFT, padx=10)

        # اضافه کردن امکان فشردن Enter برای ثبت پروژه
        dialog.bind("<Return>", lambda event: submit_new_project())

    # --- Function to handle deleting the selected project ---

    def _delete_selected_project(self):
        """Deletes the project currently selected in the combobox."""
        selected_project_name = self.project_combo.get()
        if not selected_project_name:
            messagebox.showwarning(
                "انتخاب نشده", "لطفاً پروژه‌ای را برای حذف از لیست انتخاب کنید."
            )
            return

        project_id_to_delete = self.project_id_map.get(selected_project_name)
        if not project_id_to_delete:
            messagebox.showerror("خطا", "پروژه انتخاب شده معتبر نیست.")
            return

        if messagebox.askyesno(
            "تایید حذف",
            f"آیا از حذف پروژه '{selected_project_name}' و تمام درب‌های مرتبط با آن مطمئن هستید؟\nاین عملیات قابل بازگشت نیست!",
            icon="warning",
        ):
            try:
                # --- IMPORT NEEDED AT TOP ---
                # from database import delete_project
                # --- END IMPORT ---
                # This uses ON DELETE CASCADE
                delete_project(project_id_to_delete)
                messagebox.showinfo(
                    "حذف موفق", f"پروژه '{selected_project_name}' حذف شد."
                )
                self._load_project_list()  # Refresh combobox, which also clears the view
                self._update_add_door_button_state()
            except Exception as e:
                messagebox.showerror("خطا در حذف", f"خطا در هنگام حذف پروژه:\n{e}")

            # self.btn_toggle_result = frame.winfo_children()[-1] # Store ref if needed, maybe not necessary

    # --- END OF CODE TO ADD INSIDE CuttingApp CLASS ---

    # 2. تغییر در تابع _create_customer_info_frame برای نمایش تاریخ شمسی:

    def _create_customer_info_frame(self, parent):
        """ایجاد فریم اطلاعات مشتری با ظاهر بهتر."""
        frame = tk.LabelFrame(
            parent, text="📋 اطلاعات مشتری", font=("Tahoma", 10, "bold")
        )
        frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        # تنظیم ستون‌ها برای انعطاف‌پذیری بهتر
        frame.columnconfigure((0, 2, 4), weight=0)  # ستون‌های برچسب
        frame.columnconfigure((1, 3, 5), weight=1)  # ستون‌های مقدار

        # اضافه کردن رنگ پس‌زمینه به فریم
        frame.configure(bg="#f0f8ff")  # آبی بسیار روشن

        # سبک یکسان برای همه برچسب‌ها
        label_style = {"font": ("Tahoma", 9), "bg": "#f0f8ff"}
        value_style = {
            "relief": "groove",
            "bd": 1,
            "bg": "white",
            "anchor": "w",
            "width": 30,
        }

        # نام مشتری
        tk.Label(frame, text="نام مشتری:", **label_style).grid(
            row=0, column=0, padx=5, pady=8, sticky="e"
        )
        self.label_customer_name = tk.Label(frame, **value_style)
        self.label_customer_name.grid(row=0, column=1, padx=5, pady=8, sticky="ew")

        # شماره محک
        tk.Label(frame, text="شماره محک:", **label_style).grid(
            row=0, column=2, padx=5, pady=8, sticky="e"
        )
        self.label_customer_id = tk.Label(frame, **value_style)
        self.label_customer_id.grid(row=0, column=3, padx=5, pady=8, sticky="ew")

        # شماره سفارش
        tk.Label(frame, text="شماره سفارش:", **label_style).grid(
            row=1, column=0, padx=5, pady=8, sticky="e"
        )
        self.label_order_id = tk.Label(frame, **value_style)
        self.label_order_id.grid(row=1, column=1, padx=5, pady=8, sticky="ew")

        # نام پروژه - نمایش نام پروژه فعلی از کمبوباکس (اگر موجود باشد)
        tk.Label(frame, text="نام پروژه:", **label_style).grid(
            row=1, column=2, padx=5, pady=8, sticky="e"
        )
        self.label_project_name = tk.Label(frame, **value_style)
        self.label_project_name.grid(row=1, column=3, padx=5, pady=8, sticky="ew")

        # تاریخ (تغییر به تاریخ شمسی)
        tk.Label(frame, text="تاریخ:", **label_style).grid(
            row=1, column=4, padx=5, pady=8, sticky="e"
        )

        # تاریخ شمسی فعلی
        shamsi_date = jdatetime.datetime.now().strftime("%Y/%m/%d")

        # ایجاد یک فریم برای نگهداری تاریخ و دکمه انتخاب تاریخ
        date_frame = tk.Frame(frame, bg="#f0f8ff")
        date_frame.grid(row=1, column=5, padx=5, pady=8, sticky="ew")

        # نمایش تاریخ
        self.label_date = tk.Label(date_frame, text=shamsi_date, **value_style)
        self.label_date.pack(side=tk.LEFT, expand=True, fill="x")

        # دکمه انتخاب تاریخ
        btn_select_date = tk.Button(
            date_frame,
            text="📅",
            command=self._show_date_picker,
            bg="#dcdcdc",
            relief="groove",
            width=2,
        )
        btn_select_date.pack(side=tk.LEFT, padx=(2, 0))

        return frame

    # 3. اضافه کردن تابع _show_date_picker برای انتخاب تاریخ شمسی:

    def _show_date_picker(self):
        """نمایش پنجره انتخاب تاریخ شمسی"""
        try:
            # ایجاد پنجره انتخاب تاریخ
            date_picker = tk.Toplevel(self.root)
            date_picker.title("انتخاب تاریخ")
            date_picker.geometry("300x320")
            date_picker.transient(self.root)
            date_picker.grab_set()

            # دریافت تاریخ فعلی شمسی
            current_date_text = self.label_date.cget("text").strip()
            try:
                # اگر فرمت تاریخ درست باشد، آن را تجزیه می‌کنیم
                current_year, current_month, current_day = map(
                    int, current_date_text.split("/")
                )
                current_date = jdatetime.date(current_year, current_month, current_day)
            except:
                # در صورت بروز خطا، از تاریخ امروز استفاده می‌کنیم
                current_date = jdatetime.date.today()

            # متغیرهای Tkinter برای سال، ماه و روز
            selected_year = tk.StringVar(value=str(current_date.year))
            selected_month = tk.StringVar(value=str(current_date.month))
            selected_day = tk.StringVar(value=str(current_date.day))

            # لیست سال‌ها، ماه‌ها و روزها
            years = [
                str(y) for y in range(current_date.year - 10, current_date.year + 11)
            ]
            months = [str(m) for m in range(1, 13)]

            # فریم اصلی
            main_frame = tk.Frame(date_picker, padx=15, pady=15)
            main_frame.pack(fill="both", expand=True)

            # عنوان
            tk.Label(
                main_frame, text="انتخاب تاریخ شمسی", font=("Tahoma", 12, "bold")
            ).pack(pady=(0, 10))

            # فریم انتخاب سال، ماه و روز
            date_select_frame = tk.Frame(main_frame)
            date_select_frame.pack(fill="x", pady=10)

            # انتخاب سال
            year_frame = tk.LabelFrame(date_select_frame, text="سال")
            year_frame.pack(side=tk.LEFT, padx=5, fill="both", expand=True)
            year_sb = tk.Scrollbar(year_frame)
            year_sb.pack(side=tk.RIGHT, fill="y")
            year_listbox = tk.Listbox(
                year_frame, yscrollcommand=year_sb.set, exportselection=0, height=7
            )
            year_listbox.pack(fill="both", expand=True)
            year_sb.config(command=year_listbox.yview)

            # پر کردن لیست‌باکس سال‌ها
            for year in years:
                year_listbox.insert(tk.END, year)
                if year == selected_year.get():
                    year_listbox.selection_set(years.index(year))
                    year_listbox.see(years.index(year))

            # انتخاب ماه
            month_frame = tk.LabelFrame(date_select_frame, text="ماه")
            month_frame.pack(side=tk.LEFT, padx=5, fill="both", expand=True)
            month_listbox = tk.Listbox(month_frame, exportselection=0, height=7)
            month_listbox.pack(fill="both", expand=True)

            # پر کردن لیست‌باکس ماه‌ها
            month_names = [
                "فروردین",
                "اردیبهشت",
                "خرداد",
                "تیر",
                "مرداد",
                "شهریور",
                "مهر",
                "آبان",
                "آذر",
                "دی",
                "بهمن",
                "اسفند",
            ]
            for i, month_name in enumerate(month_names, 1):
                month_listbox.insert(tk.END, f"{i} - {month_name}")
                if str(i) == selected_month.get():
                    month_listbox.selection_set(i - 1)
                    month_listbox.see(i - 1)

            # انتخاب روز
            day_frame = tk.LabelFrame(date_select_frame, text="روز")
            day_frame.pack(side=tk.LEFT, padx=5, fill="both", expand=True)
            day_listbox = tk.Listbox(day_frame, exportselection=0, height=7)
            day_listbox.pack(fill="both", expand=True)

            def update_days(*args):
                """به‌روزرسانی روزهای ماه بر اساس سال و ماه انتخاب شده"""
                day_listbox.delete(0, tk.END)

                # دریافت سال و ماه انتخاب شده
                try:
                    year_sel = int(years[year_listbox.curselection()[0]])
                    month_sel = month_listbox.curselection()[0] + 1

                    # تعیین تعداد روزهای ماه انتخاب شده
                    if month_sel <= 6:  # فروردین تا شهریور
                        days_in_month = 31
                    elif month_sel <= 11:  # مهر تا بهمن
                        days_in_month = 30
                    else:  # اسفند
                        # بررسی سال کبیسه
                        if jdatetime.date(year_sel, 12, 29).isleap():
                            days_in_month = 30
                        else:
                            days_in_month = 29

                    # پر کردن لیست‌باکس روزها
                    for day in range(1, days_in_month + 1):
                        day_listbox.insert(tk.END, str(day))
                        if str(day) == selected_day.get():
                            day_listbox.selection_set(day - 1)
                            day_listbox.see(day - 1)
                except (IndexError, ValueError):
                    # در صورت بروز خطا، 31 روز نمایش می‌دهیم
                    for day in range(1, 32):
                        day_listbox.insert(tk.END, str(day))

            # رویدادهای انتخاب سال و ماه
            year_listbox.bind("<<ListboxSelect>>", update_days)
            month_listbox.bind("<<ListboxSelect>>", update_days)

            # اجرای اولیه برای نمایش روزها
            if not year_listbox.curselection():
                year_index = (
                    years.index(str(current_date.year))
                    if str(current_date.year) in years
                    else 0
                )
                year_listbox.selection_set(year_index)
            if not month_listbox.curselection():
                month_listbox.selection_set(current_date.month - 1)

            update_days()

            # فریم دکمه‌ها
            button_frame = tk.Frame(main_frame)
            button_frame.pack(fill="x", pady=(15, 0))

            def confirm_date():
                """تأیید و ذخیره تاریخ انتخاب شده"""
                try:
                    selected_year = int(years[year_listbox.curselection()[0]])
                    selected_month = month_listbox.curselection()[0] + 1
                    selected_day = int(day_listbox.get(day_listbox.curselection()[0]))

                    # اعتبارسنجی تاریخ
                    try:
                        selected_date = jdatetime.date(
                            selected_year, selected_month, selected_day
                        )
                        formatted_date = selected_date.strftime("%Y/%m/%d")
                        self.label_date.config(text=formatted_date)
                        date_picker.destroy()
                    except ValueError as e:
                        messagebox.showerror(
                            "خطا در تاریخ",
                            f"تاریخ انتخاب شده معتبر نیست: {e}",
                            parent=date_picker,
                        )
                except (IndexError, ValueError):
                    messagebox.showerror(
                        "خطا", "لطفاً سال، ماه و روز را انتخاب کنید.", parent=date_picker
                    )

            def use_today():
                """استفاده از تاریخ امروز"""
                today = jdatetime.date.today()
                formatted_today = today.strftime("%Y/%m/%d")
                self.label_date.config(text=formatted_today)
                date_picker.destroy()

            # دکمه‌های تأیید و انصراف
            btn_today = tk.Button(
                button_frame,
                text="امروز",
                command=use_today,
                bg="#5cb85c",
                fg="white",
                width=10,
            )
            btn_today.pack(side=tk.LEFT, padx=5)

            btn_confirm = tk.Button(
                button_frame,
                text="تأیید",
                command=confirm_date,
                bg="#337ab7",
                fg="white",
                width=10,
            )
            btn_confirm.pack(side=tk.LEFT, padx=5)

            btn_cancel = tk.Button(
                button_frame, text="انصراف", command=date_picker.destroy, width=10
            )
            btn_cancel.pack(side=tk.LEFT, padx=5)

            # نمایش پنجره و منتظر ماندن
            date_picker.wait_window()

        except Exception as e:
            messagebox.showerror("خطا", f"خطا در نمایش انتخابگر تاریخ: {e}")

    def _create_treeview_frame(self, parent):
        """Creates the frame containing the TreeView and the result display area."""
        self.frame_tree_area = tk.Frame(parent)
        self.frame_tree_area.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        self.frame_tree_area.columnconfigure(0, weight=1)
        # TreeView takes most space initially
        self.frame_tree_area.rowconfigure(0, weight=1)
        self.frame_tree_area.rowconfigure(1, weight=0)  # Scrollbar
        # Result frame, initially no weight
        self.frame_tree_area.rowconfigure(2, weight=0)

        # --- TreeView ---
        # Columns will be set by _load_initial_tree_columns and _rebuild_main_tree
        self.tree = ttk.Treeview(
            self.frame_tree_area, show="headings", selectmode="extended"
        )
        self.tree.grid(row=0, column=0, sticky="nsew")

        # --- Scrollbars ---
        scrollbar_y = tk.Scrollbar(
            self.frame_tree_area, orient="vertical", command=self.tree.yview
        )
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x = tk.Scrollbar(
            self.frame_tree_area, orient="horizontal", command=self.tree.xview
        )
        scrollbar_x.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.tree.configure(
            yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set
        )

        # --- Result Frame (Initially Hidden) ---
        self.frame_result = tk.Frame(self.frame_tree_area)
        # Don't grid it yet, grid it when showing results
        self.frame_result.rowconfigure(0, weight=1)
        self.frame_result.columnconfigure(0, weight=1)

        self.result_display = tk.Text(
            self.frame_result, height=10, wrap="word", relief="sunken", borderwidth=1
        )
        self.result_display.grid(row=0, column=0, sticky="nsew")
        # Optional scrollbar for results text
        result_scrollbar = tk.Scrollbar(
            self.frame_result, orient="vertical", command=self.result_display.yview
        )
        result_scrollbar.grid(row=0, column=1, sticky="ns")
        self.result_display.configure(yscrollcommand=result_scrollbar.set)

        btn_close_result = tk.Button(
            self.frame_result,
            text="\u274c",  # Smaller close button
            bg="lightgrey",
            relief="raised",
            borderwidth=1,
            command=self._hide_result_frame,
        )
        btn_close_result.grid(
            row=0, column=0, sticky="ne", padx=2, pady=2
        )  # Inside corner

        # --- Bindings ---
        self.tree.bind("<Button-3>", self._on_tree_right_click)
        self.tree.bind("<Motion>", self._on_tree_hover)
        self.tree.bind("<Leave>", self._on_tree_leave)
        # Consider adding <Double-1> for editing a row
        # اضافه کردن بایندینگ‌های تشخیص تغییرات
        self.tree.bind(
            "<<TreeviewSelect>>",
            lambda event: (
                self._track_treeview_changes()
                if self.current_project_id is not None
                else None
            ),
        )
        self.tree.bind(
            "<KeyRelease>",
            lambda event: (
                self._track_treeview_changes()
                if self.current_project_id is not None
                else None
            ),
        )

    def _load_initial_tree_columns(self):
        """Loads base and active custom columns into the TreeView on startup."""
        self._rebuild_main_tree()  # Use the rebuild function for initial setup too

    def _get_active_custom_columns(self):
        """Fetches active custom column names and optionally IDs from the database."""
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            # Fetch both id and name if needed elsewhere, otherwise just name
            cursor.execute(
                "SELECT column_name FROM custom_columns WHERE is_active = 1 ORDER BY id"
            )
            custom_cols = [row[0] for row in cursor.fetchall()]
            conn.close()
            return custom_cols
        except Exception as e:
            messagebox.showerror(
                "خطای پایگاه داده", f"خطا در خواندن ستون‌های سفارشی:\n{e}"
            )
            return []

    # --- START OF REPLACEMENT for _rebuild_main_tree method ---

    # --- START OF REPLACEMENT for _rebuild_main_tree method ---

    def _rebuild_main_tree(self, preserve_data=False):
        """
        Reconfigures TreeView columns ensuring unique keys and 'tozihat' last.
        """
        print("DEBUG: Rebuilding main tree...")  # Debug Print
        try:
            custom_columns_data = get_active_custom_columns_data()
            custom_col_keys = [col["key"] for col in custom_columns_data]
            custom_col_map = {col["key"]: col["display"] for col in custom_columns_data}
            # Debug Print
            print(f"DEBUG: Fetched custom keys: {custom_col_keys}")

            # --- Build the final, unique, ordered list of keys ---
            final_ordered_keys = []
            seen_keys = set()  # Keep track of keys already added

            # 1. Add base keys first (excluding tozihat), ensuring uniqueness
            last_column_key = "tozihat"
            for key in BASE_COLUMN_KEYS:
                if key != last_column_key and key not in seen_keys:
                    final_ordered_keys.append(key)
                    seen_keys.add(key)

            # 2. Add custom keys, ensuring uniqueness and avoiding base keys already added
            for key in custom_col_keys:
                if key not in seen_keys:
                    final_ordered_keys.append(key)
                    seen_keys.add(key)

            # 3. Add the last column key ('tozihat') if it's a base key and not already added
            if last_column_key in BASE_COLUMN_KEYS and last_column_key not in seen_keys:
                final_ordered_keys.append(last_column_key)
                # Not strictly needed here, but good practice
                seen_keys.add(last_column_key)

            # Debug Print
            print(f"DEBUG: Final ordered keys for tree columns: {final_ordered_keys}")
            all_column_keys = final_ordered_keys

            # --- Preserve Data ---
            existing_data = []
            if preserve_data:
                # ... (Preserve data logic remains the same as before) ...
                old_columns = list(self.tree["columns"])
                for item_id in self.tree.get_children():
                    values = self.tree.item(item_id, "values")
                    tags = self.tree.item(item_id, "tags")
                    row_data = {old_columns[i]: values[i] for i in range(len(values))}
                    existing_data.append(
                        {"id": item_id, "data": row_data, "tags": tags}
                    )

            # --- Configure Tree Columns and Display ---
            print(f"DEBUG: Setting tree['columns'] to: {tuple(all_column_keys)}")
            self.tree["columns"] = tuple(all_column_keys)
            # Start by displaying all columns in the correct order
            print(f"DEBUG: Setting tree['displaycolumns'] to: {tuple(all_column_keys)}")
            self.tree["displaycolumns"] = tuple(all_column_keys)

            # --- Set Headings and Widths ---
            base_col_headings = {key: text for key, text in BASE_COLUMNS_DATA}
            print("DEBUG: Setting headings and column properties...")
            for col_key in all_column_keys:
                # Determine heading text
                if col_key in base_col_headings:
                    heading_text = base_col_headings[col_key]
                elif col_key in custom_col_map:
                    heading_text = custom_col_map[col_key]
                else:
                    heading_text = col_key  # Fallback
                self.tree.heading(col_key, text=heading_text, anchor="center")
                # Determine width and stretch
                width = 100
                stretch = tk.YES
                if col_key == "makan":
                    width = 120
                elif col_key == last_column_key:
                    width = 150
                    stretch = tk.NO
                self.tree.column(col_key, width=width, anchor="center", stretch=stretch)

            # --- Re-insert data if preserved ---
            if preserve_data:
                print("DEBUG: Re-inserting preserved data...")
                # Clear existing items AFTER configuring columns/headings
                for item_id in self.tree.get_children():
                    self.tree.delete(item_id)
                for preserved_item in existing_data:
                    new_values = [
                        preserved_item["data"].get(key, "") for key in all_column_keys
                    ]
                    while len(new_values) < len(all_column_keys):
                        new_values.append("")
                    try:
                        self.tree.insert(
                            "",
                            "end",
                            iid=preserved_item["id"],
                            values=tuple(new_values),
                            tags=preserved_item["tags"],
                        )
                    except tk.TclError as e:
                        print(f"Warn Insert:{e}")
                        self.tree.insert(
                            "",
                            "end",
                            values=tuple(new_values),
                            tags=preserved_item["tags"],
                        )
            elif not preserve_data:  # Clear if not preserving and tree not empty
                if self.tree.get_children():  # Only clear if necessary
                    print("DEBUG: Clearing existing tree items (not preserving).")
                    for item_id in self.tree.get_children():
                        self.tree.delete(item_id)

            self._configure_row_tags()
            print("DEBUG: Finished rebuilding main tree.")  # Debug Print

        except Exception as e:
            print(f"ERROR in _rebuild_main_tree: {e}")
            import traceback

            traceback.print_exc()
            messagebox.showerror(
                "خطای بازسازی جدول", f"خطا در هنگام بازسازی جدول اصلی:\n{e}"
            )

    # --- END OF REPLACEMENT for _rebuild_main_tree method ---
    # --- END OF REPLACEMENT for _rebuild_main_tree method ---

    def _configure_row_tags(self):
        """Sets up the background colors for row tags."""
        # تنظیم رنگ پس‌زمینه برای هر تگ
        self.tree.tag_configure("yellow", background="yellow")
        self.tree.tag_configure("lightgreen", background="lightgreen")
        self.tree.tag_configure("lightblue", background="lightblue")
        self.tree.tag_configure("white", background="white")

        # اجبار کردن تری‌ویو به رفرش کردن خودش
        self.tree.update()

    def _set_row_color(self, item_id, color_tag):
        """Applies a color tag to a specific TreeView row."""
        # اطمینان از وجود آیتم
        if not item_id:
            return

        # حذف تگ‌های رنگ قبلی
        current_tags = list(self.tree.item(item_id, "tags"))
        color_tags = ["yellow", "lightgreen", "lightblue", "white"]

        new_tags = [tag for tag in current_tags if tag not in color_tags]
        new_tags.append(color_tag)

        # اعمال تگ جدید
        self.tree.item(item_id, tags=tuple(new_tags))

        # بازخوانی تنظیمات تگ‌ها و اجبار به بروزرسانی
        self._configure_row_tags()
        self.tree.update_idletasks()
        self.has_unsaved_changes = True

    def _on_tree_right_click(self, event):
        """Handles right-clicks on the TreeView for coloring rows."""
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)  # انتخاب سطر کلیک شده

            context_menu = tk.Menu(self.root, tearoff=0)
            context_menu.add_command(
                label="رنگ زرد", command=lambda: self._set_row_color(row_id, "yellow")
            )
            context_menu.add_command(
                label="رنگ سبز",
                command=lambda: self._set_row_color(row_id, "lightgreen"),
            )
            context_menu.add_command(
                label="رنگ آبی",
                command=lambda: self._set_row_color(row_id, "lightblue"),
            )
            context_menu.add_command(
                label="رنگ سفید (پیش‌فرض)",
                command=lambda: self._set_row_color(row_id, "white"),
            )

            context_menu.tk_popup(event.x_root, event.y_root)

            # اضافه کردن این خط جدید برای اطمینان از اعمال تغییرات
            self.root.after(100, self._configure_row_tags)

    def _on_tree_hover(self, event):
        """Shows a tooltip for the 'tozihat' column on hover."""
        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)

        # Ensure tooltip exists only once
        if not self.tooltip_label:
            self.tooltip_label = tk.Toplevel(self.tree)
            self.tooltip_label.wm_overrideredirect(True)  # No window decorations
            self.tooltip_label.attributes("-topmost", True)
            self._tooltip_widget = tk.Label(
                self.tooltip_label,
                bg="#FFFFDD",
                relief="solid",
                borderwidth=1,
                justify="right",
                wraplength=300,
                font=("Tahoma", 10),
            )
            self._tooltip_widget.pack(ipadx=2, ipady=2)
            self.tooltip_label.withdraw()  # Start hidden

        if row_id and col_id:
            try:
                col_index = int(col_id.replace("#", "")) - 1
                # Use tree["columns"] which contains the *actual* column keys in order
                current_columns = self.tree["columns"]

                if 0 <= col_index < len(current_columns):
                    col_key = current_columns[col_index]

                    if col_key == "tozihat":  # Check against the internal key
                        values = self.tree.item(row_id, "values")
                        if col_index < len(values):
                            cell_text = values[col_index]
                            if cell_text and cell_text.strip():
                                bbox = self.tree.bbox(row_id, col_id)
                                if bbox:
                                    x, y, _, height = bbox
                                    # Position below the cell
                                    x_pos = self.tree.winfo_rootx() + x
                                    y_pos = self.tree.winfo_rooty() + y + height + 5

                                    self._tooltip_widget.config(text=cell_text)
                                    self.tooltip_label.geometry(f"+{x_pos}+{y_pos}")
                                    self.tooltip_label.deiconify()  # Show
                                    return  # Exit function, tooltip is shown
            except (ValueError, IndexError) as e:
                print(f"Tooltip error: {e}")  # Log error, but continue
                pass  # Ignore errors during hover/tooltip logic

        # If conditions not met or exited tooltip area, hide
        if self.tooltip_label and self.tooltip_label.winfo_viewable():
            self.tooltip_label.withdraw()

    def _on_tree_leave(self, event=None):
        """Hides the tooltip when the mouse leaves the TreeView."""
        if self.tooltip_label:
            self.tooltip_label.withdraw()

    # --- Core Functionality Methods ---

    # --- START OF REPLACEMENT for open_add_door_dialog method ---

    def open_add_door_dialog(self):
        """Opens a dialog window to add new door entries."""
        if not self.ensure_project_saved("افزودن درب جدید"):
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("افزودن درب جدید")
        dialog.geometry("400x280")
        dialog.transient(self.root)
        dialog.grab_set()

        # Use a frame for better layout within the dialog
        content_frame = tk.Frame(dialog)
        content_frame.pack(padx=10, pady=10, fill="both", expand=True)

        labels = ["مکان نصب", "عرض (cm)", "ارتفاع (cm)", "تعداد درب", "جهت درب"]
        entries = {}  # Use dict for easier access by label

        # Direction Variable
        direction_var = tk.StringVar(value="راست")

        for i, label_text in enumerate(labels):
            tk.Label(content_frame, text=label_text + ":").grid(
                row=i, column=0, padx=5, pady=5, sticky="e"
            )

            if label_text == "جهت درب":
                frame_direction = tk.Frame(content_frame)
                frame_direction.grid(
                    row=i, column=1, columnspan=2, padx=5, pady=5, sticky="w"
                )
                tk.Radiobutton(
                    frame_direction, text="راست", variable=direction_var, value="راست"
                ).pack(side="left")
                tk.Radiobutton(
                    frame_direction, text="چپ", variable=direction_var, value="چپ"
                ).pack(side="left")
            else:
                entry = tk.Entry(content_frame, width=25)
                entry.grid(row=i, column=1, padx=5, pady=5, sticky="ew")
                entries[label_text] = entry

        # Allow entry column to expand
        content_frame.columnconfigure(1, weight=1)

        # --- Space/Arrow Key Toggle ---
        def toggle_direction(event=None):
            direction_var.set("چپ" if direction_var.get() == "راست" else "راست")
            return "break"

        dialog.bind("<space>", toggle_direction)
        dialog.bind("<Left>", toggle_direction)
        dialog.bind("<Right>", toggle_direction)

        # --- Local Functions ---
        def add_and_clear():
            try:
                new_entry_values = [
                    entries["مکان نصب"].get().strip(),
                    entries["عرض (cm)"].get().strip(),
                    entries["ارتفاع (cm)"].get().strip(),
                    entries["تعداد درب"].get().strip(),
                    direction_var.get(),
                ]
                # Map these values to the first 5 base internal keys
                # ["makan", "arz", "ertefa", "tedad", "jeht"]
                keys_for_input = BASE_COLUMN_KEYS[:5]
                new_entry_dict = dict(zip(keys_for_input, new_entry_values))

            except KeyError as e:
                messagebox.showerror("خطا", "...", parent=dialog)
                return

            if not all(new_entry_values[:4]):
                messagebox.showwarning("...", "...", parent=dialog)
                return
            try:
                float(new_entry_values[1])
                float(new_entry_values[2])
                int(new_entry_values[3])
            except ValueError:
                messagebox.showwarning("...", "...", parent=dialog)
                return

            # Append the dictionary to the buffer
            self.door_entries_buffer.append(new_entry_dict)

            for entry_widget in entries.values():
                entry_widget.delete(0, tk.END)
            direction_var.set("راست")
            entries["مکان نصب"].focus_set()

        # *** MODIFIED finish_adding function ***
        def finish_adding():
            """Adds buffered entries to TreeView using correct column order and closes."""
            inserted_count = 0
            if self.door_entries_buffer:
                try:
                    # Get the CURRENT order of column keys from the TreeView
                    current_tree_keys = list(self.tree["columns"])
                    num_total_cols = len(current_tree_keys)

                    for door_data_dict in self.door_entries_buffer:
                        # Build the values tuple in the order required by the TreeView
                        values_tuple = []
                        for key in current_tree_keys:
                            # Get the value from the input dict if key matches, else empty string
                            values_tuple.append(door_data_dict.get(key, ""))

                        # Ensure tuple has correct length (should be guaranteed by above loop)
                        if len(values_tuple) != num_total_cols:
                            print(
                                f"Warning: Value tuple length mismatch for insert. Expected {num_total_cols}, got {len(values_tuple)}"
                            )
                            # Pad just in case, though it shouldn't be needed
                            values_tuple.extend(
                                [""] * (num_total_cols - len(values_tuple))
                            )

                        # Insert the correctly ordered tuple
                        self.tree.insert(
                            "",
                            "end",
                            values=tuple(values_tuple),
                            tags=(DEFAULT_ROW_TAG,),
                        )
                        inserted_count += 1

                except Exception as e:
                    # Catch potential errors during insertion (e.g., if tree columns changed unexpectedly)
                    print(f"Error during TreeView insert: {e}")
                    messagebox.showerror(
                        "خطای درج",
                        f"خطا در هنگام افزودن داده به جدول:\n{e}",
                        parent=dialog,
                    )
                    # Decide if you want to clear buffer even on error
                    # self.door_entries_buffer.clear()
                    # dialog.destroy()
                    return  # Stop processing further if error occurs

                # Show success message only if insertions happened
                if inserted_count > 0:
                    messagebox.showinfo(
                        "ثبت شد", f"{inserted_count} درب جدید اضافه شد.", parent=dialog
                    )

                self.door_entries_buffer.clear()  # Clear buffer after successful processing

            dialog.unbind("<space>")
            dialog.unbind("<Left>")
            dialog.unbind("<Right>")
            dialog.unbind("<Return>")
            dialog.unbind("<Escape>")
            self.has_unsaved_changes = True
            dialog.destroy()

        # *** END of MODIFIED finish_adding ***

        # --- Dialog Buttons ---
        btn_frame = tk.Frame(dialog)  # Place buttons outside content_frame
        btn_frame.pack(pady=(0, 10))  # Add padding below buttons

        btn_add_more = tk.Button(
            btn_frame,
            text="ثبت و بعدی (Enter)",
            command=add_and_clear,
            bg="green",
            fg="white",
        )
        btn_add_more.pack(side=tk.LEFT, padx=10)
        btn_finish = tk.Button(
            btn_frame,
            text="اتمام و بستن (Esc)",
            command=finish_adding,
            bg="blue",
            fg="white",
        )
        btn_finish.pack(side=tk.LEFT, padx=10)

        # Bind Enter/Escape
        dialog.bind("<Return>", lambda event: add_and_clear())
        dialog.bind("<Escape>", lambda event: finish_adding())

        entries["مکان نصب"].focus_set()
        self.root.wait_window(dialog)

    # --- END OF REPLACEMENT for open_add_door_dialog method ---

    # ... (درون کلاس CuttingApp) ...

    # --- START OF REPLACEMENT for open_batch_edit_dialog method ---

    # --- START OF FINAL REPLACEMENT for open_batch_edit_dialog method ---

    # _can_hide_column stays the same
    # --- START OF FINAL REPLACEMENT for open_batch_edit_dialog method ---
    # (Includes ALL fixes: combo options, scroll, apply, dynamic update, no critical cols, tozihat last)

    # _can_hide_column stays the same

    def _can_hide_column(self, column_key):
        if not column_key or column_key not in self.tree["columns"]:
            return True
        try:
            col_index = list(self.tree["columns"]).index(column_key)
        except ValueError:
            return True
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            if col_index < len(values) and str(values[col_index]).strip():
                return False
        return True

    def open_batch_edit_dialog(self):
        # print("DEBUG: Entering open_batch_edit_dialog") # Optional Debug
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("انتخاب نشده", "لطفاً حداقل یک سطر را انتخاب کنید.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("ویرایش گروهی")
        dialog.geometry("550x550")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(True, True)

        # --- Prepare Data & Mappings ---
        try:
            active_custom_cols_data = get_active_custom_columns_data()
            self.display_to_key_map = {text: key for key, text in BASE_COLUMNS_DATA}
            for col_data in active_custom_cols_data:
                self.display_to_key_map[col_data["display"]] = col_data["key"]

            CRITICAL_BASE_KEYS = ["makan", "arz", "ertefa", "tedad", "jeht"]
            critical_display_names = {
                text for key, text in BASE_COLUMNS_DATA if key in CRITICAL_BASE_KEYS
            }

            # --- Get display names of NON-CRITICAL base columns ---
            editable_base_labels = []
            for key, text in BASE_COLUMNS_DATA:
                if key not in CRITICAL_BASE_KEYS:
                    editable_base_labels.append(text)

            # --- Get display names of ONLY NON-CRITICAL custom columns ---
            editable_custom_display_names = []
            for col_data in active_custom_cols_data:
                # Check if the custom column's key is NOT a critical base key
                if col_data["key"] not in CRITICAL_BASE_KEYS:
                    editable_custom_display_names.append(col_data["display"])

            # --- Create final ordered list with 'tozihat' last ---
            last_label_text = "توضیحات"
            # Combine EDITABLE base labels and EDITABLE custom names
            combined_labels = list(
                set(editable_base_labels + editable_custom_display_names)
            )
            tozihat_present = False
            if last_label_text in combined_labels:
                # Ensure tozihat is not critical
                if (
                    self.display_to_key_map.get(last_label_text)
                    not in CRITICAL_BASE_KEYS
                ):
                    combined_labels.remove(last_label_text)
                    tozihat_present = True
                else:
                    tozihat_present = False  # Should not happen

            sorted_labels_without_last = sorted(combined_labels)
            final_ordered_labels = sorted_labels_without_last
            if tozihat_present:
                final_ordered_labels.append(last_label_text)

            # Get hidden columns from database
            try:
                conn = sqlite3.connect('cutting.db')
                cursor = conn.cursor()
                cursor.execute('SELECT display_name FROM hidden_columns WHERE is_hidden = 1')
                hidden_columns = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                # Add hidden columns to final_ordered_labels if they're not already there
                for col in hidden_columns:
                    if col not in final_ordered_labels:
                        final_ordered_labels.append(col)
            except Exception as e:
                print(f"Error loading hidden columns: {e}")

            if not final_ordered_labels:
                print("ERROR: No editable labels found!")
                messagebox.showerror("خطا", "...", parent=dialog)
                dialog.destroy()
                return

        except Exception as e:
            print(f"ERROR preparing data: {e}")
            import traceback

            traceback.print_exc()
            messagebox.showerror("...", f"خطا:\n{e}", parent=dialog)
            dialog.destroy()
            return

        # --- UI Structure & Variables ---
        check_vars = {}
        widgets = {}
        first_item_values = self.tree.item(selected_items[0], "values")
        all_tree_columns_keys = list(self.tree["columns"])
        frame_scroll_area = tk.Frame(dialog)
        frame_scroll_area.pack(padx=10, pady=(10, 5), fill="both", expand=True)
        canvas = tk.Canvas(frame_scroll_area, borderwidth=0)
        scrollbar = ttk.Scrollbar(
            frame_scroll_area, orient="vertical", command=canvas.yview
        )
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # --- Internal Functions ---
        def _update_tree_display():
            fixed_columns_keys = ["makan", "arz", "ertefa", "tedad", "jeht"]
            dynamic_columns_keys = []
            last_column_key = "tozihat"
            tozihat_is_checked = False
            for display_name in final_ordered_labels:
                if check_vars.get(display_name) and check_vars[display_name].get():
                    key = self.display_to_key_map.get(display_name)
                    if key:
                        if key == last_column_key:
                            tozihat_is_checked = True
                        elif key not in fixed_columns_keys:
                            dynamic_columns_keys.append(key)
            visible_columns_keys_before_last = fixed_columns_keys + dynamic_columns_keys
            current_tree_cols_keys = list(self.tree["columns"])
            final_display_cols_keys = [
                key
                for key in visible_columns_keys_before_last
                if key in current_tree_cols_keys
            ]
            if tozihat_is_checked and last_column_key in current_tree_cols_keys:
                if last_column_key not in final_display_cols_keys:
                    final_display_cols_keys.append(last_column_key)
                elif final_display_cols_keys[-1] != last_column_key:
                    final_display_cols_keys.remove(last_column_key)
                    final_display_cols_keys.append(last_column_key)
            try:
                if not final_display_cols_keys:
                    final_display_cols_keys = [
                        k for k in fixed_columns_keys if k in current_tree_cols_keys
                    ]
                self.tree["displaycolumns"] = tuple(final_display_cols_keys)
            except tk.TclError as e:
                print(f"Error: {e}")
                messagebox.showerror("...", parent=dialog)

        def toggle_widget_state(display_name):
            widget = widgets.get(display_name)
            if widget:
                widget.config(
                    state="normal" if check_vars[display_name].get() else "disabled"
                )

        def _handle_checkbox_change(display_name):
            var = check_vars.get(display_name)
            if not var:
                return
            is_checked_after_click = var.get()
            column_key = self.display_to_key_map.get(display_name)
            if not is_checked_after_click and column_key:
                if not self._can_hide_column(column_key):
                    messagebox.showerror(
                        "امکان مخفی کردن نیست",
                        f"ستون '{display_name}' دارای مقدار است.",
                        parent=dialog,
                    )
                    var.set(True)
                    toggle_widget_state(display_name)
                    return
                
                # Save hidden state to database
                try:
                    conn = sqlite3.connect('cutting.db')
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO hidden_columns (column_key, display_name, is_hidden, last_updated)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (column_key, display_name, 1))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"Error saving hidden column state: {e}")
            elif is_checked_after_click and column_key:
                # Remove from hidden columns if it was hidden
                try:
                    conn = sqlite3.connect('cutting.db')
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM hidden_columns WHERE column_key = ?', (column_key,))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"Error removing hidden column state: {e}")
                    
            toggle_widget_state(display_name)
            _update_tree_display()

        # --- Create Widgets ---
        corrected_combo_options = {
            "رنگ پروفیل": ["سفید", "آنادایز"],
            "نوع پروفیل": [
                "فریم لس آلومینیومی",
                "فریم قدیمی",
                "فریم داخل چوب دار",
                "داخل چوب دار دو آلومینیوم درب",
            ],
            "وضعیت تولید درب": [
                "همزمان با تولید چهارچوب",
                "تولید درب در آینده",
                "بدون درب",
            ],
            "لولا": ["OTLAV", "HTH", "NHN", "متفرقه"],
            "قفل": ["STV", "ایزدو", "NHN", "HTN"],
            "اکسسوری": [
                "آلومینیوم آستانه فاق و زبانه",
                "آرامبند مرونی",
                "قفل برق سارو با فنر",
                "آرامبند NHN",
            ],
            "کلاف": ["دو طرفه", "سه طرفه"],
            "دستگیره": ["دو تیکه", "ایزدو", "گریف ورک", "متفرقه"],
        }

        # Use the correctly filtered and ordered list
        print(f"DEBUG - FINAL LABELS TO CREATE WIDGETS FOR: {final_ordered_labels}")
        for i, display_name in enumerate(final_ordered_labels):
            row_frame = tk.Frame(scrollable_frame)
            row_frame.pack(fill="x", pady=2, padx=5)
            
            # Check if column is hidden in database
            is_hidden = False
            try:
                conn = sqlite3.connect('cutting.db')
                cursor = conn.cursor()
                cursor.execute('SELECT is_hidden FROM hidden_columns WHERE display_name = ?', (display_name,))
                result = cursor.fetchone()
                if result:
                    is_hidden = bool(result[0])
                conn.close()
            except Exception as e:
                print(f"Error checking hidden status: {e}")
            
            is_checked = display_name in self.previous_checked_labels_batch_edit and not is_hidden
            var = tk.BooleanVar(value=is_checked)
            check_vars[display_name] = var
            cb = tk.Checkbutton(
                row_frame,
                variable=var,
                command=lambda dn=display_name: _handle_checkbox_change(dn),
            )
            cb.pack(side=tk.LEFT, padx=(0, 5))
            tk.Label(row_frame, text=display_name + ":").pack(side=tk.LEFT, padx=5)

            widget = None
            initial_value = ""
            options = []
            col_id = None
            col_index = -1
            col_key = self.display_to_key_map.get(display_name)
            if col_key:
                col_id = get_column_id_by_key(col_key)
                if col_id is not None:
                    options = get_custom_column_options(col_id)
                if col_key in all_tree_columns_keys:
                    try:
                        col_index = all_tree_columns_keys.index(col_key)
                    except ValueError:
                        pass
                    if col_index != -1 and col_index < len(first_item_values):
                        initial_value = first_item_values[col_index]

            if options:
                widget = ttk.Combobox(
                    row_frame, values=options, width=30, state="readonly"
                )
            else:
                width = 50 if display_name == last_label_text else 33
                widget = tk.Entry(row_frame, width=width)
            widget.pack(side=tk.LEFT, fill="x", expand=True, padx=5)
            widget.insert(0, initial_value)
            widget.config(state="normal" if is_checked else "disabled")
            widgets[display_name] = widget

        # --- Select/Deselect All ---
        select_all_var = tk.BooleanVar(
            value=all(
                check_vars[lbl].get()
                for lbl in final_ordered_labels
                if lbl in check_vars
            )
        )

        def toggle_all_checkboxes():
            new_state = select_all_var.get()
            if not new_state:
                columns_with_data = [
                    dn
                    for dn in final_ordered_labels
                    if dn in check_vars
                    and not self._can_hide_column(self.display_to_key_map.get(dn))
                ]
                if columns_with_data:
                    messagebox.showerror(
                        "امکان مخفی کردن نیست",
                        "...\n" + "\n".join(columns_with_data),
                        parent=dialog,
                    )
                    select_all_var.set(True)
                    return
            for display_name in final_ordered_labels:
                if display_name in check_vars:
                    check_vars[display_name].set(new_state)
                    toggle_widget_state(display_name)
            _update_tree_display()

        cb_all = tk.Checkbutton(
            dialog,
            text="فعال/غیرفعال کردن همه موارد",
            variable=select_all_var,
            command=toggle_all_checkboxes,
            anchor="w",
            bg="lightgrey",
        )
        cb_all.pack(fill="x", padx=10, pady=(5, 0))

        # --- Apply Button ---
        def apply_common():
            self.previous_checked_labels_batch_edit.clear()
            updated_count = 0
            current_tree_cols_keys = list(self.tree["columns"])
            for item_id in selected_items:
                try:
                    current_values = list(self.tree.item(item_id, "values"))
                    while len(current_values) < len(current_tree_cols_keys):
                        current_values.append("")
                    made_change_for_item = False
                    for display_name in final_ordered_labels:
                        if (
                            display_name in check_vars
                            and check_vars[display_name].get()
                        ):
                            self.previous_checked_labels_batch_edit.add(display_name)
                            new_value = widgets[display_name].get().strip()
                            col_key = self.display_to_key_map.get(display_name)
                            if col_key and col_key in current_tree_cols_keys:
                                try:
                                    col_index = current_tree_cols_keys.index(col_key)
                                    if col_index < len(current_values):
                                        if current_values[col_index] != new_value:
                                            current_values[col_index] = new_value
                                            made_change_for_item = True
                                except ValueError:
                                    print(f"Error: Key '{col_key}' not found.")
                                    continue
                    if made_change_for_item:
                        self.tree.item(item_id, values=tuple(current_values))
                        updated_count += 1
                except Exception as e:
                    print(f"Error item {item_id}: {e}")
                    messagebox.showerror("...", parent=dialog)
            if updated_count > 0:
                messagebox.showinfo(
                    "اعمال شد",
                    f"تغییرات روی {updated_count} سطر اعمال شد.",
                    parent=dialog,
                )
            else:
                messagebox.showinfo("بدون تغییر", "تغییری اعمال نشد.", parent=dialog)
            dialog.destroy()

        btn_apply = tk.Button(
            dialog, text="اعمال تغییرات", command=apply_common, bg="green", fg="white"
        )
        btn_apply.pack(pady=(5, 10))

        # --- Initial Setup ---
        _update_tree_display()  # Update TreeView display based on initial checks
        # Focus first editable widget
        for dn in final_ordered_labels:
            if check_vars.get(dn) and check_vars[dn].get():
                widgets[dn].focus_set()
                break
        dialog.wait_window(dialog)
        if hasattr(self, "display_to_key_map"):
            del self.display_to_key_map

    # --- END OF FINAL REPLACEMENT for open_batch_edit_dialog method ---

    # --- END OF REPLACEMENT for open_batch_edit_dialog ---

    # ... (rest of the CuttingApp class) ...

    def _get_custom_column_options(self, column_name):
        """Fetches dropdown options for a specific custom column."""
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT o.option_value
                FROM custom_column_options o
                JOIN custom_columns c ON o.column_id = c.id
                WHERE c.column_name = ? AND c.is_active = 1
                ORDER BY o.id
            """,
                (column_name,),
            )
            options = [row[0] for row in cursor.fetchall()]
            conn.close()
            return options
        except Exception as e:
            print(f"Error fetching options for column '{column_name}': {e}")
            return []

    def calculate_cutting_from_orders(self):
        """Calculates optimized cutting list based on TreeView data."""
        stock_length = STOCK_LENGTH  # Use constant
        required_pieces = []  # List of tuples: (length, count)

        # --- Gather required pieces from TreeView ---
        valid_rows = 0
        for item_id in self.tree.get_children():
            try:
                values = self.tree.item(item_id, "values")
                # Find indices for width, height, count robustly
                all_keys = list(self.tree["columns"])
                width_idx = all_keys.index("arz")
                height_idx = all_keys.index("ertefa")
                count_idx = all_keys.index("tedad")

                width = float(values[width_idx])
                height = float(values[height_idx])
                count = int(values[count_idx])

                if width <= 0 or height <= 0 or count <= 0:
                    continue  # Skip rows with invalid dimensions/count

                # Standard door profile calculation (adjust if logic differs)
                # Two vertical pieces per door
                required_pieces.append((height, count * 2))
                # One horizontal piece per door
                required_pieces.append((width, count * 1))

                valid_rows += 1

            except (ValueError, IndexError, TypeError) as e:
                print(
                    f"Skipping row {item_id} due to invalid data: {e} - Values: {values}"
                )
                continue  # Skip rows with non-numeric or missing data

        if not required_pieces:
            messagebox.showwarning(
                "بدون داده معتبر",
                "هیچ درب معتبری (با عرض، ارتفاع و تعداد عددی مثبت) در جدول برای محاسبه برش یافت نشد.",
            )
            return
        if valid_rows < len(self.tree.get_children()):
            messagebox.showinfo(
                "داده نامعتبر",
                "برخی ردیف‌ها به دلیل داشتن مقادیر نامعتبر (غیرعددی یا صفر) در عرض، ارتفاع یا تعداد، در محاسبه نادیده گرفته شدند.",
                icon="warning",
            )

        # --- Bin Packing Algorithm (First Fit Decreasing Heuristic) ---
        bins = []  # Each bin is a dict: {"pieces": [], "remaining": float}
        # Flatten the list: [(length1, 1), (length1, 1), ..., (length2, 1), ...]
        flat_pieces = []
        for length, count in required_pieces:
            flat_pieces.extend([length] * count)

        # Sort pieces by length, descending
        sorted_pieces = sorted(flat_pieces, reverse=True)

        for piece_length in sorted_pieces:
            if piece_length > stock_length:
                messagebox.showerror(
                    "خطا در محاسبه",
                    f"امکان برش قطعه‌ای به طول {piece_length}cm از شاخه {stock_length}cm وجود ندارد!",
                )
                return

            placed = False
            # Try to place in existing bins
            for bin_data in bins:
                if bin_data["remaining"] >= piece_length:
                    bin_data["pieces"].append(piece_length)
                    bin_data["remaining"] -= piece_length
                    placed = True
                    break
            # If not placed, create a new bin
            if not placed:
                bins.append(
                    {"pieces": [piece_length], "remaining": stock_length - piece_length}
                )

        # --- Calculate Statistics ---
        total_bins_used = len(bins)
        WASTE_THRESHOLD = 70  # Define threshold for "small" waste pieces
        small_pieces_info = [
            (i + 1, bin_data["remaining"])
            for i, bin_data in enumerate(bins)
            if 0 < bin_data["remaining"] < WASTE_THRESHOLD
        ]
        small_pieces_count = len(small_pieces_info)
        total_small_waste_length = sum(rem for _, rem in small_pieces_info)
        total_small_waste_weight = (
            total_small_waste_length / 100
        ) * WEIGHT_PER_METER  # Convert cm to m

        # --- Format Result Text ---
        result_lines = [
            f"تعداد کل شاخه‌های مورد نیاز ({stock_length}cm): {total_bins_used} عدد",
            f"تعداد تکه‌های باقی‌مانده کوچک‌تر از {WASTE_THRESHOLD}cm: {small_pieces_count} عدد",
            f"طول کل ضایعات کوچک‌تر از {WASTE_THRESHOLD}cm: {total_small_waste_length:.1f} cm",
            f"وزن تقریبی ضایعات کوچک‌تر از {WASTE_THRESHOLD}cm: {total_small_waste_weight:.2f} کیلوگرم",
            "\n" + "=" * 30 + "\n",
            "جزئیات برش هر شاخه:",
            "=" * 30 + "\n",
        ]

        for i, bin_data in enumerate(bins, start=1):
            pieces_str = " | ".join(map(str, bin_data["pieces"]))
            remaining_str = f"{bin_data['remaining']:.1f} cm"
            result_lines.append(f"شاخه {i}:")
            result_lines.append(f"  برش‌ها: [ {pieces_str} ]")
            result_lines.append(f"  باقی‌مانده: {remaining_str}")
            if 0 < bin_data["remaining"] < WASTE_THRESHOLD:
                result_lines[-1] += "  (ضایعات کوچک)"  # Mark small waste
            result_lines.append("-" * 25)

        result_text = "\n".join(result_lines)

        # --- Display Results ---
        # Show in the dedicated frame below tree
        self._show_result_frame(result_text)
        self._show_result_popup(result_text)  # Also show in a popup

    def _show_result_frame(self, result_text):
        """Displays the cutting result text in the frame below the TreeView."""
        self.result_display.config(state="normal")  # Enable editing
        self.result_display.delete("1.0", tk.END)
        self.result_display.insert(tk.END, result_text)
        self.result_display.config(state="disabled")  # Make read-only

        # Make the frame visible and adjust layout weights
        self.frame_result.grid(
            row=2, column=0, columnspan=2, sticky="nsew", padx=0, pady=(5, 0)
        )
        self.frame_tree_area.rowconfigure(0, weight=3)  # Reduce TreeView weight
        self.frame_tree_area.rowconfigure(2, weight=1)  # Give weight to result frame
        self.output_visible = True
        # Consider updating a toggle button's text if you re-add one

    def _hide_result_frame(self):
        """Hides the cutting result frame and readjusts layout."""
        self.frame_result.grid_remove()
        self.frame_tree_area.rowconfigure(0, weight=1)  # Restore TreeView weight
        self.frame_tree_area.rowconfigure(2, weight=0)  # Remove result frame weight
        self.output_visible = False
        # Consider updating a toggle button's text

    def _show_result_popup(self, result_text):
        """Displays the cutting result text in a separate popup window."""
        popup = tk.Toplevel(self.root)
        popup.title("📏 نتیجه بهینه‌سازی برش")
        popup.geometry("600x450")
        popup.transient(self.root)
        popup.grab_set()

        text_popup = tk.Text(popup, wrap="word", relief="flat")
        text_popup.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        text_popup.insert(tk.END, result_text)
        text_popup.config(state="disabled")  # Read-only

        # Add a scrollbar to the popup text
        scrollbar = tk.Scrollbar(text_popup, command=text_popup.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_popup["yscrollcommand"] = scrollbar.set

        btn_frame = tk.Frame(popup)
        btn_frame.pack(pady=10)
        btn_ok = tk.Button(btn_frame, text="بستن", width=10, command=popup.destroy)
        btn_ok.pack(side=tk.LEFT, padx=5)
        # Optional: Add a "Copy to Clipboard" button here

        popup.wait_window(popup)

    # --- Export Methods ---

    def export_to_excel(self):
        """Exports the current TreeView data to an Excel file."""
        if not self.ensure_project_saved("خروجی گرفتن Excel"):
            return
        items = self.tree.get_children()
        if not items:
            messagebox.showwarning(
                "بدون داده", "جدول خالی است. داده‌ای برای خروجی Excel وجود ندارد."
            )
            return

        try:
            # Use displaycolumns to get visible columns in their current order
            visible_cols_keys = self.tree["displaycolumns"]
            # Check if empty or default
            if not visible_cols_keys or visible_cols_keys == ("",):
                # Fallback to all columns
                visible_cols_keys = self.tree["columns"]

            # Get headers based on displaycolumns
            headers = [self.tree.heading(key)["text"] for key in visible_cols_keys]
            # Get indices based on the *full* column list
            all_col_keys = list(self.tree["columns"])
            col_indices = [
                all_col_keys.index(key)
                for key in visible_cols_keys
                if key in all_col_keys
            ]

            data = []
            for item_id in items:
                values = list(self.tree.item(item_id, "values"))
                # Extract only the values for visible columns using indices
                row_data = [
                    str(values[i]) if i < len(values) and values[i] is not None else ""
                    for i in col_indices
                ]
                data.append(row_data)

            df = pd.DataFrame(data, columns=headers)  # Use visible headers

            # Generate filename (consider adding customer name/order ID if available)
            excel_file = os.path.join(PROJECTS_DIR, "exported_data.xlsx")
            df.to_excel(excel_file, index=False, engine="openpyxl")  # Specify engine

            if messagebox.askyesno(
                "باز کردن فایل",
                f"فایل Excel با موفقیت ذخیره شد:\n{excel_file}\n\nآیا مایلید فایل باز شود؟",
            ):
                open_file_externally(excel_file)

        except Exception as e:
            messagebox.showerror(
                "خطا در خروجی Excel", f"مشکلی در ایجاد یا ذخیره فایل Excel رخ داد:\n{e}"
            )

    # تغییرات در تابع export_table_to_pdf برای استفاده از تاریخ شمسی در PDF

    def export_table_to_pdf(self):
        """Exports the TreeView data directly to a PDF file using FPDF."""
        if not self.ensure_project_saved("خروجی گرفتن PDF"):
            return
        items = self.tree.get_children()
        if not items:
            messagebox.showerror("خطا", "هیچ داده‌ای برای خروجی PDF وجود ندارد.")
            return

        # --- Determine Visible Columns and Headers (excluding 'توضیحات' for main table) ---
        visible_cols_keys = self.tree["displaycolumns"]
        if not visible_cols_keys or visible_cols_keys == ("",):
            visible_cols_keys = list(self.tree["columns"])
        else:
            visible_cols_keys = list(visible_cols_keys)  # Ensure it's a list

        all_col_keys = list(self.tree["columns"])  # Full list of keys

        # Filter out 'tozihat' key and get corresponding headers and indices
        headers = []
        col_indices_for_data = []
        tozihat_key = "tozihat"
        tozihat_idx_in_all = -1
        if tozihat_key in all_col_keys:
            tozihat_idx_in_all = all_col_keys.index(tozihat_key)

        for key in visible_cols_keys:
            if key == tozihat_key:
                continue  # Skip tozihat for main table columns
            if key in all_col_keys:
                headers.append(self.tree.heading(key)["text"])
                col_indices_for_data.append(all_col_keys.index(key))

        if not headers:
            messagebox.showerror(
                "خطا",
                "هیچ ستون معتبری (به جز توضیحات) برای نمایش در PDF انتخاب نشده است!",
            )
            return

        # --- Prepare Data for PDF ---
        pdf_data = []  # Data for main table cells
        all_row_values_with_tags = []  # Store all values for tozihat later
        for item_id in items:
            row_values = self.tree.item(item_id, "values")
            row_tags = self.tree.item(item_id, "tags")
            all_row_values_with_tags.append((row_values, row_tags))  # Keep full data

            # Extract data for visible columns (excluding tozihat)
            filtered_row = [
                (
                    str(row_values[i])
                    if i < len(row_values) and row_values[i] is not None
                    else ""
                )
                for i in col_indices_for_data
            ]
            pdf_data.append(filtered_row)

        # --- Initialize PDF (Landscape A4) ---
        try:
            pdf = FPDF("L", "mm", "A4")
            pdf.add_page()
            # Ensure Vazir font file is present
            font_path = "Vazir.ttf"
            if not os.path.exists(font_path):
                messagebox.showerror(
                    "خطای فونت",
                    f"فایل فونت Vazir.ttf در مسیر برنامه یافت نشد.\nبرای نمایش صحیح فارسی، این فایل لازم است.",
                )
                return
            pdf.add_font("Vazir", "", font_path, uni=True)
            pdf.set_font("Vazir", "", 10)  # Slightly smaller font size

            # --- Title ---
            title_txt = fix_persian_text("لیست سفارشات درب")
            pdf.cell(0, 10, txt=title_txt, border=0, ln=1, align="C")

            # --- اضافه کردن اطلاعات مشتری ---
            # ایجاد یک جدول برای اطلاعات مشتری
            pdf.set_font("Vazir", "", 9)
            pdf.ln(2)  # کمی فاصله

            # دریافت مقادیر از برچسب‌ها
            customer_name = (
                self.label_customer_name.cget("text")
                if hasattr(self, "label_customer_name")
                else ""
            )
            customer_id = (
                self.label_customer_id.cget("text")
                if hasattr(self, "label_customer_id")
                else ""
            )
            order_id = (
                self.label_order_id.cget("text")
                if hasattr(self, "label_order_id")
                else ""
            )
            project_name = (
                self.label_project_name.cget("text")
                if hasattr(self, "label_project_name")
                else ""
            )
            # استفاده از تاریخ شمسی از برچسب
            date = self.label_date.cget("text") if hasattr(self, "label_date") else ""

            # ایجاد جدول اطلاعات مشتری با رنگ پس‌زمینه
            info_cell_width = 45  # عرض هر سلول
            info_cell_height = 7  # ارتفاع هر سلول

            # تنظیم رنگ پس‌زمینه آبی روشن برای جدول اطلاعات مشتری
            pdf.set_fill_color(240, 248, 255)  # #f0f8ff

            # ردیف اول
            start_x = pdf.get_x()

            # نام مشتری
            pdf.set_font("Vazir", "", 8)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(25, info_cell_height, fix_persian_text("نام مشتری:"), 1, 0, "R", 1)
            pdf.set_font("Vazir", "", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(
                info_cell_width,
                info_cell_height,
                fix_persian_text(customer_name),
                1,
                0,
                "R",
                1,
            )

            # شماره محک
            pdf.set_font("Vazir", "", 8)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(25, info_cell_height, fix_persian_text("شماره محک:"), 1, 0, "R", 1)
            pdf.set_font("Vazir", "", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(
                info_cell_width,
                info_cell_height,
                fix_persian_text(customer_id),
                1,
                0,
                "R",
                1,
            )

            # نام پروژه
            pdf.set_font("Vazir", "", 8)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(25, info_cell_height, fix_persian_text("نام پروژه:"), 1, 0, "R", 1)
            pdf.set_font("Vazir", "", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(
                info_cell_width,
                info_cell_height,
                fix_persian_text(project_name),
                1,
                1,
                "R",
                1,
            )

            # ردیف دوم
            # شماره سفارش
            pdf.set_font("Vazir", "", 8)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(
                25, info_cell_height, fix_persian_text("شماره سفارش:"), 1, 0, "R", 1
            )
            pdf.set_font("Vazir", "", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(
                info_cell_width,
                info_cell_height,
                fix_persian_text(order_id),
                1,
                0,
                "R",
                1,
            )

            # تاریخ
            pdf.set_font("Vazir", "", 8)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(25, info_cell_height, fix_persian_text("تاریخ:"), 1, 0, "R", 1)
            pdf.set_font("Vazir", "", 10)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(
                info_cell_width, info_cell_height, fix_persian_text(date), 1, 0, "R", 1
            )

            # فضای خالی برای تکمیل ردیف
            remaining_width = pdf.w - pdf.get_x() - pdf.r_margin
            pdf.cell(remaining_width, info_cell_height, "", 1, 1, "C", 1)

            pdf.ln(5)  # فاصله بین اطلاعات مشتری و جدول اصلی
            pdf.set_font("Vazir", "", 10)  # بازگشت به فونت اصلی
            pdf.set_text_color(0, 0, 0)  # بازگشت به رنگ متن اصلی

            # ادامه کد قبلی...

            # (بقیه کد تابع export_table_to_pdf بدون تغییر می‌ماند)

            # --- Draw Header ---
            # (کد مربوط به جدول اصلی ادامه می‌یابد)

            # --- Calculate Column Widths ---
            page_width = pdf.w - 2 * pdf.l_margin  # Usable width
            # Estimate widths based on header/content, give more space if possible
            col_widths = []
            MIN_COL_WIDTH = 15
            # Try to distribute width, maybe give fixed size to some columns like count, width, height
            # Simple initial distribution:
            num_cols = len(headers)
            base_width = page_width / num_cols if num_cols > 0 else page_width
            for i, header in enumerate(headers):
                # Simple estimation: max length * factor, with min width
                header_len = len(fix_persian_text(header))
                max_content_len = header_len
                for row in pdf_data:
                    max_content_len = max(
                        max_content_len, len(fix_persian_text(str(row[i])))
                    )

                # Width estimation (needs tuning)
                # Adjust factor as needed
                estimated_width = max(MIN_COL_WIDTH, max_content_len * 1.8)
                col_widths.append(estimated_width)

            # Scale widths if they exceed page width
            total_width = sum(col_widths)
            if total_width > page_width:
                scale_factor = page_width / total_width
                col_widths = [w * scale_factor for w in col_widths]
            elif total_width < page_width - 10:  # If there's extra space, distribute it
                extra_space_per_col = (page_width - total_width) / num_cols
                col_widths = [w + extra_space_per_col for w in col_widths]

            # --- Draw Header ---
            pdf.set_fill_color(200, 220, 255)  # Light blue fill
            pdf.set_font("Vazir", "", 10)  # Font for header
            header_height = 7  # Cell height for header
            for i, header_txt in enumerate(headers):
                pdf.cell(
                    col_widths[i],
                    header_height,
                    fix_persian_text(header_txt),
                    border=1,
                    align="C",
                    fill=True,
                )
            pdf.ln(header_height)

            # --- Draw Table Data ---
            pdf.set_font("Vazir", "", 9)  # Font for data rows
            row_height = 6  # Base height for a row line
            zebra_color_1 = (255, 255, 255)  # White
            zebra_color_2 = (240, 240, 240)  # Light Gray

            # --- محاسبه ارتفاع ردیف بر اساس محتوا (باید قبل از تعیین رنگ باشد)---
            for row_idx, item_id in enumerate(items):
                wrapped_cells = []
                max_lines = 1
                try:
                    values = self.tree.item(item_id, "values")
                    # Find indices for displayed columns
                    current_values = []
                    for i in col_indices_for_data:
                        if i < len(values):
                            current_values.append(values[i])
                        else:
                            current_values.append("")

                    for i, cell_text in enumerate(current_values):
                        # Estimate characters per line based on width (adjust factor)
                        # Factor needs tuning
                        chars_per_line = max(5, int(col_widths[i] / 1.8))
                        lines = textwrap.wrap(
                            fix_persian_text(str(cell_text)),
                            width=chars_per_line,
                            replace_whitespace=False,
                            drop_whitespace=False,
                        )
                        if not lines:
                            # Ensure at least one line for empty cells
                            lines = [" "]
                        wrapped_cells.append(lines)
                        max_lines = max(max_lines, len(lines))

                    current_row_height = max_lines * row_height

                    # Check page break *before* drawing the multi-line cell
                    if pdf.get_y() + current_row_height > pdf.page_break_trigger:
                        pdf.add_page(orientation="L")
                        # Redraw header on new page
                        pdf.set_fill_color(200, 220, 255)
                        pdf.set_font("Vazir", "", 10)
                        for i, header_txt in enumerate(headers):
                            pdf.cell(
                                col_widths[i],
                                header_height,
                                fix_persian_text(header_txt),
                                border=1,
                                align="C",
                                fill=True,
                            )
                        pdf.ln(header_height)
                        pdf.set_font("Vazir", "", 9)  # Reset font for data

                    # --- تعیین رنگ پس‌زمینه بر اساس تگ ذخیره شده یا الگوی زبرا ---
                    # Get the original full data including tags for this row
                    original_tags_for_this_row = self.tree.item(item_id, "tags")

                    # Find the actual color tag applied (similar to saving logic)
                    row_color_tag_name = (
                        DEFAULT_ROW_TAG  # استفاده از مقدار پیش‌فرض اولیه (white)
                    )
                    known_colors = ["yellow", "lightgreen", "lightblue"]
                    has_custom_color = False

                    for tag in original_tags_for_this_row:
                        if tag in known_colors:
                            row_color_tag_name = tag
                            has_custom_color = True
                            break

                    # اگر رنگ سفارشی نبود، از الگوی زبرا استفاده کن
                    if not has_custom_color:
                        if row_idx % 2 == 0:
                            # رنگ سطرهای زوج
                            row_fill_color_rgb = zebra_color_1
                        else:
                            # رنگ سطرهای فرد
                            row_fill_color_rgb = zebra_color_2
                    else:
                        # استفاده از رنگ سفارشی تنظیم شده توسط کاربر
                        row_fill_color_rgb = color_map(row_color_tag_name)

                    # تنظیم رنگ پس‌زمینه
                    pdf.set_fill_color(*row_fill_color_rgb)
                    # --- پایان تعیین رنگ ---

                    # Draw cell borders first (as a background) - حالا current_row_height تعریف شده است
                    start_x = pdf.get_x()
                    start_y = pdf.get_y()
                    for i in range(len(current_values)):
                        try:
                            # تلاش با پارامتر ln (نسخه قدیمی‌تر FPDF)
                            pdf.multi_cell(
                                col_widths[i],
                                current_row_height,
                                "",
                                border=1,
                                align="C",
                                fill=True,
                                ln=3,
                            )
                        except TypeError:
                            # اگر خطا داد، بدون پارامتر ln امتحان کن
                            x_before = pdf.get_x()
                            y_before = pdf.get_y()
                            pdf.multi_cell(
                                col_widths[i],
                                current_row_height,
                                "",
                                border=1,
                                align="C",
                                fill=True,
                            )
                            # برگرداندن مکان‌نما به مکان بعدی (دستی شبیه‌سازی ln=3)
                            pdf.set_xy(x_before + col_widths[i], y_before)
                    pdf.set_xy(start_x, start_y)

                    # Draw text line by line, cell by cell
                    for line_num in range(max_lines):
                        for i, lines in enumerate(wrapped_cells):
                            text_to_draw = (
                                lines[line_num] if line_num < len(lines) else ""
                            )
                            current_y = start_y + line_num * row_height
                            pdf.set_xy(start_x + sum(col_widths[:i]), current_y)
                            pdf.cell(
                                col_widths[i],
                                row_height,
                                text_to_draw,
                                border=0,
                                align="C",
                            )

                    # Move cursor down below the drawn row block
                    pdf.set_y(start_y + current_row_height)

                    # اضافه کردن توضیحات اگر وجود داشته باشد - بدون فاصله اضافی
                    if tozihat_idx_in_all != -1 and tozihat_idx_in_all < len(values):
                        tozihat_text = str(values[tozihat_idx_in_all]).strip()
                        if tozihat_text:
                            # Check page break for tozihat
                            if pdf.get_y() + row_height > pdf.page_break_trigger:
                                pdf.add_page(orientation="L")

                            # تنظیم رنگ برای توضیحات (همان رنگ سطر اصلی یا زرد برای مشخص شدن)
                            pdf.set_fill_color(*row_fill_color_rgb)

                            pdf.set_font("Vazir", "", 8)
                            fixed_tozihat = fix_persian_text("توضیحات: " + tozihat_text)

                            # نمایش توضیحات با کادر کامل برای یکپارچگی با جدول - بدون ln اضافی
                            try:
                                pdf.multi_cell(
                                    sum(col_widths),
                                    row_height,
                                    fixed_tozihat,
                                    border=1,
                                    align="R",
                                    fill=True,
                                    ln=1,
                                )
                            except TypeError:
                                pdf.multi_cell(
                                    sum(col_widths),
                                    row_height,
                                    fixed_tozihat,
                                    border=1,
                                    align="R",
                                    fill=True,
                                )

                            pdf.set_font("Vazir", "", 9)  # Reset font size

                except Exception as e:
                    print(f"Error processing row {row_idx}: {e}")
                    continue

                # --- پایان بخش توضیحات ---

            # --- Save PDF ---
            pdf_file = os.path.join(PROJECTS_DIR, "order_table_output.pdf")
            pdf.output(pdf_file, "F")

            if messagebox.askyesno(
                "باز کردن فایل",
                f"فایل PDF با موفقیت ذخیره شد:\n{pdf_file}\n\nآیا مایلید فایل باز شود؟",
            ):
                open_file_externally(pdf_file)

        except Exception as e:
            messagebox.showerror(
                "خطا در خروجی PDF", f"مشکلی در ایجاد یا ذخیره فایل PDF رخ داد:\n{e}"
            )
            import traceback

            traceback.print_exc()  # Print detailed error for debugging

    # --- Settings Window ---

    def open_settings_window(self):
        """Opens the settings window for managing columns and combo options."""
        if self.settings_win and tk.Toplevel.winfo_exists(self.settings_win):
            self.settings_win.lift()
            self.settings_win.focus_force()
            return

        self.settings_win = tk.Toplevel(self.root)
        self.settings_win.title("⚙️ تنظیمات برنامه")
        self.settings_win.geometry("650x550")
        self.settings_win.transient(self.root)
        # self.settings_win.grab_set() # Make modal if preferred

        notebook_settings = ttk.Notebook(self.settings_win)
        notebook_settings.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Create Tabs ---
        self._create_settings_columns_tab(notebook_settings)
        self._create_settings_combos_tab(notebook_settings)

        # Focus the window when done
        self.settings_win.focus_set()
        self.settings_win.protocol(
            "WM_DELETE_WINDOW", self._on_settings_close
        )  # Handle closing

    def _on_settings_close(self):
        """Callback when the settings window is closed."""
        if self.settings_win:
            self.settings_win.destroy()
        self.settings_win = None  # Reset the reference

    # --- START OF REPLACEMENT for _create_settings_columns_tab and its inner functions ---

    def _generate_internal_key(self, display_name, existing_keys):
        """
        Generates a unique internal key based on the display name.
        Ensures the key is unique by appending a number if necessary.
        """
        base_key = "".join(c if c.isalnum() else "_" for c in display_name.lower())
        key = base_key
        counter = 1
        while key in existing_keys:
            key = f"{base_key}_{counter}"
            counter += 1
        return key

    # --- START OF REPLACEMENT for _create_settings_columns_tab ---

    def _create_settings_columns_tab(self, parent_notebook):
        """Creates the 'Manage Columns' tab, listing only manageable columns."""
        tab_columns = tk.Frame(parent_notebook)
        # Title changed slightly
        parent_notebook.add(tab_columns, text="🗂 مدیریت ستون‌های سفارشی/پایه")

        # --- Frame for Adding New Custom Column (Base columns are seeded, not added here) ---
        frame_add = tk.LabelFrame(
            tab_columns, text="➕ افزودن ستون سفارشی جدید", padx=10, pady=10
        )
        frame_add.pack(fill="x", padx=10, pady=10)
        tk.Label(frame_add, text="نام نمایشی ستون (فارسی مجاز):").pack(
            side=tk.LEFT, padx=5
        )
        entry_new_display_name = tk.Entry(frame_add, width=30)
        entry_new_display_name.pack(side=tk.LEFT, fill="x", expand=True, padx=5)
        add_status_label = tk.Label(frame_add, text="", fg="green")
        add_status_label.pack(side=tk.LEFT, padx=5)

        def add_new_column_action():  # Only adds CUSTOM columns now
            display_name = entry_new_display_name.get().strip()
            if not display_name:
                messagebox.showwarning("...", "...", parent=self.settings_win)
                return
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT column_name FROM custom_columns")
                existing_keys = {r[0] for r in cursor.fetchall()}
                conn.close()
                internal_key = self._generate_internal_key(
                    display_name, existing_keys
                )  # Generate key
                add_custom_column(internal_key, display_name)  # Add to DB
                entry_new_display_name.delete(0, tk.END)
                add_status_label.config(text=f"✅ '{display_name}' اضافه شد")
                self.settings_win.after(3500, lambda: add_status_label.config(text=""))
                refresh_column_list_action()
                self._refresh_settings_combo_columns()
                self._rebuild_main_tree(preserve_data=True)
            except Exception as e:
                messagebox.showerror(
                    "خطا", f"خطا در افزودن:\n{e}", parent=self.settings_win
                )

        btn_add = tk.Button(
            frame_add,
            text="افزودن",
            bg="green",
            fg="white",
            command=add_new_column_action,
        )
        btn_add.pack(side=tk.LEFT, padx=5)
        entry_new_display_name.bind("<Return>", lambda e: add_new_column_action())

        # --- Frame for Listing Manageable Columns (Base Non-Critical + Custom) ---
        frame_list = tk.LabelFrame(
            # Title changed
            tab_columns,
            text="📋 ستون‌های موجود (سفارشی و پایه غیرحیاتی)",
            padx=10,
            pady=10,
        )
        frame_list.pack(fill="both", expand=True, padx=10, pady=10)
        list_canvas = tk.Canvas(frame_list)
        list_scrollbar = ttk.Scrollbar(
            frame_list, orient="vertical", command=list_canvas.yview
        )
        list_scrollable_frame = ttk.Frame(list_canvas)
        list_scrollable_frame.bind(
            "<Configure>",
            lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")),
        )
        list_canvas.create_window((0, 0), window=list_scrollable_frame, anchor="nw")
        list_canvas.configure(yscrollcommand=list_scrollbar.set)
        list_canvas.pack(side="left", fill="both", expand=True)
        list_scrollbar.pack(side="right", fill="y")

        def refresh_column_list_action():
            for widget in list_scrollable_frame.winfo_children():
                widget.destroy()
            try:
                # *** Use the new DB function to get only manageable columns ***
                columns_data = get_manageable_columns_data()

                if not columns_data:
                    tk.Label(
                        list_scrollable_frame, text="ستون قابل مدیریتی یافت نشد."
                    ).pack(pady=10)
                    return

                for col_info in columns_data:
                    col_id = col_info["id"]
                    col_key = col_info["key"]
                    col_display = col_info["display"]
                    is_active = True  # get_manageable_columns_data fetches active ones

                    row_frame = tk.Frame(list_scrollable_frame)
                    row_frame.pack(fill="x", pady=3)
                    active_var = tk.BooleanVar(value=is_active)
                    # Pass col_id and new status to the handler
                    cb_active = tk.Checkbutton(
                        row_frame,
                        variable=active_var,
                        command=lambda v=active_var, c_id=col_id: toggle_column_active_status(
                            c_id, v.get()
                        ),
                    )
                    cb_active.pack(side=tk.LEFT, padx=5)
                    lbl_name = tk.Label(
                        row_frame, text=col_display, width=25, anchor="w"
                    )
                    lbl_name.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
                    # Edit display name button
                    btn_edit = tk.Button(
                        row_frame,
                        text="✏️ ویرایش نام",
                        bg="orange",
                        fg="black",
                        command=lambda c_id=col_id, old_display=col_display: edit_display_name_action(
                            c_id, old_display
                        ),
                    )
                    btn_edit.pack(side=tk.LEFT, padx=5)
                    # Delete button (DB function now prevents deleting critical ones)
                    btn_delete = tk.Button(
                        row_frame,
                        text="🗑 حذف",
                        bg="red",
                        fg="white",
                        command=lambda c_id=col_id, disp_name=col_display: delete_column_action(
                            c_id, disp_name
                        ),
                    )
                    btn_delete.pack(side=tk.LEFT, padx=5)

            except Exception as e:
                messagebox.showerror(
                    "خطا", f"مشکل در خواندن لیست:\n{e}", parent=self.settings_win
                )

        def toggle_column_active_status(col_id, new_status):
            try:
                # Call DB function (raises error if critical)
                update_custom_column_status(col_id, new_status)
                self._rebuild_main_tree(preserve_data=True)
                refresh_column_list_action()
                self._refresh_settings_combo_columns()
            except ValueError as ve:  # Catch error from DB function if critical
                messagebox.showerror("خطای عملیات", str(ve), parent=self.settings_win)
                refresh_column_list_action()  # Refresh list to show original state
            except Exception as e:
                messagebox.showerror(
                    "خطا", f"خطا در به‌روزرسانی وضعیت:\n{e}", parent=self.settings_win
                )
                refresh_column_list_action()

        def edit_display_name_action(col_id, old_display_name):
            # ... (Edit window code remains the same, but uses update_custom_column_display_name) ...
            edit_win = tk.Toplevel(self.settings_win)
            edit_win.title(f"ویرایش: {old_display_name}")
            edit_win.geometry("350x130")
            edit_win.transient(self.settings_win)
            edit_win.grab_set()
            tk.Label(edit_win, text="نام نمایشی جدید:").pack(padx=10, pady=5)
            new_name_entry = tk.Entry(edit_win, width=40)
            new_name_entry.pack(padx=10, pady=5)
            new_name_entry.insert(0, old_display_name)
            status_lbl = tk.Label(edit_win, text="", fg="green")
            status_lbl.pack(pady=2)

            def save_new():
                new_display = new_name_entry.get().strip()
                if not new_display:
                    messagebox.showerror("...", "...", parent=edit_win)
                    return
                if new_display == old_display_name:
                    edit_win.destroy()
                    return
                try:
                    # Call DB function (raises error if critical)
                    update_custom_column_display_name(col_id, new_display)
                    status_lbl.config(text="✅ به‌روز شد.")
                    edit_win.after(1500, edit_win.destroy)
                    refresh_column_list_action()
                    self._refresh_settings_combo_columns()
                    self._rebuild_main_tree(preserve_data=True)
                except ValueError as ve:  # Catch error from DB function if critical
                    messagebox.showerror("خطای عملیات", str(ve), parent=edit_win)
                except Exception as e:
                    messagebox.showerror(
                        "خطا", f"خطا در به‌روزرسانی نام:\n{e}", parent=edit_win
                    )

            btn = tk.Button(edit_win, text="ذخیره", command=save_new)
            btn.pack(pady=10)
            edit_win.wait_window(edit_win)

        def delete_column_action(col_id, display_name):
            if not messagebox.askyesno(
                "تأیید حذف",
                f"حذف ستون '{display_name}'؟\n(ستون‌های پایه حیاتی حذف نمی‌شوند)",
                icon="warning",
                parent=self.settings_win,
            ):
                return
            try:
                # Call DB function (raises error if critical)
                delete_custom_column(col_id)
                messagebox.showinfo(
                    "حذف موفق",
                    f"ستون '{display_name}' حذف شد.",
                    parent=self.settings_win,
                )
                refresh_column_list_action()
                self._refresh_settings_combo_columns()
                self._rebuild_main_tree(preserve_data=True)
            except ValueError as ve:  # Catch error from DB function if critical
                messagebox.showerror("خطای عملیات", str(ve), parent=self.settings_win)
            except Exception as e:
                messagebox.showerror(
                    "خطا", f"مشکل در حذف:\n{e}", parent=self.settings_win
                )

        refresh_column_list_action()  # Initial load

    # --- END OF REPLACEMENT for _create_settings_columns_tab ---

    # --- END OF REPLACEMENT for _create_settings_columns_tab and its inner functions ---

    # --- START OF REPLACEMENT PART 1 for _create_settings_combos_tab ---

    def _create_settings_combos_tab(self, parent_notebook):
        """Creates the 'Manage Combobox Options' tab, listing base and custom columns."""
        tab_combos = tk.Frame(parent_notebook)
        parent_notebook.add(tab_combos, text="🏷 مدیریت گزینه‌های کمبوباکس")

        # --- Column Selection (Uses get_all_configurable_columns_data) ---
        frame_select = tk.LabelFrame(
            tab_combos, text="1. انتخاب ستون (پایه یا سفارشی)", padx=10, pady=10
        )
        frame_select.pack(fill="x", padx=10, pady=(10, 5))
        tk.Label(frame_select, text="ستون:").pack(side=tk.LEFT, padx=5)
        self.settings_combo_columns = ttk.Combobox(
            frame_select, state="readonly", width=35
        )
        self.settings_combo_columns.pack(side=tk.LEFT, fill="x", expand=True, padx=5)
        # Store data as {display_name: column_id} for easier lookup
        self.settings_combo_columns.column_id_map = {}

        # --- Add New Option ---
        frame_add = tk.LabelFrame(
            tab_combos, text="2. افزودن/ویرایش گزینه", padx=10, pady=10
        )
        frame_add.pack(fill="x", padx=10, pady=5)
        tk.Label(frame_add, text="مقدار گزینه:").pack(side=tk.LEFT, padx=5)
        entry_new_option = tk.Entry(frame_add, width=30)
        entry_new_option.pack(side=tk.LEFT, fill="x", expand=True, padx=5)
        add_option_status_label = tk.Label(frame_add, text="", fg="green")
        add_option_status_label.pack(side=tk.LEFT, padx=5)

        # --- Option List ---
        frame_list = tk.LabelFrame(
            tab_combos, text="3. گزینه‌های موجود", padx=10, pady=10
        )
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)
        listbox_options = tk.Listbox(frame_list, height=8)
        listbox_options.pack(side=tk.LEFT, fill="both", expand=True)
        listbox_options.options_data = {}  # {value: option_id}
        scrollbar_options = tk.Scrollbar(
            frame_list, orient="vertical", command=listbox_options.yview
        )
        scrollbar_options.pack(side=tk.LEFT, fill="y")
        listbox_options.config(yscrollcommand=scrollbar_options.set)

        # --- Buttons Frame ---
        frame_buttons = tk.Frame(tab_combos)
        frame_buttons.pack(fill="x", padx=10, pady=(0, 10))

        # --- Action Functions ---

        # --- START OF REPLACEMENT PART 2 for _create_settings_combos_tab (Action Functions & Bindings) ---
        # (This code should follow PART 1 immediately, at the same indentation level within the class)

        # --- Action Functions (Defined within _create_settings_combos_tab scope) ---

        def load_options_for_selected_column():
            listbox_options.delete(0, tk.END)
            listbox_options.options_data.clear()
            selected_display_name = self.settings_combo_columns.get()
            if not selected_display_name:
                return
            column_id = self.settings_combo_columns.column_id_map.get(
                selected_display_name
            )
            if column_id is None:
                return
            try:
                # Fetch options with their IDs for deletion/update
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, option_value FROM custom_column_options WHERE column_id = ? ORDER BY id",
                    (column_id,),
                )
                options_with_ids = cursor.fetchall()
                conn.close()

                for opt_id, opt_value in options_with_ids:
                    listbox_options.insert(tk.END, opt_value)
                    # Store {value: option_id}
                    listbox_options.options_data[opt_value] = opt_id
            except Exception as e:
                messagebox.showerror(
                    "خطا", f"خطا در خواندن گزینه‌ها:\n{e}", parent=self.settings_win
                )

        def add_or_update_option_action():
            option_value = entry_new_option.get().strip()
            if not option_value:
                messagebox.showwarning(
                    "ورودی نامعتبر",
                    "مقدار گزینه نباید خالی باشد.",
                    parent=self.settings_win,
                )
                return
            selected_display_name = self.settings_combo_columns.get()
            if not selected_display_name:
                messagebox.showerror(
                    "انتخاب نشده", "لطفاً ستون را انتخاب کنید.", parent=self.settings_win
                )
                return
            column_id = self.settings_combo_columns.column_id_map.get(
                selected_display_name
            )
            if column_id is None:
                return

            target_option_id = None
            status_message = ""
            selected_indices = listbox_options.curselection()
            if selected_indices:
                selected_value_in_list = listbox_options.get(selected_indices[0])
                target_option_id = listbox_options.options_data.get(
                    selected_value_in_list
                )
                if (
                    option_value == selected_value_in_list
                    and target_option_id is not None
                ):
                    add_option_status_label.config(text="ℹ️ بدون تغییر")
                    self.settings_win.after(
                        2000, lambda: add_option_status_label.config(text="")
                    )
                    return

            try:
                # Update logic (Requires DB function)
                if target_option_id is not None:
                    # Placeholder - Assume update_column_option(option_id, new_value) exists in database.py
                    # update_column_option(target_option_id, option_value)
                    print(
                        f"Update needs DB function: update_column_option({target_option_id}, '{option_value}')"
                    )
                    messagebox.showinfo(
                        "توجه",
                        "قابلیت به‌روزرسانی گزینه فعلاً پیاده‌سازی نشده است.\nبرای تغییر، گزینه را حذف و دوباره اضافه کنید.",
                        parent=self.settings_win,
                    )
                    # Temp message
                    status_message = f"✅ '{selected_value_in_list}' (به‌روزرسانی نیاز به پیاده‌سازی دارد)"
                    # If implemented, message should be: f"✅ '{selected_value_in_list}' -> '{option_value}' به‌روز شد"
                else:  # Add new
                    # Use existing DB function
                    add_option_to_column(column_id, option_value)
                    status_message = f"✅ '{option_value}' اضافه شد"

                entry_new_option.delete(0, tk.END)
                add_option_status_label.config(text=status_message)
                self.settings_win.after(
                    3000, lambda: add_option_status_label.config(text="")
                )
                load_options_for_selected_column()
                listbox_options.selection_clear(0, tk.END)
            except sqlite3.IntegrityError:
                messagebox.showerror(
                    "خطا",
                    f"مقدار '{option_value}' تکراری است.",
                    parent=self.settings_win,
                )
            except Exception as e:
                messagebox.showerror(
                    "خطا", f"خطا در افزودن/ویرایش:\n{e}", parent=self.settings_win
                )

        def delete_option_action():
            selected_indices = listbox_options.curselection()
            if not selected_indices:
                messagebox.showwarning(
                    "انتخاب نشده",
                    "گزینه را برای حذف انتخاب کنید.",
                    parent=self.settings_win,
                )
                return
            selected_value = listbox_options.get(selected_indices[0])
            option_id = listbox_options.options_data.get(selected_value)
            if option_id is None:
                messagebox.showerror(
                    "خطای داخلی", "شناسه گزینه یافت نشد!", parent=self.settings_win
                )
                return
            if not messagebox.askyesno(
                "تأیید حذف",
                f"آیا از حذف گزینه '{selected_value}' مطمئن هستید؟",
                icon="warning",
                parent=self.settings_win,
            ):
                return
            try:
                # Use DB function taking option's ID
                delete_column_option(option_id)
                add_option_status_label.config(
                    text=f"🗑 گزینه '{selected_value}' حذف شد."
                )
                self.settings_win.after(
                    3000, lambda: add_option_status_label.config(text="")
                )
                load_options_for_selected_column()
                # Clear entry field after delete
                entry_new_option.delete(0, tk.END)
            except Exception as e:
                messagebox.showerror(
                    "خطا", f"خطا در حذف:\n{e}", parent=self.settings_win
                )

        def on_option_select(event):
            selected_indices = listbox_options.curselection()
            if selected_indices:
                entry_new_option.delete(0, tk.END)
                entry_new_option.insert(0, listbox_options.get(selected_indices[0]))
            else:
                entry_new_option.delete(0, tk.END)

        # --- Add Buttons and Bind Commands ---
        btn_add_update = tk.Button(
            frame_buttons,
            text="افزودن / به‌روزرسانی گزینه",
            bg="green",
            fg="white",
            command=add_or_update_option_action,
            width=25,
        )
        btn_add_update.pack(side=tk.LEFT, padx=10, pady=5)
        entry_new_option.bind(
            "<Return>", lambda e: add_or_update_option_action()
        )  # Bind Enter key

        btn_delete = tk.Button(
            frame_buttons,
            text="حذف گزینه انتخاب شده",
            bg="red",
            fg="white",
            command=delete_option_action,
            width=20,
        )
        btn_delete.pack(side=tk.LEFT, padx=10, pady=5)

        # --- Bindings and Initial Load ---
        self.settings_combo_columns.bind(
            "<<ComboboxSelected>>", lambda e: load_options_for_selected_column()
        )
        listbox_options.bind("<<ListboxSelect>>", on_option_select)
        self._refresh_settings_combo_columns()  # Load columns initially

    # --- END OF REPLACEMENT PART 2 for _create_settings_combos_tab ---

    # --- START OF REPLACEMENT for _refresh_settings_combo_columns ---

    def _refresh_settings_combo_columns(self):
        """Loads configurable columns (non-critical base & custom) into the settings combo box."""
        if not (
            self.settings_win
            and tk.Toplevel.winfo_exists(self.settings_win)
            and hasattr(self, "settings_combo_columns")
        ):
            return

        try:
            # *** Use the correct DB function to get columns for combo config ***
            columns_data = get_all_configurable_columns_data()

            display_names = [col["display"] for col in columns_data]
            self.settings_combo_columns["values"] = display_names
            self.settings_combo_columns.column_id_map = {
                col["display"]: col["id"] for col in columns_data
            }

            if display_names:
                self.settings_combo_columns.current(0)
            else:
                self.settings_combo_columns.set("")

            self.settings_combo_columns.event_generate("<<ComboboxSelected>>")

        except Exception as e:
            messagebox.showerror(
                "خطا",
                f"خطا در بارگذاری ستون‌ها برای کمبوباکس:\n{e}",
                parent=self.settings_win,
            )

    # --- END OF REPLACEMENT for _refresh_settings_combo_columns ---

    # --- Run Method ---

    def run(self):
        """Starts the Tkinter main loop."""
        self.root.mainloop()


# --- Main Execution ---
if __name__ == "__main__":
    # راه‌اندازی سیستم لاگینگ
    app_logger = ProgramLogger()
    # سطح پیش‌فرض (می‌تواند از طریق تنظیمات برنامه تغییر کند)
    log_level = (logging.INFO,)
    log_to_file = (True,)  # ذخیره لاگ‌ها در فایل
    log_dir = "logs"  # پوشه لاگ‌ها
    # ایجاد لاگر برای بخش‌های مختلف برنامه
    db_logger = app_logger.get_module_logger("DATABASE")
    ui_logger = app_logger.get_module_logger("UI")
    tree_logger = app_logger.get_module_logger("TREEVIEW")
    project_logger = app_logger.get_module_logger("PROJECT")
    root = tk.Tk()
    app = CuttingApp(root, app_logger)
    app.run()

# --- END OF REFACTORED FILE ---
