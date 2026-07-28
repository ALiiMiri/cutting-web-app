import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
CSS = ROOT / "static" / "css"


class TypographyFoundationTests(unittest.TestCase):
    DIRECT_TEMPLATES = (
        "index.html",
        "add_project.html",
        "project_details.html",
        "project_treeview.html",
        "login.html",
        "change_password.html",
        "admin/users.html",
        "inventory_dashboard.html",
        "pdf_table_template.html",
    )
    ORDER_TYPOGRAPHY_FILES = (
        CSS / "orders_dashboard.css",
        CSS / "cutting_orders.css",
        CSS / "project_column_settings.css",
        TEMPLATES / "add_project.html",
        TEMPLATES / "project_details.html",
        TEMPLATES / "project_treeview.html",
        TEMPLATES / "batch_edit.html",
        TEMPLATES / "_app_header.html",
    )

    def test_official_local_variable_font_is_present(self):
        font_path = ROOT / "static" / "fonts" / "Vazirmatn-Variable.woff2"
        self.assertTrue(font_path.is_file())
        self.assertEqual(font_path.read_bytes()[:4], b"wOF2")
        self.assertGreater(font_path.stat().st_size, 100_000)
        self.assertTrue((font_path.parent / "Vazirmatn-OFL.txt").is_file())

    def test_design_system_uses_only_the_local_font(self):
        design_system = (CSS / "design-system.css").read_text(encoding="utf-8")
        self.assertIn("../fonts/Vazirmatn-Variable.woff2", design_system)
        self.assertIn('--font-family-base: "Vazirmatn"', design_system)
        self.assertIn("font-weight: 400 700", design_system)
        self.assertIn("--text-base: 14px", design_system)
        self.assertIn("--text-sm: 13px", design_system)
        self.assertIn("--text-xs: 12px", design_system)
        self.assertIn(":focus-visible", design_system)
        self.assertNotIn("http://", design_system)
        self.assertNotIn("https://", design_system)

    def test_shared_responsive_rules_cover_mobile_forms_tables_and_touch_targets(self):
        design_system = (CSS / "design-system.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 768px)", design_system)
        self.assertIn("grid-template-columns: 1fr", design_system)
        self.assertIn("overflow-x: auto", design_system)
        self.assertIn("min-height: 40px", design_system)

        dashboard = (CSS / "orders_dashboard.css").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:900px)", dashboard)
        self.assertIn("@media(max-width:580px)", dashboard)
        self.assertIn(".orders-table{min-width:760px}", dashboard)
        self.assertIn(".tab{height:40px", dashboard)

        admin_users = (TEMPLATES / "admin/users.html").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 768px)", admin_users)
        self.assertGreaterEqual(admin_users.count('class="table-responsive"'), 2)
        self.assertIn("min-height: 40px", admin_users)

        legacy_style = (CSS / "style.css").read_text(encoding="utf-8")
        self.assertRegex(
            legacy_style,
            r"\.btn\s*\{[^}]*min-height:\s*40px",
        )

    def test_treeview_column_setup_has_no_jquery_dependency(self):
        treeview = (TEMPLATES / "project_treeview.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("$(", treeview)
        self.assertNotIn("$.ajax", treeview)
        self.assertIn("document.addEventListener('DOMContentLoaded'", treeview)

    def test_key_pages_load_the_shared_design_system(self):
        for template_name in self.DIRECT_TEMPLATES:
            with self.subTest(template=template_name):
                template = (TEMPLATES / template_name).read_text(encoding="utf-8")
                self.assertIn("css/design-system.css", template)

        imports = {
            CSS / "style.css",
            CSS / "cutting_orders.css",
            CSS / "project_column_settings.css",
        }
        for css_path in imports:
            with self.subTest(stylesheet=css_path.name):
                self.assertIn(
                    "design-system.css", css_path.read_text(encoding="utf-8")
                )

    def test_active_templates_do_not_reference_removed_font_files_or_font_cdn(self):
        excluded = {
            "new_project_details.html",
            "pdf_template.orig.html",
            "pdf_template_optimized.html",
            "project_details.html.backup2.html",
        }
        legacy_pattern = re.compile(
            r"Vazir\.ttf|fonts/Vazir\.(?:woff2|woff|eot|ttf)|"
            r"cdn\.jsdelivr\.net/gh/rastikerdar",
            re.IGNORECASE,
        )
        for template_path in TEMPLATES.rglob("*.html"):
            if template_path.name in excluded:
                continue
            with self.subTest(template=template_path.relative_to(TEMPLATES)):
                template = template_path.read_text(encoding="utf-8")
                self.assertIsNone(legacy_pattern.search(template))

    def test_order_interfaces_have_no_8_to_11_pixel_text_or_800_900_weights(self):
        tiny_text = re.compile(r"font-size:\s*(?:8|9|10|11)px")
        heavy_weight = re.compile(r"font-weight:\s*(?:800|900)")
        for file_path in self.ORDER_TYPOGRAPHY_FILES:
            with self.subTest(file=file_path.relative_to(ROOT)):
                source = file_path.read_text(encoding="utf-8")
                self.assertIsNone(tiny_text.search(source))
                self.assertIsNone(heavy_weight.search(source))


if __name__ == "__main__":
    unittest.main()
