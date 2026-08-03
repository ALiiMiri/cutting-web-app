import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProjectDetailsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "templates" / "project_details.html").read_text(
            encoding="utf-8"
        )
        cls.app_source = (ROOT / "cutting_web_app.py").read_text(encoding="utf-8")

    def test_selected_measurement_unit_is_shown_with_dimensions(self):
        self.assertIn("{{ measurement_unit_label }}", self.template)
        self.assertIn("measurement_unit_label=unit_labels[\"fa\"]", self.app_source)

    def test_code_and_locations_are_visible_in_the_project_table(self):
        self.assertIn("کد درب", self.template)
        self.assertIn("محل‌های نصب", self.template)
        self.assertIn("door.installation_locations", self.template)

    def test_delete_uses_custom_confirmation_dialog(self):
        self.assertIn('id="delete-modal"', self.template)
        self.assertIn('id="confirm-delete"', self.template)
        self.assertNotIn("if(!confirm(", self.template)

    def test_quantity_is_entered_per_installation_location(self):
        self.assertNotIn('id="door-quantity"', self.template)
        self.assertIn('class="control location-quantity"', self.template)
        self.assertIn("تعداد کل این کد", self.template)

    def test_installer_report_is_linked(self):
        self.assertIn("installer_report", self.template)


if __name__ == "__main__":
    unittest.main()
