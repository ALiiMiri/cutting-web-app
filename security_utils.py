"""Small security helpers shared by authentication and administration forms."""

import hmac
import secrets
from functools import wraps

from flask import abort, request, session


MANAGER_ONLY_ENDPOINTS = {
    'delete_project_route', 'inventory_settings_route', 'add_profile_type_route',
    'edit_profile_type_route', 'delete_profile_type_route',
    'add_column_route', 'update_column_display', 'delete_column_route',
    'manage_custom_columns', 'settings_combos', 'add_column_option_api',
    'delete_column_option_api', 'edit_column_option_api', 'price_calculator_settings',
    'delete_quote', 'delete_multiple_quotes', 'quotes.delete_quote',
    'quotes.delete_multiple_quotes', 'inventory.update_waste',
    'inventory.add_profile_type_route', 'inventory.edit_profile_type_route',
    'inventory.delete_profile_type_route', 'inventory.reactivate_profile',
    'inventory.corrections', 'inventory.correct_stock', 'inventory.correct_color',
    'inventory.correct_piece_add', 'inventory.correct_piece_remove',
    'inventory.settings', 'inventory.undo_operation', 'apply_cutting_plan',
}

PROJECT_EDIT_ENDPOINTS = {
    'update_project_route', 'add_door_form', 'add_door_buffer',
    'finish_adding_doors', 'quick_add_door', 'update_door',
    'set_door_color', 'delete_door',
    'apply_cutting_plan', 'batch_edit_form', 'apply_batch_edit',
    'save_batch_edit_checkbox_state_project', 'batch_remove_column_value_route',
    'settings_columns', 'project_column_toggle', 'project_column_add_existing',
    'project_column_remove',
    'project_column_create', 'project_column_option_add',
    'project_column_option_edit', 'project_column_option_delete',
}


def access_denial_message(role, method, endpoint, path=''):
    """Return a user-facing reason when a role must not perform the request."""
    if role in {'staff', 'read_only'} and path.startswith('/inventory'):
        return 'بخش انبار فقط در اختیار مدیر و مدیر سیستم است.'
    if (
        role == 'read_only'
        and method in {'POST', 'PUT', 'PATCH', 'DELETE'}
        and endpoint != 'save_orders_view_preference'
    ):
        return 'حساب شما فقط اجازه مشاهده دارد و نمی‌تواند اطلاعات را تغییر دهد.'
    if endpoint in MANAGER_ONLY_ENDPOINTS and role not in {'admin', 'manager'}:
        return 'این بخش فقط در اختیار مدیر یا مدیر سیستم است.'
    return None


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def valid_csrf_token():
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("csrf_token")
    return bool(supplied and expected and hmac.compare_digest(str(supplied), str(expected)))


def csrf_protected(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not valid_csrf_token():
            abort(400, description="درخواست معتبر نیست. لطفاً صفحه را تازه‌سازی و دوباره تلاش کنید.")
        return view(*args, **kwargs)

    return wrapped
