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
        self.assertIn(
            '<span class="unit-badge">{{ measurement_unit_label }}</span>',
            self.template,
        )
        self.assertIn(
            '<span class="dimension-unit">{{ measurement_unit_label }}</span>',
            self.template,
        )
        self.assertIn("measurement_unit_label=unit_labels[\"fa\"]", self.app_source)

    def test_row_menu_escapes_the_scroll_container(self):
        self.assertIn("document.body.appendChild(menu)", self.template)
        self.assertIn("position:fixed", self.template)

    def test_edit_and_delete_share_one_menu_card(self):
        self.assertIn('class="row-menu"', self.template)
        self.assertIn("ویرایش درب", self.template)
        self.assertIn("حذف درب", self.template)

    def test_delete_uses_custom_confirmation_dialog(self):
        self.assertIn('id="delete-modal"', self.template)
        self.assertIn('id="confirm-delete"', self.template)
        self.assertNotIn("if(!confirm(", self.template)


if __name__ == "__main__":
    unittest.main()
