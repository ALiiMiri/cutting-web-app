import importlib
import os
import re
import sqlite3
import tempfile
import unittest
from unittest import mock

import database
import auth_utils
from cutting_order_excel import create_cutting_order_workbook
from cutting_orders import (
    CuttingOrderError,
    archive_project_safely,
    cancel_cutting_order,
    confirm_bar_cut,
    confirm_bars_cut,
    create_cutting_order,
    get_cutting_order,
    get_project_cutting_blockers,
    reserve_cutting_order,
    revise_cutting_order,
    send_cutting_order,
)


SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,username TEXT,role TEXT,is_active INTEGER,
    must_change_password INTEGER DEFAULT 0,session_version INTEGER DEFAULT 0
);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,customer_name TEXT,order_ref TEXT,date_shamsi TEXT,
    project_code TEXT,measurement_unit TEXT,created_by_user_id INTEGER,
    assigned_to_user_id INTEGER
);
CREATE TABLE doors (
    id INTEGER PRIMARY KEY,project_id INTEGER,location TEXT,width REAL,height REAL,
    quantity INTEGER,direction TEXT,row_color_tag TEXT
);
CREATE TABLE custom_columns (
    id INTEGER PRIMARY KEY,column_name TEXT,display_name TEXT,column_type TEXT,
    is_active INTEGER
);
CREATE TABLE door_custom_values (
    door_id INTEGER,column_id INTEGER,value TEXT,PRIMARY KEY(door_id,column_id)
);
CREATE TABLE profile_types (
    id INTEGER PRIMARY KEY,name TEXT,default_length REAL,weight_per_meter REAL,
    min_waste REAL,is_active INTEGER DEFAULT 1
);
CREATE TABLE profile_colors (
    id INTEGER PRIMARY KEY,name TEXT,hex_code TEXT,is_active INTEGER DEFAULT 1
);
CREATE TABLE inventory_items (
    id INTEGER PRIMARY KEY,profile_type_id INTEGER,color_id INTEGER,quantity INTEGER,
    last_updated TEXT,UNIQUE(profile_type_id,color_id)
);
CREATE TABLE inventory_pieces (
    id INTEGER PRIMARY KEY,profile_type_id INTEGER,color_id INTEGER,length REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE cutting_settings (
    id INTEGER PRIMARY KEY,name TEXT UNIQUE,value TEXT,description TEXT
);
CREATE TABLE inventory_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,operation_type TEXT,project_id INTEGER,
    actor_user_id INTEGER,description TEXT,status TEXT,is_reversible INTEGER,
    created_at TEXT,reversed_at TEXT,reversed_by_user_id INTEGER,
    reversal_reason TEXT,reverses_operation_id INTEGER,reversal_operation_id INTEGER
);
CREATE TABLE inventory_operation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,operation_id INTEGER,sequence_no INTEGER,
    action_type TEXT,profile_type_id INTEGER,profile_name TEXT,quantity_delta INTEGER,
    before_quantity INTEGER,after_quantity INTEGER,piece_id INTEGER,length REAL,
    color_id INTEGER,color_name_snapshot TEXT
);
CREATE TABLE inventory_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,profile_type_id INTEGER,color_id INTEGER,
    color_name_snapshot TEXT,change_type TEXT,quantity INTEGER,length REAL,
    piece_id INTEGER,project_id INTEGER,description TEXT,timestamp TEXT,
    operation_id INTEGER
);
CREATE TABLE inventory_waste_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,cutting_operation_id INTEGER NOT NULL,
    project_id INTEGER,profile_type_id INTEGER,color_id INTEGER,
    profile_name_snapshot TEXT,color_name_snapshot TEXT,length_cm REAL,
    weight_per_meter_snapshot REAL,calculated_weight_kg REAL,actual_weight_kg REAL,
    source_type TEXT,source_piece_id INTEGER,status TEXT,created_at TEXT,updated_at TEXT
);
"""


class CuttingOrderWorkflowTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO users(id,username,role,is_active) VALUES (1,'manager','manager',1)"
        )
        conn.execute(
            """
            INSERT INTO projects
                (id,customer_name,order_ref,date_shamsi,project_code,
                 measurement_unit,created_by_user_id,assigned_to_user_id)
            VALUES (1,'مشتری','A-1','1405/01/01','1001','cm',1,1)
            """
        )
        conn.execute(
            """
            INSERT INTO doors
                (id,project_id,location,width,height,quantity,direction,row_color_tag)
            VALUES (1,1,'اتاق',100,140,1,'چپ','white')
            """
        )
        conn.executemany(
            "INSERT INTO custom_columns(id,column_name,display_name,column_type,is_active) VALUES (?,?,?,?,1)",
            [
                (1, "noe_profile", "نوع پروفیل", "dropdown"),
                (2, "rang", "رنگ", "dropdown"),
                (3, "kolaft", "نوع چهارچوب", "dropdown"),
            ],
        )
        conn.executemany(
            "INSERT INTO door_custom_values(door_id,column_id,value) VALUES (1,?,?)",
            [(1, "پروفیل تست"), (2, "مشکی"), (3, "سه طرفه")],
        )
        conn.execute(
            """
            INSERT INTO profile_types
                (id,name,default_length,weight_per_meter,min_waste,is_active)
            VALUES (1,'پروفیل تست',600,1.2,50,1)
            """
        )
        conn.execute(
            "INSERT INTO profile_colors(id,name,hex_code,is_active) VALUES (1,'مشکی','#000',1)"
        )
        conn.execute(
            "INSERT INTO inventory_items(id,profile_type_id,color_id,quantity) VALUES (1,1,1,10)"
        )
        conn.execute(
            "INSERT INTO inventory_pieces(id,profile_type_id,color_id,length) VALUES (1,1,1,300)"
        )
        conn.executemany(
            "INSERT INTO cutting_settings(name,value) VALUES (?,?)",
            [
                ("use_inventory_for_cutting", "true"),
                ("prefer_inventory_pieces", "true"),
                ("inventory_optimization_strategy", "minimize_waste"),
            ],
        )
        migration = importlib.import_module("migrations.025_cutting_orders")
        migration.apply(conn)
        conn.commit()
        conn.close()
        self.previous_db = database.DB_NAME
        database.DB_NAME = self.db_path

    def tearDown(self):
        database.DB_NAME = self.previous_db
        os.unlink(self.db_path)

    def scalar(self, sql, args=()):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, args).fetchone()[0]
        finally:
            conn.close()

    def add_project(self, project_id, order_ref, *, color="مشکی"):
        conn = sqlite3.connect(self.db_path)
        door_id = project_id
        conn.execute(
            """
            INSERT INTO projects
                (id,customer_name,order_ref,date_shamsi,project_code,
                 measurement_unit,created_by_user_id,assigned_to_user_id)
            VALUES (?,?,?,?,?,'cm',1,1)
            """,
            (
                project_id,
                f"مشتری {project_id}",
                order_ref,
                "1405/01/01",
                f"10{project_id:02d}",
            ),
        )
        conn.execute(
            """
            INSERT INTO doors
                (id,project_id,location,width,height,quantity,direction,row_color_tag)
            VALUES (?,?,?,100,140,1,'چپ','white')
            """,
            (door_id, project_id, f"اتاق {project_id}"),
        )
        conn.executemany(
            "INSERT INTO door_custom_values(door_id,column_id,value) VALUES (?,?,?)",
            [
                (door_id, 1, "پروفیل تست"),
                (door_id, 2, color),
                (door_id, 3, "سه طرفه"),
            ],
        )
        conn.commit()
        conn.close()

    def test_grouped_workflow_is_atomic_incremental_and_idempotent(self):
        before_stock = self.scalar("SELECT quantity FROM inventory_items")
        first = create_cutting_order([1], 1)
        with self.assertRaises(CuttingOrderError):
            create_cutting_order([1], 1)
        self.assertEqual(self.scalar("SELECT quantity FROM inventory_items"), before_stock)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM inventory_reservations"), 0)

        self.assertTrue(reserve_cutting_order(first, 1))
        self.assertEqual(self.scalar("SELECT quantity FROM inventory_items"), before_stock)

        self.assertTrue(send_cutting_order(first, 1))
        order = get_cutting_order(first)
        stock_bar = next(
            bar for bar in order["bars"] if bar["source_type"] == "new_stock"
        )
        self.assertTrue(
            confirm_bar_cut(
                first, stock_bar["id"], 1, stock_bar["planned_remaining"]
            )
        )
        self.assertEqual(
            self.scalar("SELECT quantity FROM inventory_items"), before_stock - 1
        )
        self.assertFalse(
            confirm_bar_cut(
                first, stock_bar["id"], 1, stock_bar["planned_remaining"]
            )
        )
        self.assertEqual(
            self.scalar("SELECT quantity FROM inventory_items"), before_stock - 1
        )

        self.assertTrue(cancel_cutting_order(first, 1, "تغییر برنامه تولید"))
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM inventory_reservations WHERE order_id=? AND status='active'",
                (first,),
            ),
            0,
        )
        final = get_cutting_order(first)
        self.assertEqual(final["status"], "completed")
        self.assertEqual(
            sum(bar["status"] == "cut" for bar in final["bars"]), 1
        )
        self.assertGreater(
            create_cutting_order_workbook(final).getbuffer().nbytes, 5000
        )

    def test_cancelled_uncut_order_can_be_calculated_again(self):
        first = create_cutting_order([1], 1)
        self.assertTrue(cancel_cutting_order(first, 1, "لغو محاسبه آزمایشی"))
        second = create_cutting_order([1], 1)
        self.assertNotEqual(first, second)

    def test_legacy_applied_cutting_plan_blocks_new_order(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE inventory_cutting_applications (
                project_id INTEGER PRIMARY KEY,
                applied_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO inventory_cutting_applications(project_id,applied_at) VALUES (1,'1405-01-01')"
        )
        conn.commit()
        conn.close()

        blockers = get_project_cutting_blockers([1])
        self.assertEqual(blockers[1]["source"], "applied_cutting_plan")
        with self.assertRaises(CuttingOrderError):
            create_cutting_order([1], 1)

    def test_revision_releases_uncut_bars_and_does_not_repeat_cut_members(self):
        first = create_cutting_order([1], 1)
        reserve_cutting_order(first, 1)
        send_cutting_order(first, 1)
        original = get_cutting_order(first)
        cut_bar = original["bars"][0]
        confirm_bar_cut(first, cut_bar["id"], 1, cut_bar["planned_remaining"])

        second = revise_cutting_order(first, 1, "ابعاد سفارش تغییر کرد")
        previous = get_cutting_order(first)
        revised = get_cutting_order(second)
        self.assertEqual(revised["parent_order_id"], first)
        self.assertEqual(revised["version"], 2)
        self.assertEqual(previous["status"], "completed")
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM inventory_reservations WHERE order_id=? AND status='active'",
                (first,),
            ),
            0,
        )
        original_piece_count = sum(len(bar["pieces"]) for bar in original["bars"])
        revised_piece_count = sum(len(bar["pieces"]) for bar in revised["bars"])
        self.assertEqual(
            revised_piece_count, original_piece_count - len(cut_bar["pieces"])
        )

    def test_three_selected_projects_can_share_compatible_bars(self):
        self.add_project(2, "A-2")
        self.add_project(3, "A-3")
        before_stock = self.scalar("SELECT quantity FROM inventory_items")
        before_pieces = self.scalar("SELECT COUNT(*) FROM inventory_pieces")
        order = get_cutting_order(create_cutting_order([1, 2, 3], 1))
        self.assertEqual(len(order["projects"]), 3)
        self.assertEqual(self.scalar("SELECT quantity FROM inventory_items"), before_stock)
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM inventory_pieces"), before_pieces
        )
        self.assertTrue(
            any(
                len({piece["project_id"] for piece in bar["pieces"]}) > 1
                for bar in order["bars"]
            )
        )

    def test_four_of_ten_stock_bars_are_reserved_without_physical_deduction(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM inventory_pieces")
        conn.execute(
            "UPDATE cutting_settings SET value='false' WHERE name='use_inventory_for_cutting'"
        )
        conn.execute("UPDATE doors SET height=590,quantity=2 WHERE id=1")
        conn.execute(
            "UPDATE door_custom_values SET value='دو طرفه' WHERE door_id=1 AND column_id=3"
        )
        conn.commit()
        conn.close()
        order_id = create_cutting_order([1], 1)
        order = get_cutting_order(order_id)
        self.assertEqual(len(order["bars"]), 4)
        reserve_cutting_order(order_id, 1)
        summary = get_cutting_order(order_id)["inventory_summary"][0]
        self.assertEqual(summary["physical_stock"], 10)
        self.assertEqual(summary["reserved_stock"], 4)
        self.assertEqual(summary["available_stock"], 6)
        cancel_cutting_order(order_id, 1, "لغو پیش از شروع برش")
        self.assertEqual(self.scalar("SELECT quantity FROM inventory_items"), 10)

    def test_remainder_and_waste_are_created_only_after_cut_confirmation(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE profile_types SET min_waste=70 WHERE id=1")
        conn.execute(
            "UPDATE cutting_settings SET value='false' WHERE name='use_inventory_for_cutting'"
        )
        conn.execute("UPDATE doors SET quantity=2 WHERE id=1")
        conn.commit()
        conn.close()
        order_id = create_cutting_order([1], 1)
        reserve_cutting_order(order_id, 1)
        send_cutting_order(order_id, 1)
        order = get_cutting_order(order_id)
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM inventory_pieces WHERE source_cutting_order_id=?",
                (order_id,),
            ),
            0,
        )
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM inventory_waste_items WHERE cutting_operation_id IN "
                "(SELECT id FROM inventory_operations WHERE operation_type='cutting_order_bar')"
            ),
            0,
        )
        confirm_bar_cut(order_id, order["bars"][0]["id"], 1, 80)
        confirm_bar_cut(order_id, order["bars"][1]["id"], 1, 40)
        updated = get_cutting_order(order_id)
        self.assertIsNotNone(updated["bars"][0]["returned_piece_id"])
        self.assertIsNotNone(updated["bars"][1]["waste_item_id"])

    def test_failure_during_bar_confirmation_rolls_back_every_change(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE cutting_settings SET value='false' WHERE name='use_inventory_for_cutting'"
        )
        conn.commit()
        conn.close()
        order_id = create_cutting_order([1], 1)
        reserve_cutting_order(order_id, 1)
        send_cutting_order(order_id, 1)
        bar = get_cutting_order(order_id)["bars"][0]
        before = self.scalar("SELECT quantity FROM inventory_items")
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TRIGGER fail_cut_event BEFORE INSERT ON cutting_order_events
            WHEN NEW.event_type='inventory_consumed'
            BEGIN SELECT RAISE(ABORT,'forced cut failure'); END
            """
        )
        conn.commit()
        conn.close()
        with self.assertRaises(sqlite3.IntegrityError):
            confirm_bar_cut(order_id, bar["id"], 1, bar["planned_remaining"])
        self.assertEqual(self.scalar("SELECT quantity FROM inventory_items"), before)
        self.assertEqual(
            self.scalar(
                "SELECT status FROM cutting_order_bars WHERE id=?", (bar["id"],)
            ),
            "reserved",
        )
        self.assertEqual(
            self.scalar(
                "SELECT status FROM inventory_reservations WHERE bar_id=?",
                (bar["id"],),
            ),
            "active",
        )

    def test_confirming_every_bar_completes_order_and_consumes_each_source_once(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE cutting_settings SET value='false' WHERE name='use_inventory_for_cutting'"
        )
        conn.execute("UPDATE doors SET quantity=2 WHERE id=1")
        conn.commit()
        conn.close()
        order_id = create_cutting_order([1], 1)
        reserve_cutting_order(order_id, 1)
        send_cutting_order(order_id, 1)
        order = get_cutting_order(order_id)
        before = self.scalar("SELECT quantity FROM inventory_items")
        for bar in order["bars"]:
            self.assertTrue(confirm_bar_cut(order_id, bar["id"], 1, 0))
        completed = get_cutting_order(order_id)
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(all(bar["status"] == "cut" for bar in completed["bars"]))
        self.assertEqual(
            self.scalar("SELECT quantity FROM inventory_items"),
            before - len(order["bars"]),
        )

    def test_bulk_confirmation_is_atomic_and_completes_all_selected_bars(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM inventory_pieces")
        conn.execute(
            "UPDATE cutting_settings SET value='false' WHERE name='use_inventory_for_cutting'"
        )
        conn.execute("UPDATE doors SET quantity=2 WHERE id=1")
        conn.commit()
        conn.close()

        order_id = create_cutting_order([1], 1)
        reserve_cutting_order(order_id, 1)
        send_cutting_order(order_id, 1)
        order = get_cutting_order(order_id)
        self.assertGreater(len(order["bars"]), 1)
        before_stock = self.scalar("SELECT quantity FROM inventory_items")

        confirmed = confirm_bars_cut(
            order_id,
            [
                {
                    "bar_id": bar["id"],
                    "actual_remaining": bar["planned_remaining"],
                }
                for bar in order["bars"]
            ],
            1,
        )

        self.assertEqual(confirmed, len(order["bars"]))
        self.assertEqual(get_cutting_order(order_id)["status"], "completed")
        self.assertEqual(
            self.scalar("SELECT quantity FROM inventory_items"),
            before_stock - len(order["bars"]),
        )

    def test_bulk_confirmation_rolls_back_every_bar_when_one_value_is_invalid(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM inventory_pieces")
        conn.execute(
            "UPDATE cutting_settings SET value='false' WHERE name='use_inventory_for_cutting'"
        )
        conn.execute("UPDATE doors SET quantity=2 WHERE id=1")
        conn.commit()
        conn.close()

        order_id = create_cutting_order([1], 1)
        reserve_cutting_order(order_id, 1)
        send_cutting_order(order_id, 1)
        bars = get_cutting_order(order_id)["bars"]
        before_stock = self.scalar("SELECT quantity FROM inventory_items")
        before_operations = self.scalar("SELECT COUNT(*) FROM inventory_operations")

        with self.assertRaises(CuttingOrderError):
            confirm_bars_cut(
                order_id,
                [
                    {
                        "bar_id": bars[0]["id"],
                        "actual_remaining": bars[0]["planned_remaining"],
                    },
                    {
                        "bar_id": bars[1]["id"],
                        "actual_remaining": bars[1]["initial_length"] + 1,
                    },
                ],
                1,
            )

        self.assertEqual(self.scalar("SELECT quantity FROM inventory_items"), before_stock)
        self.assertEqual(
            self.scalar("SELECT COUNT(*) FROM inventory_operations"),
            before_operations,
        )
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM cutting_order_bars WHERE order_id=? AND status='reserved'",
                (order_id,),
            ),
            len(bars),
        )

    def test_main_web_route_from_calculation_to_excel(self):
        previous_auth_db = auth_utils.DB_NAME
        auth_utils.DB_NAME = self.db_path
        try:
            with mock.patch.object(database, "init_db"):
                from cutting_web_app import app

            app.config.update(TESTING=True)
            client = app.test_client()
            with client.session_transaction() as session:
                session["_user_id"] = "1"
                session["_fresh"] = True
                session["auth_version"] = 0
                session["csrf_token"] = "cutting-order-test-token"
            response = client.post(
                "/cutting-orders/calculate",
                data={
                    "csrf_token": "cutting-order-test-token",
                    "project_ids": "1",
                },
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            match = re.search(
                r"/cutting-orders/(\d+)$", response.headers["Location"]
            )
            self.assertIsNotNone(match)
            order_id = int(match.group(1))
            for action in ("reserve", "send"):
                response = client.post(
                    f"/cutting-orders/{order_id}/{action}",
                    data={"csrf_token": "cutting-order-test-token"},
                    follow_redirects=False,
                )
                self.assertEqual(response.status_code, 302)
            details = client.get(f"/cutting-orders/{order_id}")
            self.assertEqual(details.status_code, 200)
            self.assertIn(b'id="select-all-cuts"', details.data)
            bar = get_cutting_order(order_id)["bars"][0]
            response = client.post(
                f"/cutting-orders/{order_id}/confirm-cuts",
                data={
                    "csrf_token": "cutting-order-test-token",
                    "bar_ids": str(bar["id"]),
                    f"actual_remaining_{bar['id']}": bar["planned_remaining"],
                },
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            response = client.get(f"/cutting-orders/{order_id}/excel")
            self.assertEqual(response.status_code, 200)
            self.assertGreater(len(response.data), 5000)
        finally:
            auth_utils.DB_NAME = previous_auth_db

    def test_archiving_project_never_restores_an_already_cut_source(self):
        order_id = create_cutting_order([1], 1)
        reserve_cutting_order(order_id, 1)
        send_cutting_order(order_id, 1)
        order = get_cutting_order(order_id)
        stock_bar = next(
            bar for bar in order["bars"] if bar["source_type"] == "new_stock"
        )
        before_cut = self.scalar("SELECT quantity FROM inventory_items")
        confirm_bar_cut(order_id, stock_bar["id"], 1, 0)
        after_cut = self.scalar("SELECT quantity FROM inventory_items")
        self.assertEqual(after_cut, before_cut - 1)
        archived, affected = archive_project_safely(1, 1)
        self.assertTrue(archived)
        self.assertEqual(affected, [order_id])
        self.assertIsNotNone(
            self.scalar("SELECT archived_at FROM projects WHERE id=1")
        )
        self.assertEqual(self.scalar("SELECT quantity FROM inventory_items"), after_cut)
        self.assertEqual(
            self.scalar(
                "SELECT COUNT(*) FROM inventory_reservations WHERE order_id=? AND status='active'",
                (order_id,),
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
