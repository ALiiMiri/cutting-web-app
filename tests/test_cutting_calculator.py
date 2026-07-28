import unittest

from cutting_calculator import CuttingPlanError, calculate_cutting_plan


def profile(name, weight, min_waste=70):
    return {
        "id": 1,
        "name": name,
        "weight_per_meter": weight,
        "min_waste": min_waste,
        "default_length": 600,
    }


def door(
    profile_name,
    width=100,
    height=270,
    quantity=1,
    door_id=1,
    color=None,
    frame_type=None,
):
    return {
        "id": door_id,
        "width": width,
        "height": height,
        "quantity": quantity,
        "noe_profile": profile_name,
        "rang": color,
        "kolaft": frame_type,
    }


class CuttingCalculatorTests(unittest.TestCase):
    def test_profile_uses_its_registered_stock_length(self):
        custom_profile = profile("پروفیل", 1.2)
        custom_profile["default_length"] = 500

        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=240, frame_type="سه طرفه")],
            [custom_profile],
        )

        self.assertEqual(plan["total_bins"], 2)
        self.assertTrue(
            all(source["initial_length"] == 500 for source in plan["bins"])
        )
        self.assertEqual(plan["profile_summaries"][0]["default_length"], 500)
        self.assertEqual(
            plan["inventory_application_data"]["پروفیل"]["default_length"], 500
        )

    def test_three_sided_frame_cuts_two_verticals_and_one_top(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=200, quantity=2, frame_type="سه طرفه")],
            [profile("پروفیل", 1.2)],
        )

        pieces = [piece for source in plan["bins"] for piece in source["pieces"]]
        self.assertEqual(sorted(pieces), [100.0, 100.0, 200.0, 200.0, 200.0, 200.0])
        self.assertEqual(sum(source["cut_count"] for source in plan["bins"]), 6)

        details = [
            piece for source in plan["bins"] for piece in source["piece_details"]
        ]
        top = [piece for piece in details if piece["member_type"] == "horizontal_top"]
        verticals = [piece for piece in details if piece["member_type"].startswith("vertical_")]
        self.assertEqual(len(top), 2)
        self.assertTrue(all("دو سر فارسی‌بُر" in piece["cut_instruction"] for piece in top))
        self.assertTrue(all("پایین: صاف ۹۰ درجه" in piece["cut_instruction"] for piece in verticals))

    def test_two_sided_frame_omits_top_member_and_its_blade_loss(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=200, quantity=2, frame_type="دو طرفه")],
            [profile("پروفیل", 1.2)],
        )

        pieces = [piece for source in plan["bins"] for piece in source["pieces"]]
        self.assertEqual(pieces, [200.0, 200.0, 200.0, 200.0])
        self.assertEqual(sum(source["cut_count"] for source in plan["bins"]), 4)
        self.assertAlmostEqual(plan["stats"]["total_kerf_length"], 2.0)
        details = [
            piece for source in plan["bins"] for piece in source["piece_details"]
        ]
        self.assertTrue(
            all(
                piece["cut_instruction"]
                == "بالا: صاف ۹۰ درجه؛ پایین: صاف ۹۰ درجه"
                for piece in details
            )
        )
        self.assertFalse(any(piece["member_type"] == "horizontal_top" for piece in details))

    def test_fingerprint_changes_when_registered_stock_length_changes(self):
        first_profile = profile("پروفیل", 1.2)
        second_profile = profile("پروفیل", 1.2)
        second_profile["default_length"] = 580

        first = calculate_cutting_plan([door("پروفیل")], [first_profile])
        second = calculate_cutting_plan([door("پروفیل")], [second_profile])

        self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_missing_or_retired_frame_type_keeps_three_sided_calculation(self):
        for frame_type in (None, "", "یک طرفه", "بدون کلافت"):
            with self.subTest(frame_type=frame_type):
                plan = calculate_cutting_plan(
                    [door("پروفیل", width=100, height=200, frame_type=frame_type)],
                    [profile("پروفیل", 1.2)],
                )
                pieces = [piece for source in plan["bins"] for piece in source["pieces"]]
                self.assertEqual(sorted(pieces), [100.0, 200.0, 200.0])

    def test_same_profile_is_planned_separately_for_each_color(self):
        plan = calculate_cutting_plan(
            [
                door("پروفیل", door_id=1, color="مشکی"),
                door("پروفیل", door_id=2, color="سفید"),
            ],
            [profile("پروفیل", 1.2)],
        )

        self.assertEqual(len(plan["profile_summaries"]), 2)
        self.assertEqual(
            {row["color_name"] for row in plan["profile_summaries"]},
            {"مشکی", "سفید"},
        )
        self.assertEqual(plan["total_bins"], 4)

    def test_uses_each_profiles_own_weight(self):
        plan = calculate_cutting_plan(
            [door("سبک", door_id=1), door("سنگین", door_id=2)],
            [profile("سبک", 1.2), profile("سنگین", 1.9)],
        )

        summaries = {item["profile_type"]: item for item in plan["profile_summaries"]}
        self.assertAlmostEqual(summaries["سبک"]["discarded_length"], 59)
        self.assertAlmostEqual(summaries["سبک"]["discarded_weight"], 0.708)
        self.assertAlmostEqual(summaries["سنگین"]["discarded_length"], 59)
        self.assertAlmostEqual(summaries["سنگین"]["discarded_weight"], 1.121)
        self.assertAlmostEqual(plan["stats"]["discarded_weight"], 1.829)

    def test_single_profile_uses_registered_weight(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=270)],
            [profile("پروفیل", 1.25)],
        )
        self.assertAlmostEqual(plan["stats"]["discarded_weight"], 0.7375)
        self.assertAlmostEqual(plan["stats"]["reusable_weight"], 6.24375)

    def test_inventory_piece_remaining_uses_same_profile_weight(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=140)],
            [profile("پروفیل", 1.5, min_waste=50)],
            available_pieces_by_profile={"پروفیل": [{"id": 9, "length": 300}]},
            use_inventory=True,
            prefer_inventory_pieces=True,
        )

        inventory_bin = next(item for item in plan["bins"] if item["from_inventory_piece"])
        self.assertEqual(inventory_bin["inventory_piece_id"], 9)
        self.assertAlmostEqual(inventory_bin["remaining"], 19)
        self.assertAlmostEqual(inventory_bin["remaining_weight"], 0.285)
        self.assertIn(9, plan["used_inventory_pieces"]["پروفیل"])

    def test_opened_source_is_filled_before_another_inventory_piece_is_opened(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=140)],
            [profile("پروفیل", 1.5, min_waste=10)],
            available_pieces_by_profile={
                "پروفیل": [
                    {"id": 1, "length": 300},
                    {"id": 2, "length": 300},
                    {"id": 3, "length": 150},
                ]
            },
            use_inventory=True,
            prefer_inventory_pieces=True,
        )

        inventory_bins = [item for item in plan["bins"] if item["from_inventory_piece"]]
        self.assertEqual(len(inventory_bins), 2)
        self.assertEqual(plan["used_inventory_pieces"]["پروفیل"], [3, 1])
        self.assertEqual(inventory_bins[1]["pieces"], [140.0, 100.0])

    def test_smallest_sufficient_inventory_piece_is_selected(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=140)],
            [profile("پروفیل", 1.5)],
            available_pieces_by_profile={
                "پروفیل": [{"id": 10, "length": 400}, {"id": 11, "length": 160}]
            },
            use_inventory=True,
            prefer_inventory_pieces=True,
        )

        self.assertEqual(plan["used_inventory_pieces"]["پروفیل"][0], 11)
        first_inventory_bin = next(item for item in plan["bins"] if item["from_inventory_piece"])
        self.assertEqual(first_inventory_bin["initial_length"], 160)

    def test_inventory_combination_is_used_without_opening_a_complete_profile(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=100)],
            [profile("پروفیل", 1.5)],
            available_pieces_by_profile={
                "پروفیل": [{"id": 20, "length": 110}, {"id": 21, "length": 210}]
            },
            use_inventory=True,
            prefer_inventory_pieces=True,
        )

        self.assertEqual(plan["total_bins"], 2)
        self.assertTrue(all(item["from_inventory_piece"] for item in plan["bins"]))
        self.assertEqual(set(plan["used_inventory_pieces"]["پروفیل"]), {20, 21})

    def test_minimize_pieces_can_choose_one_complete_profile_over_three_offcuts(self):
        pieces = [{"id": number, "length": 110} for number in (31, 32, 33)]
        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=100)],
            [profile("پروفیل", 1.5)],
            available_pieces_by_profile={"پروفیل": pieces},
            use_inventory=True,
            prefer_inventory_pieces=False,
            optimization_strategy="minimize_pieces",
        )

        self.assertEqual(plan["optimization_strategy"], "minimize_pieces")
        self.assertEqual(plan["total_bins"], 1)
        self.assertFalse(plan["bins"][0]["from_inventory_piece"])
        self.assertNotIn("پروفیل", plan["used_inventory_pieces"])

    def test_waste_and_new_profile_strategies_use_available_offcuts(self):
        pieces = [{"id": number, "length": 110} for number in (41, 42, 43)]
        for strategy in ("minimize_waste", "minimize_new_profiles"):
            with self.subTest(strategy=strategy):
                plan = calculate_cutting_plan(
                    [door("پروفیل", width=100, height=100)],
                    [profile("پروفیل", 1.5)],
                    available_pieces_by_profile={"پروفیل": pieces},
                    use_inventory=True,
                    prefer_inventory_pieces=False,
                    optimization_strategy=strategy,
                )
                self.assertEqual(plan["optimization_strategy"], strategy)
                self.assertEqual(plan["total_bins"], 3)
                self.assertTrue(all(item["from_inventory_piece"] for item in plan["bins"]))

    def test_remaining_equal_to_min_waste_is_reusable(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=100, height=270)],
            [profile("پروفیل", 1.2, min_waste=59)],
        )
        boundary_bin = next(item for item in plan["bins"] if item["remaining"] == 59)
        self.assertEqual(boundary_bin["remaining_type"], "reusable")
        self.assertEqual(plan["stats"]["discarded_count"], 0)

    def test_zero_remaining_has_no_weight_or_waste(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=298.5, height=150)],
            [profile("پروفیل", 1.9)],
        )
        self.assertEqual(plan["total_bins"], 1)
        self.assertEqual(plan["bins"][0]["remaining_type"], "none")
        self.assertAlmostEqual(plan["stats"]["total_remaining_weight"], 0)

    def test_five_millimeter_blade_loss_is_applied_to_every_cut(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", width=298.5, height=150)],
            [profile("پروفیل", 1.9)],
        )

        self.assertAlmostEqual(plan["blade_width"], 0.5)
        self.assertEqual(plan["bins"][0]["cut_count"], 3)
        self.assertAlmostEqual(plan["bins"][0]["kerf_loss"], 1.5)
        self.assertAlmostEqual(plan["stats"]["total_kerf_length"], 1.5)

    def test_invalid_row_is_reported_but_valid_rows_are_calculated(self):
        plan = calculate_cutting_plan(
            [door("پروفیل", door_id=1), door("پروفیل", width=0, door_id=2)],
            [profile("پروفیل", 1.2)],
        )
        self.assertEqual(plan["valid_rows"], 1)
        self.assertEqual(plan["invalid_rows"], [2])

    def test_missing_profile_stops_calculation(self):
        with self.assertRaisesRegex(CuttingPlanError, "در انبار تعریف نشده"):
            calculate_cutting_plan([door("ناموجود")], [profile("پروفیل", 1.2)])

    def test_invalid_profile_weight_stops_calculation(self):
        with self.assertRaisesRegex(CuttingPlanError, "وزن هر متر"):
            calculate_cutting_plan([door("پروفیل")], [profile("پروفیل", 0)])

    def test_piece_longer_than_stock_stops_calculation(self):
        with self.assertRaisesRegex(CuttingPlanError, "امکان برش قطعه"):
            calculate_cutting_plan(
                [door("پروفیل", height=601)],
                [profile("پروفیل", 1.2)],
            )


if __name__ == "__main__":
    unittest.main()
