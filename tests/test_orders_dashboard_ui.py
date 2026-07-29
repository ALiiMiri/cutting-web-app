import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class OrdersDashboardUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "templates" / "index.html").read_text(
            encoding="utf-8"
        )
        cls.app_source = (ROOT / "cutting_web_app.py").read_text(encoding="utf-8")
        cls.security_source = (ROOT / "security_utils.py").read_text(
            encoding="utf-8"
        )

    def test_both_views_are_available_and_personally_persisted(self):
        self.assertIn('data-view-option="table"', self.template)
        self.assertIn('data-view-option="cards"', self.template)
        self.assertIn("/preferences/orders-view", self.template)
        self.assertIn("set_orders_view_preference(current_user.id", self.app_source)

    def test_quick_scopes_are_connected_to_server_filters(self):
        self.assertIn('data-scope="mine"', self.template)
        self.assertIn('data-scope="unassigned"', self.template)
        self.assertIn("scope=scope", self.app_source)
        self.assertIn("get_project_dashboard_counts", self.app_source)

    def test_customer_filter_uses_bounded_recent_suggestions(self):
        self.assertIn('list="recent-customers"', self.template)
        self.assertIn("get_recent_customers()", self.app_source)
        self.assertNotIn("get_unique_customers()", self.app_source)

    def test_project_permissions_are_derived_from_loaded_assignments(self):
        self.assertIn("user_can_edit_project_assignment(", self.app_source)
        self.assertNotIn(
            "project['can_edit'] = user_can_edit_project(",
            self.app_source,
        )

    def test_dangerous_actions_live_in_row_menu_and_use_custom_modal(self):
        self.assertIn('class="row-menu"', self.template)
        self.assertIn('id="delete-modal"', self.template)
        self.assertNotIn("confirm(`", self.template)

    def test_mutating_order_forms_are_csrf_protected(self):
        self.assertIn(
            '@app.route("/project/<int:project_id>/update", methods=["POST"])\n@csrf_protected',
            self.app_source,
        )
        self.assertIn(
            '@manager_or_admin_required\n@csrf_protected\ndef delete_project_route',
            self.app_source,
        )

    def test_read_only_user_can_save_only_visual_preference(self):
        self.assertIn("endpoint != 'save_orders_view_preference'", self.security_source)

    def test_create_order_button_keeps_readable_text_on_hover(self):
        css = (ROOT / "static" / "css" / "orders_dashboard.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".add-order:hover,.add-order:focus", css)
        self.assertIn("color:#fff!important", css)
        self.assertNotIn('class="add-order open-order"', self.template)


if __name__ == "__main__":
    unittest.main()
