import tkinter as tk
from tkinter import ttk, messagebox
import math

# --- Lookup Tables (from sheet, rows 17 onwards) ---
قیمت_انواع_پروفیل = {
    "فریم لس قدیمی": 1.7,
    "فریم لس قالب جدید": 1.9,
    "توچوب دار": 1.5,
    "دور آلومینیوم": 1.5,
}

قیمت_ملزومات_نصب = {
    "لاستیک": 98000,
    "بست نصب": 600000,
}

قیمت_اجرت_ماشین_کاری = {
    "چهارچوب فریم لس": 20000000,
    "داخل چوب": 40000000,
    "دور آلومینیوم": 50000000,
}

قیمت_رنگ_آلومینیوم_جدول = {
    "خام": 3450000,
    "آنادایز": 3950000,
    "رنگی": 3750000,
}

قیمت_جنس_درب = {
    "ام دی اف": 0,
    "پلای وود": 19000000,
}

# New dictionary for base door prices by height
قیمت_پایه_درب_خام_بر_اساس_ارتفاع = {
    "تا 260 سانتی متر": 121000000,
    "261 تا 320 سانتی متر": 133100000,
    "321 تا 360 سانتی متر": 145200000,
    "بیش از 360 سانتی متر": 145200000, # Default for heights > 360
}

def get_قیمت_پایه_درب_خام(height_cm):
    if height_cm <= 260:
        return قیمت_پایه_درب_خام_بر_اساس_ارتفاع["تا 260 سانتی متر"]
    elif height_cm <= 320:
        return قیمت_پایه_درب_خام_بر_اساس_ارتفاع["261 تا 320 سانتی متر"]
    elif height_cm <= 360:
        return قیمت_پایه_درب_خام_بر_اساس_ارتفاع["321 تا 360 سانتی متر"]
    else:
        return قیمت_پایه_درب_خام_بر_اساس_ارتفاع["بیش از 360 سانتی متر"]

قیمت_خدمات_رنگ = {
    ("رنگ نهایی", "خارجی"): 27000000,
    ("رنگ نهایی", "ایرانی"): 20000000,
    ("زیر سازی", "خارجی"): 22000000,
    ("زیر سازی", "ایرانی"): 15000000,
    ("کد رنگ", "خارجی"): 33000000,
    ("کد رنگ", "ایرانی"): 25000000,
}

قیمت_یراق_آلات = {
    "لولا": 18000000,
    "قفل": 14000000,
    "سیلندر": 6800000,
}

# --- Selections and Markups (from sheet, row 6 & 7) ---
# For GUI simplicity, these selections are initially fixed as per the example.
# They can be made dynamic with checkboxes and entry fields.
selections = {
    "درب_خام":            (False, 0),
    "درب_با_رنگ_کامل":   (True, 30),
    "فریم":              (True, 30),
    "یراق_کامل":         (True, 10),
    "رنگ_کاری":          (False, 0),
}


def calculate_costs(inputs, component_markup_rules):
    results = {}

    input_عرض_درب = inputs["عرض_درب"]
    input_ارتفاع_درب = inputs["ارتفاع_درب"]
    input_نوع_پروفیل_فریم_لس = inputs["نوع_پروفیل_فریم_لس"]
    input_رنگ_آلومینیوم = inputs["رنگ_آلومینیوم"]
    input_جنس_درب = inputs["جنس_درب"]
    input_شرایط_رنگ = inputs["شرایط_رنگ"]
    input_رند_رنگ = inputs["رند_رنگ"]

    # --- محاسبه داینامیک متراژ پروفیل کل بر اساس ابعاد درب ---
    # محیط یک درب (چهارچوب) = عرض + ارتفاع + ارتفاع (برای دو سمت عمودی)
    # ابعاد ورودی (عرض و ارتفاع) به سانتی متر هستند.
    محیط_پایه_پروفیل_سانتی_متر = input_عرض_درب + (2 * input_ارتفاع_درب)

    # رند کردن به عدد ۱۰۰گان بعدی برای متراژ پروفیل کل (به سانتی متر).
    # مثال: ورودی 670 سانتی متر -> خروجی 700 سانتی متر. ورودی 500 -> خروجی 500.
    sheet_F14_متراژ_پروفیل_کل = math.ceil(محیط_پایه_پروفیل_سانتی_متر / 100.0) * 100

    # --- Calculate Base 100% Costs for each fundamental item (before any selectable component markup) ---
    # calc_... prefix here denotes these are calculated fundamental costs.
    calc_D14_هزینه_درب_خام_یک_درب = get_قیمت_پایه_درب_خام(input_ارتفاع_درب) + قیمت_جنس_درب[input_جنس_درب]
    # This is a fundamental cost, also used as the base for "درب_خام" component
    results["D14_هزینه_درب_خام_یک_درب_base"] = calc_D14_هزینه_درب_خام_یک_درب 

    calc_E14_وزن_پروفیل_واحد = قیمت_انواع_پروفیل[input_نوع_پروفیل_فریم_لس]
    results["E14_وزن_پروفیل_واحد"] = calc_E14_وزن_پروفیل_واحد # Informational

    # sheet_F14_متراژ_پروفیل_کل = 700 # Original fixed value, now calculated dynamically above
    # results["F14_متراژ_پروفیل_کل"] = sheet_F14_متراژ_پروفیل_کل # Informational, not directly displayed by default

    alu_color_key = "رنگی" if input_رنگ_آلومینیوم == "سفید" else input_رنگ_آلومینیوم
    if alu_color_key not in قیمت_رنگ_آلومینیوم_جدول:
         raise ValueError(f"رنگ آلومینیوم نامعتبر: {alu_color_key}.")
    calc_G14_هزینه_فریم_پروفیل_کل = (sheet_F14_متراژ_پروفیل_کل * calc_E14_وزن_پروفیل_واحد * قیمت_رنگ_آلومینیوم_جدول[alu_color_key]) / 100
    results["G14_هزینه_فریم_کل"] = calc_G14_هزینه_فریم_پروفیل_کل # Display this as "هزینه پایه فریم (کل)"

    # ضریب_اصلاحی_لاستیک = 30 # Removed as per user request
    # ضریب_واحد_لاستیک = 100  # Removed as per user request
    # calc_H14_هزینه_لاستیک_کل = (sheet_F14_متراژ_پروفیل_کل - ضریب_اصلاحی_لاستیک) * (قیمت_ملزومات_نصب["لاستیک"] / ضریب_واحد_لاستیک) # Old calculation

    # --- محاسبه هزینه لاستیک مطابق با فرمول شیت ---
    # فرمول شیت: =(('سفارشات '!D2 + 'سفارشات '!E2 * 2) / 100) * 'سفارشات '!E19
    # 'سفارشات '!D2 -> input_عرض_درب
    # 'سفارشات '!E2 -> input_ارتفاع_درب
    # 'سفارشات '!E19 -> قیمت_ملزومات_نصب["لاستیک"] (با این فرض که این قیمت واحد پس از تبدیل محیط به متر است)

    محیط_برای_لاستیک_سانتی_متر = input_عرض_درب + (2 * input_ارتفاع_درب)

    # اگر قیمت_ملزومات_نصب["لاستیک"] قیمت هر متر لاستیک است،
    # و محیط به سانتی متر است، پس باید محیط را به متر تبدیل کنیم:
    محیط_برای_لاستیک_متر = محیط_برای_لاستیک_سانتی_متر / 100.0

    # فرض می کنیم قیمت_ملزومات_نصب["لاستیک"] همان 'سفارشات '!E19 است (قیمت هر متر)
    calc_H14_هزینه_لاستیک_کل = محیط_برای_لاستیک_متر * قیمت_ملزومات_نصب["لاستیک"]

    # sheet_I14_تعداد_بست_کل = 10 # Original fixed value, now calculated dynamically below
    # results["I14_تعداد_بست_کل"] = sheet_I14_تعداد_بست_کل # Informational

    # --- محاسبه داینامیک تعداد بست نصب ---
    # فرمول شیت: =CEILING('سفارشات '!E2 / 60, 1) * 2
    # 'سفارشات '!E2 -> input_ارتفاع_درب (فرض می شود به سانتی متر است)

    if input_ارتفاع_درب <= 0: # جلوگیری از تقسیم بر صفر یا نتایج نامعقول برای ارتفاع نامعتبر
        تعداد_بست_پایه = 0
    else:
        تعداد_بست_پایه = math.ceil(input_ارتفاع_درب / 60.0) 
        # math.ceil معادل CEILING(..., 1) در اکسل است وقتی به عدد صحیح گرد می کنیم.
    sheet_I14_تعداد_بست_کل = تعداد_بست_پایه * 2

    calc_J14_هزینه_بست_نصب_کل = sheet_I14_تعداد_بست_کل * قیمت_ملزومات_نصب["بست نصب"]

    اجرت_ماشین_کاری_key = "چهارچوب فریم لس" 
    if input_نوع_پروفیل_فریم_لس == "فریم لس قالب جدید": اجرت_ماشین_کاری_key = "چهارچوب فریم لس"
    elif input_نوع_پروفیل_فریم_لس == "توچوب دار": اجرت_ماشین_کاری_key = "داخل چوب"
    elif input_نوع_پروفیل_فریم_لس == "دور آلومینیوم": اجرت_ماشین_کاری_key = "دور آلومینیوم"
    if اجرت_ماشین_کاری_key not in قیمت_اجرت_ماشین_کاری:
        raise ValueError(f"نگاشت نامعتبر برای اجرت ماشین کاری: {input_نوع_پروفیل_فریم_لس}")
    calc_K14_اجرت_ماشین_کاری_کل = قیمت_اجرت_ماشین_کاری[اجرت_ماشین_کاری_key]

    sheet_L14_مساحت_رنگ_کاری_یک_درب = 5.48
    # results["L14_مساحت_رنگ_کاری_یک_درب"] = sheet_L14_مساحت_رنگ_کاری_یک_درب # Informational

    # Get unit paint service cost per square meter
    unit_paint_service_cost_per_sqm = 0.0
    if (input_شرایط_رنگ, input_رند_رنگ) not in قیمت_خدمات_رنگ:
        raise ValueError(f"ترکیب شرایط رنگ و رند رنگ نامعتبر است.")
    unit_paint_service_cost_per_sqm = قیمت_خدمات_رنگ[(input_شرایط_رنگ, input_رند_رنگ)]

    # Calculate paint area (paint_area_sqm) based on door dimensions
    # width و height اینجا باید مقادیر عددی سانتی متر باشند
    if input_عرض_درب > 10 and input_ارتفاع_درب > 6:  # برای جلوگیری از مساحت منفی
        paint_area_sqm = ((input_عرض_درب - 10.0) * (input_ارتفاع_درب - 6.0) * 2.0) / 10000.0
    else:
        paint_area_sqm = 0.0  # یا مقدار پیش فرض دیگر یا ایجاد خطا

    # Calculate total paint service cost
    calc_N14_هزینه_کل_رنگ_کاری_یک_درب = paint_area_sqm * unit_paint_service_cost_per_sqm
    results["N14_هزینه_کل_رنگ_کاری_یک_درب"] = calc_N14_هزینه_کل_رنگ_کاری_یک_درب # Display as "هزینه پایه رنگ کاری (یک درب)"

    sheet_O14_تعداد_لولا_خاص = 5
    # results["O14_تعداد_لولا_خاص"] = sheet_O14_تعداد_لولا_خاص # Informational

    calc_A14_هزینه_لولا_کل = sheet_O14_تعداد_لولا_خاص * قیمت_یراق_آلات["لولا"]
    calc_B14_هزینه_قفل_کل = قیمت_یراق_آلات["قفل"]
    calc_C14_هزینه_سیلندر_کل = قیمت_یراق_آلات["سیلندر"]

    # --- Start of user-directed modifications within calculate_costs ---

    # الف) اصلاح محاسبه سهم یراق کامل (calc_E11_یراق_کامل)
    base_cost_yaraq_kamel = calc_A14_هزینه_لولا_کل + calc_B14_هزینه_قفل_کل + calc_C14_هزینه_سیلندر_کل
    # component_markup_rules[key] is (is_selected, markup_decimal_from_gui)
    # markup_decimal_from_gui is e.g. 0.30 for 30%
    # User wants: base_cost * "ضریب مشارکت"
    # If "ضریب مشارکت" is markup_decimal_from_gui, this becomes base_cost * markup_decimal_from_gui
    # If item is not selected, markup_decimal_from_gui is forced to 0.0 in perform_calculation if entry is empty OR checkbox is off.
    # More accurately, component_markup_rules stores (is_selected, effective_markup_decimal)
    # where effective_markup_decimal is 0 if not selected or invalid, else it's the user's input (e.g. 0.3 for 30%)

    selected_yaraq, markup_decimal_yaraq = component_markup_rules.get("یراق_کامل", (False, 0.0))
    if selected_yaraq:
        calc_E11_یراق_کامل = base_cost_yaraq_kamel * (1 + markup_decimal_yaraq)
    else:
        calc_E11_یراق_کامل = 0.0
    results["E11_یراق_کامل"] = calc_E11_یراق_کامل

    # ب) اصلاح محاسبه سهم فریم (calc_D11_فریم)
    base_cost_frame = calc_G14_هزینه_فریم_پروفیل_کل + calc_H14_هزینه_لاستیک_کل + calc_J14_هزینه_بست_نصب_کل + calc_K14_اجرت_ماشین_کاری_کل
    selected_frame, markup_decimal_frame = component_markup_rules.get("فریم", (False, 0.0))
    if selected_frame:
        calc_D11_فریم = base_cost_frame * (1 + markup_decimal_frame)
    else:
        calc_D11_فریم = 0.0
    results["D11_فریم"] = calc_D11_فریم

    # ج) اصلاح محاسبه سهم درب با رنگ کامل (calc_C11_درب_با_رنگ_کامل)
    base_cost_one_door_colored = calc_D14_هزینه_درب_خام_یک_درب + calc_N14_هزینه_کل_رنگ_کاری_یک_درب
    selected_door_colored, markup_decimal_door_colored = component_markup_rules.get("درب_با_رنگ_کامل", (False, 0.0))
    if selected_door_colored:
        calc_C11_درب_با_رنگ_کامل = base_cost_one_door_colored * (1 + markup_decimal_door_colored)
    else:
        calc_C11_درب_با_رنگ_کامل = 0.0
    results["C11_درب_با_رنگ_کامل"] = calc_C11_درب_با_رنگ_کامل
    
    # د) محاسبه سهم درب خام (results["D14_هزینه_درب_خام_یک_درب"] to match display key)
    # Base cost for "درب خام" component is simply calc_D14_هزینه_درب_خام_یک_درب
    selected_door_raw, markup_decimal_door_raw = component_markup_rules.get("درب_خام", (False, 0.0))
    if selected_door_raw:
        # Storing in "D14_هزینه_درب_خام_یک_درب" to match result_keys_to_display for "سهم نهایی درب خام"
        results["D14_هزینه_درب_خام_یک_درب"] = calc_D14_هزینه_درب_خام_یک_درب * (1 + markup_decimal_door_raw)
    else:
        results["D14_هزینه_درب_خام_یک_درب"] = 0.0

    # ه) محاسبه سهم رنگ کاری مجزا (results["رنگ_کاری_contrib"])
    # Base cost for "رنگ کاری (مجزا)" component is calc_N14_هزینه_کل_رنگ_کاری_یک_درب
    selected_painting, markup_decimal_painting = component_markup_rules.get("رنگ_کاری", (False, 0.0))
    if selected_painting:
        results["رنگ_کاری_contrib"] = calc_N14_هزینه_کل_رنگ_کاری_یک_درب * (1 + markup_decimal_painting)
    else:
        results["رنگ_کاری_contrib"] = 0.0

    # و) اصلاح محاسبه total_cost (هزینه کل نهایی)
    # Summing the final *contributions* of selected components (which now include their markups)
    total_cost = (
        results.get("D14_هزینه_درب_خام_یک_درب", 0.0) +  # This now stores final contribution of raw door
        results.get("C11_درب_با_رنگ_کامل", 0.0) +
        results.get("D11_فریم", 0.0) +
        results.get("E11_یراق_کامل", 0.0) +
        results.get("رنگ_کاری_contrib", 0.0)
    )
    results["total_cost"] = total_cost
    
    # --- End of user-directed modifications ---

    return results

class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, update_callback):
        super().__init__(parent)
        self.update_callback = update_callback
        self.title("تنظیمات قیمت های پایه")
        self.geometry("700x550")
        self.transient(parent) # Keep on top of main window
        self.grab_set() # Modal behavior

        self.entries = {}

        notebook = ttk.Notebook(self)
        
        # Tab data: (tab_name, dictionary_to_edit, value_type)
        # For قیمت_خدمات_رنگ, keys are tuples. We'll handle this by creating labels from tuple parts.
        # For قیمت_پایه_درب_خام_بر_اساس_ارتفاع, keys are descriptive strings.
        tabs_data = [
            ("یراق آلات", قیمت_یراق_آلات, int),
            ("ملزومات نصب", قیمت_ملزومات_نصب, int),
            ("انواع پروفیل (وزن)", قیمت_انواع_پروفیل, float), # وزن میتواند اعشاری باشد
            ("جنس درب", قیمت_جنس_درب, int),
            ("رنگ آلومینیوم (جدول)", قیمت_رنگ_آلومینیوم_جدول, int),
            ("اجرت ماشین کاری", قیمت_اجرت_ماشین_کاری, int),
            ("خدمات رنگ", قیمت_خدمات_رنگ, int),
            ("قیمت پایه درب خام (ارتفاع)", قیمت_پایه_درب_خام_بر_اساس_ارتفاع, int),
        ]

        for tab_name, price_dict, value_type in tabs_data:
            frame = ttk.Frame(notebook, padding="10")
            notebook.add(frame, text=tab_name)
            self.entries[tab_name] = {}
            row = 0
            # Add a scrollbar if content exceeds frame height
            canvas = tk.Canvas(frame)
            scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
            scrollable_frame = ttk.Frame(canvas)

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(
                    scrollregion=canvas.bbox("all")
                )
            )
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            for key, value in price_dict.items():
                # Create a display key for tuple keys in قیمت_خدمات_رنگ
                if isinstance(key, tuple):
                    display_key = f"{key[0]} ({key[1]})"
                else:
                    display_key = str(key)
                
                lbl = ttk.Label(scrollable_frame, text=f"{display_key}:")
                lbl.grid(row=row, column=0, sticky=tk.W, pady=2)
                
                entry_var = tk.StringVar(value=str(value))
                entry = ttk.Entry(scrollable_frame, textvariable=entry_var, width=15, justify='right')
                entry.grid(row=row, column=1, sticky=tk.EW, pady=2, padx=5)
                
                self.entries[tab_name][key] = (entry_var, value_type) # Store var and expected type
                row += 1
            
            scrollable_frame.columnconfigure(1, weight=1) # Allow entries to expand
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")


        notebook.pack(expand=True, fill="both", padx=10, pady=10)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, pady=10, padx=10, side=tk.BOTTOM)

        save_button = ttk.Button(button_frame, text="ذخیره تغییرات", command=self.save_settings)
        save_button.pack(side=tk.RIGHT, padx=5)

        cancel_button = ttk.Button(button_frame, text="لغو", command=self.destroy)
        cancel_button.pack(side=tk.RIGHT)
        
        # Center the window
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")


    def save_settings(self):
        updated_any = False
        all_valid = True
        for tab_name, items in self.entries.items():
            # Find the original dictionary by tab_name (a bit indirect, but works with current setup)
            original_dict_ref = None
            if tab_name == "یراق آلات": original_dict_ref = قیمت_یراق_آلات
            elif tab_name == "ملزومات نصب": original_dict_ref = قیمت_ملزومات_نصب
            elif tab_name == "انواع پروفیل (وزن)": original_dict_ref = قیمت_انواع_پروفیل
            elif tab_name == "جنس درب": original_dict_ref = قیمت_جنس_درب
            elif tab_name == "رنگ آلومینیوم (جدول)": original_dict_ref = قیمت_رنگ_آلومینیوم_جدول
            elif tab_name == "اجرت ماشین کاری": original_dict_ref = قیمت_اجرت_ماشین_کاری
            elif tab_name == "خدمات رنگ": original_dict_ref = قیمت_خدمات_رنگ
            elif tab_name == "قیمت پایه درب خام (ارتفاع)": original_dict_ref = قیمت_پایه_درب_خام_بر_اساس_ارتفاع
            
            if original_dict_ref is None:
                print(f"Warning: Could not find original dictionary for tab: {tab_name}")
                continue

            for key, (entry_var, value_type) in items.items():
                try:
                    new_value_str = entry_var.get()
                    new_value = value_type(new_value_str) # Convert to expected type (int or float)
                    
                    if original_dict_ref[key] != new_value:
                        original_dict_ref[key] = new_value
                        updated_any = True
                except ValueError:
                    all_valid = False
                    messagebox.showerror("خطای ورودی", f"مقدار نامعتبر برای '{key}' در تب '{tab_name}'. لطفاً یک عدد صحیح وارد کنید.", parent=self)
                    return # Stop saving on first error
        
        if not all_valid:
            return

        if updated_any:
            messagebox.showinfo("ذخیره شد", "تغییرات قیمت پایه با موفقیت ذخیره شد.", parent=self)
            self.update_callback() # Call the callback to update main GUI
        else:
            messagebox.showinfo("بدون تغییر", "هیچ تغییری برای ذخیره وجود نداشت.", parent=self)
        self.destroy()


class PriceCalculatorApp:
    def __init__(self, master):
        self.master = master
        master.title("محاسبه گر قیمت درب")
        master.geometry("650x900") # Adjusted height for new entry fields

        style = ttk.Style()
        style.configure("TLabel", font=("Tahoma", 9), padding=5)
        style.configure("TButton", font=("Tahoma", 10, "bold"), padding=5)
        style.configure("TEntry", font=("Tahoma", 9), padding=5, width=5) # Default width for percentage entries
        style.configure("Input.TEntry", font=("Tahoma", 9), padding=5, width=15) # For main inputs
        style.configure("TCombobox", font=("Tahoma", 9), padding=5)
        style.configure("Header.TLabel", font=("Tahoma", 12, "bold"))
        style.configure("TCheckbutton", font=("Tahoma", 9), padding=(0,5))


        main_frame = ttk.Frame(master, padding="10 10 10 10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        inputs_frame = ttk.LabelFrame(main_frame, text="ورودی های سفارش", padding="10 10 10 10")
        inputs_frame.pack(fill=tk.X, pady=5) 
        inputs_frame.columnconfigure(1, weight=1)

        self.inputs = {}
        row_idx = 0

        # عرض درب
        ttk.Label(inputs_frame, text="عرض درب (سانتی متر):").grid(row=row_idx, column=0, sticky=tk.W)
        self.inputs["عرض_درب"] = ttk.Entry(inputs_frame, style="Input.TEntry", justify='right')
        self.inputs["عرض_درب"].insert(0, "110")
        self.inputs["عرض_درب"].grid(row=row_idx, column=1, sticky=tk.EW, padx=5)
        row_idx += 1

        # ارتفاع درب
        ttk.Label(inputs_frame, text="ارتفاع درب (سانتی متر):").grid(row=row_idx, column=0, sticky=tk.W)
        self.inputs["ارتفاع_درب"] = ttk.Entry(inputs_frame, style="Input.TEntry", justify='right')
        self.inputs["ارتفاع_درب"].insert(0, "280")
        self.inputs["ارتفاع_درب"].grid(row=row_idx, column=1, sticky=tk.EW, padx=5)
        row_idx += 1
        
        # نوع پروفیل فریم لس
        ttk.Label(inputs_frame, text="نوع پروفیل فریم لس:").grid(row=row_idx, column=0, sticky=tk.W)
        self.inputs["نوع_پروفیل_فریم_لس"] = ttk.Combobox(inputs_frame, values=list(قیمت_انواع_پروفیل.keys()), state="readonly", justify='right', width=25)
        self.inputs["نوع_پروفیل_فریم_لس"].set("فریم لس قالب جدید")
        self.inputs["نوع_پروفیل_فریم_لس"].grid(row=row_idx, column=1, sticky=tk.EW, padx=5)
        row_idx += 1

        # رنگ آلومینیوم
        ttk.Label(inputs_frame, text="رنگ آلومینیوم:").grid(row=row_idx, column=0, sticky=tk.W)
        self.inputs["رنگ_آلومینیوم"] = ttk.Combobox(inputs_frame, values=["سفید", "خام", "آنادایز", "رنگی"], state="readonly", justify='right', width=25)
        self.inputs["رنگ_آلومینیوم"].set("سفید")
        self.inputs["رنگ_آلومینیوم"].grid(row=row_idx, column=1, sticky=tk.EW, padx=5)
        row_idx += 1
        
        # جنس درب
        ttk.Label(inputs_frame, text="جنس درب:").grid(row=row_idx, column=0, sticky=tk.W)
        self.inputs["جنس_درب"] = ttk.Combobox(inputs_frame, values=list(قیمت_جنس_درب.keys()), state="readonly", justify='right', width=25)
        self.inputs["جنس_درب"].set("پلای وود")
        self.inputs["جنس_درب"].grid(row=row_idx, column=1, sticky=tk.EW, padx=5)
        row_idx += 1

        # شرایط رنگ
        ttk.Label(inputs_frame, text="شرایط رنگ:").grid(row=row_idx, column=0, sticky=tk.W)
        شرایط_رنگ_options = sorted(list(set(k[0] for k in قیمت_خدمات_رنگ.keys())))
        self.inputs["شرایط_رنگ"] = ttk.Combobox(inputs_frame, values=شرایط_رنگ_options, state="readonly", justify='right', width=25)
        self.inputs["شرایط_رنگ"].set("رنگ نهایی")
        self.inputs["شرایط_رنگ"].grid(row=row_idx, column=1, sticky=tk.EW, padx=5)
        row_idx += 1

        # رند رنگ
        ttk.Label(inputs_frame, text="رند رنگ:").grid(row=row_idx, column=0, sticky=tk.W)
        رند_رنگ_options = sorted(list(set(k[1] for k in قیمت_خدمات_رنگ.keys())))
        self.inputs["رند_رنگ"] = ttk.Combobox(inputs_frame, values=رند_رنگ_options, state="readonly", justify='right', width=25)
        self.inputs["رند_رنگ"].set("خارجی")
        self.inputs["رند_رنگ"].grid(row=row_idx, column=1, sticky=tk.EW, padx=5)

        # --- Selections Frame for final sum components ---
        selections_frame = ttk.LabelFrame(main_frame, text="انتخاب و درصد سهم مولفه ها در جمع نهایی", padding="10 10 10 10")
        selections_frame.pack(fill=tk.X, pady=5)
        
        self.selection_vars = {}
        self.selection_percentage_vars = {}
        
        selection_items_ordered = [
            ("درب_خام", "درب خام"), 
            ("درب_با_رنگ_کامل", "درب با رنگ کامل"),
            ("فریم", "فریم"),
            ("یراق_کامل", "یراق کامل"),
            ("رنگ_کاری", "رنگ کاری (مجزا)")
        ]

        # Configure columns for selections_frame: Checkbox | Entry | % | Spacer | Checkbox | Entry | %
        selections_frame.columnconfigure(0, weight=0) # Checkbox
        selections_frame.columnconfigure(1, weight=0) # Entry
        selections_frame.columnconfigure(2, weight=0) # % label
        selections_frame.columnconfigure(3, weight=1) # Spacer
        selections_frame.columnconfigure(4, weight=0) # Checkbox
        selections_frame.columnconfigure(5, weight=0) # Entry
        selections_frame.columnconfigure(6, weight=0) # % label

        for i, (key, display_text) in enumerate(selection_items_ordered):
            if key in selections: 
                # Checkbox Variable and Widget
                var = tk.BooleanVar(value=selections[key][0])
                var.trace_add("write", lambda *args, k=key: self.perform_calculation_on_event()) 
                self.selection_vars[key] = var
                chk = ttk.Checkbutton(selections_frame, text=display_text, variable=var)
                
                # Percentage Variable and Entry Widget
                percentage_var = tk.StringVar(value="100" if var.get() else "") # Default 100 if checked
                percentage_var.trace_add("write", lambda *args, k=key: self.perform_calculation_on_event())
                self.selection_percentage_vars[key] = percentage_var
                entry = ttk.Entry(selections_frame, textvariable=percentage_var, width=5, justify='right')
                percent_label = ttk.Label(selections_frame, text="%")

                # Layout: 2 items per row
                current_row = i // 2
                if i % 2 == 0: # First item in row (left side)
                    chk.grid(row=current_row, column=0, sticky=tk.W, padx=(0,2), pady=2)
                    entry.grid(row=current_row, column=1, sticky=tk.W, padx=0, pady=2)
                    percent_label.grid(row=current_row, column=2, sticky=tk.W, padx=(0,10), pady=2)
                else: # Second item in row (right side)
                    chk.grid(row=current_row, column=4, sticky=tk.W, padx=(0,2), pady=2)
                    entry.grid(row=current_row, column=5, sticky=tk.W, padx=0, pady=2)
                    percent_label.grid(row=current_row, column=6, sticky=tk.W, padx=(0,0), pady=2)
            else:
                print(f"Warning: Key '{key}' not found in global selections dictionary.")

        # --- Control Buttons Frame ---
        control_buttons_frame = ttk.Frame(main_frame)
        control_buttons_frame.pack(fill=tk.X, pady=5) 

        self.calculate_button = ttk.Button(control_buttons_frame, text="محاسبه قیمت", command=self.perform_calculation)
        self.calculate_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0,2))

        self.settings_button = ttk.Button(control_buttons_frame, text="تنظیمات قیمت پایه", command=self.open_settings_window)
        self.settings_button.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(2,0))
        
        # Results Frame
        results_frame = ttk.LabelFrame(main_frame, text="نتایج محاسبات", padding="10 10 10 10")
        results_frame.pack(fill=tk.BOTH, expand=True, pady=5) 
        results_frame.columnconfigure(1, weight=1)

        self.result_labels = {}
        # The displayed text now reflects the *contribution* after percentage
        result_keys_to_display = {
            "D14_هزینه_درب_خام_یک_درب": "سهم نهایی درب خام:",
            "G14_هزینه_فریم_کل": "هزینه پایه فریم (کل):", 
            "N14_هزینه_کل_رنگ_کاری_یک_درب": "هزینه پایه رنگ کاری (یک درب):", 
            "E11_یراق_کامل": "سهم نهایی یراق کامل:", 
            "D11_فریم": "سهم نهایی فریم:", 
            "C11_درب_با_رنگ_کامل": "سهم نهایی درب با رنگ کامل:",
            "رنگ_کاری_contrib": "سهم نهایی رنگ کاری (مجزا):",
            "total_cost": "هزینه کل نهایی:"
        }
        
        res_row_idx = 0
        for key, text in result_keys_to_display.items():
            ttk.Label(results_frame, text=text).grid(row=res_row_idx, column=0, sticky=tk.W)
            self.result_labels[key] = ttk.Label(results_frame, text="0", anchor="e", justify='right')
            self.result_labels[key].grid(row=res_row_idx, column=1, sticky=tk.EW, padx=5)
            res_row_idx+=1
        
        self.perform_calculation() # Initial calculation

    def open_settings_window(self):
        SettingsWindow(self.master, self.perform_calculation) 

    # Debounce or throttle this if performance becomes an issue with many traces
    def perform_calculation_on_event(self, *args):
        # This lambda ensures that perform_calculation is called without extra event args
        self.master.after_idle(self.perform_calculation)

    def perform_calculation(self):
        try:
            component_markup_rules = {}
            for key, chk_var in self.selection_vars.items():
                is_selected = chk_var.get()
                percentage_str = self.selection_percentage_vars[key].get()
                contrib_decimal = 1.0 # Default to 100% for contribution if selected and no percentage

                if is_selected:
                    if percentage_str.strip():
                        try:
                            percentage = float(percentage_str)
                            if not (0 <= percentage <= 100):
                                messagebox.showerror("خطای درصد", f"درصد برای '{display_text_for_key(key)}' باید بین 0 و 100 باشد.", parent=self.master)
                                return
                            contrib_decimal = percentage / 100.0
                        except ValueError:
                            messagebox.showerror("خطای درصد", f"مقدار درصد نامعتبر برای '{display_text_for_key(key)}'.", parent=self.master)
                            return
                    # If percentage_str is empty and checkbox is selected, contrib_decimal remains 1.0 (100%)
                else: # Not selected
                    contrib_decimal = 0.0 # No contribution if not selected, percentage effectively 0
                
                component_markup_rules[key] = (is_selected, contrib_decimal)
            
            input_values = {}
            input_values["عرض_درب"] = int(self.inputs["عرض_درب"].get())
            input_values["ارتفاع_درب"] = int(self.inputs["ارتفاع_درب"].get())
            input_values["نوع_پروفیل_فریم_لس"] = self.inputs["نوع_پروفیل_فریم_لس"].get()
            input_values["رنگ_آلومینیوم"] = self.inputs["رنگ_آلومینیوم"].get()
            input_values["جنس_درب"] = self.inputs["جنس_درب"].get()
            input_values["شرایط_رنگ"] = self.inputs["شرایط_رنگ"].get()
            input_values["رند_رنگ"] = self.inputs["رند_رنگ"].get()

            results = calculate_costs(input_values, component_markup_rules)

            for key, label_widget in self.result_labels.items():
                if key in results:
                    value_to_display = results[key]
                    if isinstance(value_to_display, (int, float)):
                        if key == "E14_وزن_پروفیل_واحد": 
                             label_widget.config(text=f"{value_to_display:,.1f}") 
                        else:
                             label_widget.config(text=f"{value_to_display:,.0f} ریال")
                    else: 
                        label_widget.config(text=str(value_to_display))
                elif key in self.result_labels: 
                    self.result_labels[key].config(text="0 ریال")

        except ValueError as e:
            messagebox.showerror("خطای ورودی", str(e), parent=self.master)
        except Exception as e:
            # print(traceback.format_exc()) # For debugging unexpected errors
            messagebox.showerror("خطا در محاسبه", f"یک خطای پیش بینی نشده رخ داد: {str(e)} ({type(e).__name__})", parent=self.master)

# Helper function to get display text for error messages (optional)
def display_text_for_key(key):
    mapping = {
        "درب_خام": "درب خام", 
        "درب_با_رنگ_کامل": "درب با رنگ کامل",
        "فریم": "فریم",
        "یراق_کامل": "یراق کامل",
        "رنگ_کاری": "رنگ کاری (مجزا)"
    }
    return mapping.get(key, key) # Return key itself if not found

if __name__ == '__main__':
    root = tk.Tk()
    app = PriceCalculatorApp(root)
    root.mainloop() 