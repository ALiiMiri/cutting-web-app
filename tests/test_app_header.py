import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


class AppHeaderTests(unittest.TestCase):
    ORDER_TEMPLATES = (
        "index.html",
        "add_project.html",
        "project_details.html",
        "project_treeview.html",
        "add_door.html",
        "project_column_settings.html",
        "batch_edit.html",
        "cutting_result.html",
        "hardware_report.html",
        "factory_requirements.html",
        "project_assignment_history.html",
        "column_settings.html",
        "settings_combos.html",
    )

    LEGACY_APP_TEMPLATES = (
        "add_profile_type.html",
        "edit_profile_type.html",
        "admin/users.html",
        "backup_manager.html",
        "change_password.html",
        "inventory_corrections.html",
        "inventory_dashboard.html",
        "inventory_logs.html",
        "inventory_settings.html",
        "inventory_waste.html",
        "price_calculator.html",
        "price_calculator_settings.html",
        "profile_inventory_details.html",
        "profile_types.html",
        "saved_quotes.html",
    )

    def test_all_order_pages_use_the_shared_header(self):
        include = "{% include '_app_header.html' %}"
        for template_name in self.ORDER_TEMPLATES:
            with self.subTest(template=template_name):
                template = (TEMPLATES / template_name).read_text(encoding="utf-8")
                self.assertIn(include, template)
                self.assertIn("with-app-header", template)
                self.assertNotIn("_order_home_shortcut.html", template)

    def test_all_remaining_authenticated_pages_use_the_shared_shell(self):
        include = "{% include '_app_header.html' %}"
        for template_name in self.LEGACY_APP_TEMPLATES:
            with self.subTest(template=template_name):
                template = (TEMPLATES / template_name).read_text(encoding="utf-8")
                self.assertIn(include, template)
                self.assertIn("with-app-header", template)
                self.assertIn("ui-legacy", template)

    def test_login_uses_the_shared_palette_without_the_private_header(self):
        template = (TEMPLATES / "login.html").read_text(encoding="utf-8")
        self.assertIn("unified-ui.css", template)
        self.assertIn('class="ui-auth"', template)
        self.assertNotIn("{% include '_app_header.html' %}", template)

    def test_unified_stylesheet_uses_the_approved_navy_palette(self):
        stylesheet = (ROOT / "static" / "css" / "unified-ui.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("body.with-app-header", stylesheet)
        self.assertIn("var(--color-navy)", stylesheet)
        self.assertIn("var(--color-canvas)", stylesheet)

    def test_brand_and_user_identity_return_to_orders_dashboard(self):
        header = (TEMPLATES / "_app_header.html").read_text(encoding="utf-8")
        self.assertIn('class="app-header-brand"', header)
        self.assertIn('class="app-user-home"', header)
        self.assertEqual(header.count("href=\"{{ url_for('index') }}\""), 2)
        self.assertIn("مدیریت سفارش درب", header)

    def test_shared_header_keeps_account_and_main_navigation(self):
        header = (TEMPLATES / "_app_header.html").read_text(encoding="utf-8")
        self.assertIn("مدیریت کاربران", header)
        self.assertIn("مدیریت انبار", header)
        self.assertIn("تغییر رمز عبور", header)
        self.assertIn("خروج", header)
        self.assertIn("position:sticky", header)

    def test_page_specific_back_buttons_are_preserved(self):
        expected = {
            "project_column_settings.html": "بازگشت به جدول درب‌ها",
            "batch_edit.html": "بازگشت به جدول و تغییر انتخاب",
            "hardware_report.html": "بازگشت به پروژه",
        }
        for template_name, label in expected.items():
            with self.subTest(template=template_name):
                template = (TEMPLATES / template_name).read_text(encoding="utf-8")
                self.assertIn(label, template)


if __name__ == "__main__":
    unittest.main()
