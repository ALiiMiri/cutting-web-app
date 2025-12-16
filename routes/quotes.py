# Quotes Blueprint - routes/quotes.py
# This module contains all quote/pricing-related routes

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
from collections import defaultdict
import json
import traceback

from database import (
    save_quote_db,
    get_all_saved_quotes_db,
    delete_quote_db,
    delete_multiple_quotes_db,
)

# Create Blueprint
quotes_bp = Blueprint('quotes', __name__)


@quotes_bp.route("/save_quote", methods=["POST"])
def save_quote():
    """ذخیره یک قیمت‌دهی جدید"""
    if request.method == "POST":
        conn = None
        try:
            if not request.is_json:
                flash("درخواست باید با فرمت JSON باشد.", "danger")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, error="درخواست باید با فرمت JSON باشد"), 400
                return redirect(url_for('price_calculator'))

            data = request.get_json()
            if not data:
                flash("اطلاعات ارسال نشده یا فرمت نامعتبر است.", "danger")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, error="اطلاعات ارسال نشده یا فرمت نامعتبر است."), 400
                return redirect(url_for('price_calculator'))

            print(f"DEBUG: Data received in /save_quote: {data}")

            customer_name = data.get("customer_name")
            customer_mobile = data.get("customer_mobile")
            input_width = data.get("input_width")
            input_height = data.get("input_height")
            profile_type = data.get("profile_type")
            aluminum_color = data.get("aluminum_color")
            door_material = data.get("door_material")
            paint_condition = data.get("paint_condition")
            paint_brand = data.get("paint_brand")
            selections_details = data.get("selections_details")
            final_price = data.get("final_price")
            shamsi_order_date = data.get("shamsi_date", "")

            if not all([customer_name, input_width, input_height, profile_type, selections_details, final_price]):
                error_message = "اطلاعات ضروری برای ذخیره قیمت ناقص است."
                flash(error_message, "danger")
                if customer_name or customer_mobile:
                    session['preserved_customer_info_data'] = {'customer_name': customer_name, 'customer_mobile': customer_mobile}
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, error=error_message, preserved_info={'customer_name': customer_name, 'customer_mobile': customer_mobile}), 400
                return redirect(url_for('price_calculator'))

            data_to_save = {
                'customer_name': customer_name,
                'customer_mobile': customer_mobile,
                'input_width': input_width,
                'input_height': input_height,
                'profile_type': profile_type,
                'aluminum_color': aluminum_color,
                'door_material': door_material,
                'paint_condition': paint_condition,
                'paint_brand': paint_brand,
                'selections_details': selections_details,
                'final_price': final_price,
                'shamsi_order_date': shamsi_order_date
            }
            
            if save_quote_db(data_to_save):
                success_message = "قیمت‌دهی با موفقیت ذخیره شد."
                flash(success_message, "success")
                session['preserved_customer_info_data'] = {'customer_name': customer_name, 'customer_mobile': customer_mobile}
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=True, message=success_message, preserved_info={'customer_name': customer_name, 'customer_mobile': customer_mobile})
                return redirect(url_for('price_calculator'))
            else:
                raise Exception("خطا در عملیات ذخیره در پایگاه داده")

        except Exception as e:
            print(f"Error in /save_quote: {e}")
            traceback.print_exc()
            error_message = f"خطا در ذخیره اطلاعات: {str(e)}"
            flash(error_message, "danger")

            preserved_customer_name = ""
            preserved_customer_mobile = ""
            if request.is_json:
                data_for_flash = request.get_json() or {}
                preserved_customer_name = data_for_flash.get("customer_name", "")
                preserved_customer_mobile = data_for_flash.get("customer_mobile", "")
            
            if preserved_customer_name or preserved_customer_mobile:
                session['preserved_customer_info_data'] = {'customer_name': preserved_customer_name, 'customer_mobile': preserved_customer_mobile}

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, error=error_message, preserved_info={'customer_name': preserved_customer_name, 'customer_mobile': preserved_customer_mobile}), 500
            return redirect(url_for('price_calculator'))
    
    flash("درخواست نامعتبر برای ذخیره قیمت.", "warning")
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(success=False, error="درخواست نامعتبر برای ذخیره قیمت."), 405
    return redirect(url_for('price_calculator'))


@quotes_bp.route("/saved_quotes")
def saved_quotes():
    """نمایش قیمت‌دهی‌های ذخیره شده با قابلیت گروه‌بندی"""
    try:
        quotes = get_all_saved_quotes_db()
        
        grouped_quotes = defaultdict(list)
        for quote_data in quotes:
            quote_dict = {
                'id': quote_data['id'],
                'customer_name': quote_data['customer_name'] if quote_data['customer_name'] else "بدون نام مشتری",
                'customer_mobile': quote_data['customer_mobile'],
                'input_width': quote_data['input_width'],
                'input_height': quote_data['input_height'],
                'profile_type': quote_data['profile_type'],
                'aluminum_color': quote_data['aluminum_color'],
                'door_material': quote_data['door_material'],
                'paint_condition': quote_data['paint_condition'],
                'paint_brand': quote_data['paint_brand'],
                'final_calculated_price': quote_data['final_calculated_price'],
                'shamsi_order_date': quote_data['shamsi_order_date'] if quote_data['shamsi_order_date'] else "تاریخ نامشخص"
            }

            timestamp_val = quote_data['timestamp']
            if isinstance(timestamp_val, str):
                try:
                    timestamp_val = datetime.strptime(timestamp_val.split('.')[0], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    try:
                        timestamp_val = datetime.strptime(timestamp_val, '%Y-%m-%d %H:%M')
                    except ValueError:
                        print(f"WARNING: Could not parse timestamp string: {quote_data['timestamp']}")
                        timestamp_val = None
            elif timestamp_val is None:
                timestamp_val = None
            quote_dict['timestamp'] = timestamp_val
            
            try:
                if quote_data['selections_details']:
                    if isinstance(quote_data['selections_details'], str):
                        quote_dict['selections_details'] = json.loads(quote_data['selections_details'])
                    else:
                        quote_dict['selections_details'] = quote_data['selections_details']
                else:
                    quote_dict['selections_details'] = {}
            except json.JSONDecodeError as json_err:
                print(f"ERROR: JSONDecodeError for quote id {quote_dict['id']}: {json_err}")
                quote_dict['selections_details'] = {}
            except Exception as e_json:
                print(f"ERROR: Unknown error parsing selections_details: {e_json}")
                quote_dict['selections_details'] = {}
                
            customer_key = quote_dict['customer_name']
            grouped_quotes[customer_key].append(quote_dict)
        
        all_quotes_for_js = [quote for customer_quotes in grouped_quotes.values() for quote in customer_quotes]
        quotes_json_list = []
        for quote_data_dict in all_quotes_for_js:
            temp_quote = quote_data_dict.copy()
            if temp_quote.get('timestamp') and not isinstance(temp_quote['timestamp'], str):
                try:
                    temp_quote['timestamp'] = temp_quote['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                except AttributeError:
                    temp_quote['timestamp'] = str(temp_quote['timestamp'])
            quotes_json_list.append(temp_quote)
        all_quotes_json = json.dumps(quotes_json_list)

        return render_template("saved_quotes.html", grouped_quotes=grouped_quotes, all_quotes_json=all_quotes_json)
        
    except Exception as e:
        print(f"!!!!!! ERROR in saved_quotes route: {e}") 
        traceback.print_exc()
        flash("خطایی در بارگذاری قیمت‌دهی‌های ذخیره شده رخ داد.", "error")
        return redirect(url_for("index"))


@quotes_bp.route("/delete_quote/<int:quote_id>", methods=["POST"])
def delete_quote(quote_id):
    """پاک کردن یک قیمت‌دهی ذخیره شده"""
    try:
        if delete_quote_db(quote_id):
            flash("قیمت‌دهی با موفقیت پاک شد.", "success")
        else:
            flash("قیمت‌دهی مورد نظر یافت نشد یا خطا در حذف.", "error")
        return redirect(url_for("quotes.saved_quotes"))
        
    except Exception as e:
        print(f"خطا در پاک کردن قیمت‌دهی: {e}")
        traceback.print_exc()
        flash("خطایی در پاک کردن قیمت‌دهی رخ داد.", "error")
        return redirect(url_for("quotes.saved_quotes"))


@quotes_bp.route("/delete_multiple_quotes", methods=["POST"])
def delete_multiple_quotes():
    """پاک کردن چندین قیمت‌دهی انتخاب شده"""
    try:
        selected_ids = request.form.getlist('selected_quotes')
        
        if not selected_ids:
            flash("هیچ قیمت‌دهی‌ای انتخاب نشده است.", "warning")
            return redirect(url_for("quotes.saved_quotes"))

        deleted_count = delete_multiple_quotes_db(selected_ids)
        
        if deleted_count > 0:
            flash(f"{deleted_count} قیمت‌دهی با موفقیت پاک شدند.", "success")
        else:
            flash("هیچ قیمت‌دهی‌ای پاک نشد.", "warning")
            
        return redirect(url_for("quotes.saved_quotes"))
        
    except Exception as e:
        print(f"خطا در پاک کردن قیمت‌دهی‌های انتخاب شده: {e}")
        traceback.print_exc()
        flash("خطایی در پاک کردن قیمت‌دهی‌ها رخ داد.", "error")
        return redirect(url_for("quotes.saved_quotes"))
