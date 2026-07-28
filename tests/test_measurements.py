import unittest

from measurements import (
    centimeters_to_measurement_unit,
    dimension_to_centimeters,
    format_measurement_value,
    measurement_unit_labels,
    normalize_measurement_unit,
)


class MeasurementConversionTests(unittest.TestCase):
    def test_centimeters_are_stored_without_change(self):
        self.assertEqual(dimension_to_centimeters("110.5", "cm"), 110.5)

    def test_millimeters_are_converted_to_centimeters(self):
        self.assertEqual(dimension_to_centimeters("1105", "mm"), 110.5)

    def test_missing_unit_keeps_legacy_centimeter_behavior(self):
        self.assertEqual(dimension_to_centimeters("110", None), 110.0)

    def test_unknown_unit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "واحد اندازه‌گیری"):
            normalize_measurement_unit("meter")

    def test_canonical_centimeters_are_exported_in_project_unit(self):
        self.assertEqual(centimeters_to_measurement_unit(110.5, "cm"), 110.5)
        self.assertEqual(centimeters_to_measurement_unit(110.5, "mm"), 1105.0)

    def test_export_labels_match_project_unit(self):
        self.assertEqual(measurement_unit_labels("cm"), {"short": "cm", "fa": "سانتی‌متر"})
        self.assertEqual(measurement_unit_labels("mm"), {"short": "mm", "fa": "میلی‌متر"})

    def test_whole_display_values_do_not_have_a_trailing_decimal(self):
        self.assertEqual(format_measurement_value(1000.0), "1000")
        self.assertEqual(format_measurement_value(2300.0), "2300")

    def test_meaningful_decimal_values_are_preserved(self):
        self.assertEqual(format_measurement_value(1000.5), "1000.5")


if __name__ == "__main__":
    unittest.main()
