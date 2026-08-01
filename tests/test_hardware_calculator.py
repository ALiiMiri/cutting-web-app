import unittest

from hardware_calculator import (
    bracket_count_for_height,
    calculate_project_hardware,
    handle_requires_cylinder,
    hinge_count_for_height,
)


def door(**overrides):
    data = {
        "id": 1,
        "location": "اتاق مدیریت",
        "width": 100,
        "height": 270,
        "quantity": 2,
        "vaziat": "درب دار",
        "lola": "OTLAV",
        "ghofl": "STV",
        "dastgire": "ایزدو",
    }
    data.update(overrides)
    return data


class HardwareCalculatorTests(unittest.TestCase):
    def test_hinge_thresholds_match_price_formula(self):
        expected = {
            180: 2,
            181: 3,
            240: 3,
            241: 4,
            270: 4,
            271: 5,
            320: 5,
            321: 6,
            400: 6,
        }
        for height, count in expected.items():
            with self.subTest(height=height):
                self.assertEqual(hinge_count_for_height(height), count)

    def test_brackets_use_both_sides_at_sixty_centimeter_intervals(self):
        self.assertEqual(bracket_count_for_height(270), 10)
        self.assertEqual(bracket_count_for_height(60), 2)
        self.assertEqual(bracket_count_for_height(61), 4)

    def test_complete_project_row_calculates_all_hardware(self):
        report = calculate_project_hardware([door()])
        totals = {(item["group"], item["model"]): item["quantity"] for item in report["summary"]}

        self.assertEqual(report["included_door_count"], 2)
        self.assertEqual(report["warnings"], [])
        self.assertEqual(totals[("لولا", "OTLAV")], 8)
        self.assertEqual(totals[("قفل", "STV")], 2)
        self.assertEqual(totals[("دستگیره", "ایزدو")], 2)
        self.assertEqual(totals[("سیلندر", "سیلندر استاندارد")], 2)
        self.assertEqual(totals[("اقلام نصب", "براکت نصب")], 20)

    def test_special_handle_families_do_not_add_cylinders(self):
        for model in ("مونتیس", "مورتایس مشکی", "دستگیره تک روزه", "تک‌رزت"):
            with self.subTest(model=model):
                self.assertFalse(handle_requires_cylinder(model))
                report = calculate_project_hardware([door(dastgire=model, quantity=1)])
                cylinder_rows = [item for item in report["summary"] if item["group"] == "سیلندر"]
                self.assertEqual(cylinder_rows, [])

    def test_missing_values_warn_but_explicit_without_values_do_not(self):
        missing = calculate_project_hardware([door(lola="", ghofl="", dastgire="")])
        self.assertEqual({item["field"] for item in missing["warnings"]}, {"لولا", "قفل", "دستگیره"})

        explicit = calculate_project_hardware(
            [door(lola="بدون لولا", ghofl="بدون قفل", dastgire="بدون دستگیره")]
        )
        self.assertEqual(explicit["warnings"], [])
        self.assertEqual(
            {(item["group"], item["model"]) for item in explicit["summary"]},
            {("اقلام نصب", "براکت نصب")},
        )

    def test_rows_marked_without_door_are_excluded(self):
        report = calculate_project_hardware([door(vaziat="بدون درب", quantity=5)])
        self.assertEqual(report["included_door_count"], 0)
        self.assertEqual(report["excluded_row_count"], 1)
        self.assertEqual(report["summary"], [])

    def test_structured_hardware_uses_exact_brands_and_rosette_has_no_cylinder(self):
        report = calculate_project_hardware(
            [
                door(
                    quantity=2,
                    hardware_configured=True,
                    hinge_brand="کاله",
                    hinge_color="مشکی",
                    hinge_count=3,
                    has_handle=True,
                    handle_type="single_rosette",
                    handle_brand="ایران",
                    handle_model="R210",
                    handle_color="طلایی",
                    lock_source="own_brand",
                    lock_brand=None,
                    lock_model=None,
                    cylinder_brand=None,
                    cylinder_model=None,
                )
            ]
        )
        totals = {
            (item["group"], item["model"]): item["quantity"]
            for item in report["summary"]
        }
        self.assertEqual(totals[("لولا", "کاله — مشکی")], 6)
        self.assertEqual(totals[("قفل", "قفل مخصوص ایران")], 2)
        self.assertFalse(any(group == "سیلندر" for group, _ in totals))


if __name__ == "__main__":
    unittest.main()
