import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ProjectTreeviewUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "templates" / "project_treeview.html").read_text(
            encoding="utf-8"
        )
        cls.app_source = (ROOT / "cutting_web_app.py").read_text(encoding="utf-8")

    def test_select_all_is_limited_to_visible_rows(self):
        self.assertIn("const visibleRows", self.template)
        self.assertIn("row.style.display !== 'none'", self.template)

    def test_hidden_rows_are_removed_from_batch_selection(self):
        self.assertIn("checkbox.checked = false", self.template)
        self.assertIn("row.classList.remove('selected-row')", self.template)

    def test_filter_options_follow_visible_custom_columns(self):
        self.assertIn("{% if column.key in visible_columns %}", self.template)
        self.assertIn('<option value="{{ column.key }}">', self.template)

    def test_total_uses_real_door_quantity(self):
        self.assertIn("{{ total_door_quantity }}", self.template)
        self.assertIn("total_door_quantity = sum", self.app_source)

    def test_unused_customer_number_and_row_coloring_are_removed(self):
        self.assertNotIn("شماره محک", self.template)
        self.assertNotIn("setRowColor", self.template)
        self.assertNotIn("context-menu", self.template)
        self.assertNotIn("/set_color", self.app_source)

    def test_force_refresh_parameter_is_removed_before_page_reload(self):
        self.assertIn(
            "if (urlParams.has('t') || forceRefresh || refreshColumns)",
            self.template,
        )
        cleanup_position = self.template.index("window.history.replaceState")
        reload_position = self.template.index("location.reload()")
        self.assertLess(cleanup_position, reload_position)


if __name__ == "__main__":
    unittest.main()
