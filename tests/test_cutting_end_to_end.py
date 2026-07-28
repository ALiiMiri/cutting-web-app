import os
import sqlite3
import tempfile
import unittest

import database
from cutting_calculator import calculate_cutting_plan
from test_inventory_application import SCHEMA


class CuttingEndToEndTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.old_db_name = database.DB_NAME
        database.DB_NAME = self.db_path

        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO projects(id,customer_name,project_code) VALUES (901,'پروژه تست قطعات برش‌خورده','T901')"
        )
        conn.execute(
            "INSERT INTO profile_types(id,name,min_waste,weight_per_meter) VALUES (1,'پروفیل تست',10,1.5)"
        )
        conn.execute(
            "INSERT INTO inventory_items(profile_type_id,color_id,quantity) VALUES (1,2,2)"
        )
        conn.executemany(
            "INSERT INTO inventory_pieces(id,profile_type_id,color_id,length) VALUES (?,1,2,?)",
            [(101, 120), (102, 250)],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_NAME = self.old_db_name
        os.unlink(self.db_path)

    def test_project_uses_offcuts_and_does_not_deduct_complete_stock(self):
        doors = [
            {
                "id": 1,
                "width": 100,
                "height": 100,
                "quantity": 1,
                "noe_profile": "پروفیل تست",
                "rang": "مشکی",
            }
        ]
        profiles = [
            {
                "id": 1,
                "name": "پروفیل تست",
                "min_waste": 10,
                "weight_per_meter": 1.5,
                "default_length": 600,
            }
        ]
        available = database.get_available_inventory_pieces("پروفیل تست", "مشکی")
        plan = calculate_cutting_plan(
            doors,
            profiles,
            available_pieces_by_profile={"پروفیل تست ⟡ مشکی": available},
            use_inventory=True,
            prefer_inventory_pieces=True,
            optimization_strategy="minimize_waste",
        )

        self.assertEqual(plan["total_bins"], 2)
        self.assertTrue(all(item["from_inventory_piece"] for item in plan["bins"]))
        self.assertEqual(plan["used_inventory_pieces"]["پروفیل تست ⟡ مشکی"], [101, 102])
        self.assertEqual(plan["bins"][0]["pieces"], [100.0])
        self.assertEqual(plan["bins"][1]["pieces"], [100.0, 100.0])
        self.assertAlmostEqual(plan["stats"]["total_kerf_length"], 1.5)

        result = database.apply_cutting_plan_inventory_transaction(
            901,
            {"customer_name": "پروژه تست قطعات برش‌خورده", "project_code": "T901"},
            plan["inventory_application_data"],
            plan["used_inventory_pieces"],
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["application"]["total_stock_deducted"], 0)
        self.assertEqual(result["application"]["pieces_consumed"], 2)
        self.assertEqual(result["application"]["pieces_returned"], 2)

        conn = sqlite3.connect(self.db_path)
        stock = conn.execute(
            "SELECT quantity FROM inventory_items WHERE profile_type_id=1 AND color_id=2"
        ).fetchone()[0]
        remaining_lengths = [
            row[0]
            for row in conn.execute(
                "SELECT length FROM inventory_pieces WHERE profile_type_id=1 AND color_id=2 ORDER BY length"
            ).fetchall()
        ]
        conn.close()

        self.assertEqual(stock, 2)
        self.assertEqual(remaining_lengths, [19.5, 49.0])

    def test_registered_five_meter_profile_controls_plan_and_stock_deduction(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM inventory_pieces")
        conn.execute("UPDATE profile_types SET default_length = 500 WHERE id = 1")
        conn.commit()
        conn.close()

        doors = [
            {
                "id": 3,
                "width": 100,
                "height": 240,
                "quantity": 1,
                "noe_profile": "پروفیل تست",
                "rang": "مشکی",
                "kolaft": "سه طرفه",
            }
        ]
        profiles = [
            {
                "id": 1,
                "name": "پروفیل تست",
                "min_waste": 10,
                "weight_per_meter": 1.5,
                "default_length": 500,
            }
        ]
        plan = calculate_cutting_plan(doors, profiles)

        self.assertEqual(plan["total_bins"], 2)
        self.assertTrue(all(item["initial_length"] == 500 for item in plan["bins"]))

        result = database.apply_cutting_plan_inventory_transaction(
            901,
            {"customer_name": "پروژه تست قطعات برش‌خورده", "project_code": "T901"},
            plan["inventory_application_data"],
            plan["used_inventory_pieces"],
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["application"]["total_stock_deducted"], 2)

    def test_two_sided_frame_does_not_cut_or_deduct_an_upper_member(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM inventory_pieces")
        conn.execute(
            "INSERT INTO inventory_pieces(id,profile_type_id,color_id,length) VALUES (201,1,2,201)"
        )
        conn.commit()
        conn.close()

        doors = [
            {
                "id": 2,
                "width": 100,
                "height": 100,
                "quantity": 1,
                "noe_profile": "پروفیل تست",
                "rang": "مشکی",
                "kolaft": "دو طرفه",
            }
        ]
        profiles = [
            {
                "id": 1,
                "name": "پروفیل تست",
                "min_waste": 10,
                "weight_per_meter": 1.5,
                "default_length": 600,
            }
        ]
        available = database.get_available_inventory_pieces("پروفیل تست", "مشکی")
        plan = calculate_cutting_plan(
            doors,
            profiles,
            available_pieces_by_profile={"پروفیل تست ⟡ مشکی": available},
            use_inventory=True,
            prefer_inventory_pieces=True,
            optimization_strategy="minimize_waste",
        )

        self.assertEqual(plan["total_bins"], 1)
        self.assertEqual(plan["bins"][0]["pieces"], [100.0, 100.0])
        self.assertAlmostEqual(plan["stats"]["total_kerf_length"], 1.0)

        result = database.apply_cutting_plan_inventory_transaction(
            901,
            {"customer_name": "پروژه تست قطعات برش‌خورده", "project_code": "T901"},
            plan["inventory_application_data"],
            plan["used_inventory_pieces"],
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["application"]["total_stock_deducted"], 0)
        self.assertEqual(result["application"]["pieces_consumed"], 1)
        self.assertEqual(result["application"]["pieces_returned"], 0)

        conn = sqlite3.connect(self.db_path)
        stock = conn.execute(
            "SELECT quantity FROM inventory_items WHERE profile_type_id=1 AND color_id=2"
        ).fetchone()[0]
        remaining_pieces = conn.execute(
            "SELECT COUNT(*) FROM inventory_pieces WHERE profile_type_id=1 AND color_id=2"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(stock, 2)
        self.assertEqual(remaining_pieces, 0)


if __name__ == "__main__":
    unittest.main()
