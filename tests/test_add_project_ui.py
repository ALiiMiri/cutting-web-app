import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class AddProjectUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "templates" / "add_project.html").read_text(
            encoding="utf-8"
        )
        cls.app_source = (ROOT / "cutting_web_app.py").read_text(encoding="utf-8")

    def test_page_uses_order_language_and_two_step_flow(self):
        self.assertIn("ایجاد سفارش جدید", self.template)
        self.assertIn("اطلاعات سفارش", self.template)
        self.assertIn("افزودن درب‌ها", self.template)

    def test_measurement_unit_is_a_visible_two_choice_control(self):
        self.assertIn('data-unit="cm"', self.template)
        self.assertIn('data-unit="mm"', self.template)
        self.assertIn('name="measurement_unit"', self.template)

    def test_form_has_csrf_and_inline_validation(self):
        self.assertIn('name="csrf_token"', self.template)
        self.assertIn('id="customer-error"', self.template)
        self.assertIn("@csrf_protected\n@staff_or_admin_required\ndef add_project_route", self.app_source)

    def test_success_redirects_to_new_order_details(self):
        self.assertIn(
            'return redirect(url_for("view_project", project_id=new_id))',
            self.app_source,
        )

    def test_sidebar_step_numbers_are_centered_and_readable(self):
        self.assertIn(".side-item .side-icon", self.template)
        self.assertIn("place-items:center", self.template)
        self.assertIn("font-size:16px", self.template)


if __name__ == "__main__":
    unittest.main()
