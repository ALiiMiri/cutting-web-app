# -*- coding: utf-8 -*-
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session
import os
import traceback  # ط¨ط±ط§غŒ ظ†ظ…ط§غŒط´ ط®ط·ط§غŒ ع©ط§ظ…ظ„
from flask import send_file, jsonify
import time
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display
from weasyprint import HTML, CSS
from datetime import datetime, date
import jdatetime

# --- طھظ†ط¸غŒظ…ط§طھ ط§ظˆظ„غŒظ‡ ---
DB_NAME = "cutting_web_data.db"

# --- طھظˆط§ط¨ط¹ ع©ط§ط± ط¨ط§ ط¯غŒطھط§ط¨غŒط³ (ظ…ط³طھظ‚غŒظ… ط¯ط± ظ‡ظ…غŒظ† ظپط§غŒظ„) ---

# --- طھط§ط¨ط¹ ع©ظ…ع©غŒ ط¨ط±ط§غŒ ط¨ط±ط±ط³غŒ ظˆط¬ظˆط¯ ط¬ط¯ظˆظ„ ---


def check_table_exists(table_name):
    conn_check = None
    exists = False
    print(f"DEBUG: ط´ط±ظˆط¹ ط¨ط±ط±ط³غŒ ظˆط¬ظˆط¯ ط¬ط¯ظˆظ„ '{table_name}'...")
    try:
        conn_check = sqlite3.connect(DB_NAME)
        cursor_check = conn_check.cursor()
        cursor_check.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        result = cursor_check.fetchone()
        if result:
            exists = True
            print(
                f"DEBUG: ط¬ط¯ظˆظ„ '{table_name}' ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط¯ط± ط¯غŒطھط§ط¨غŒط³ '{DB_NAME}' ظ¾غŒط¯ط§ ط´ط¯."
            )
        else:
            print(
                f"DEBUG: ط¬ط¯ظˆظ„ '{table_name}' ط¯ط± ط¯غŒطھط§ط¨غŒط³ '{DB_NAME}' غŒط§ظپطھ ظ†ط´ط¯."
            )
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± check_table_exists: {e}")
        traceback.print_exc()
    finally:
        if conn_check:
            conn_check.close()
    return exists


# ------------------------------------


def initialize_database():
    """ط¬ط¯ظˆظ„ ظ¾ط±ظˆعکظ‡â€Œظ‡ط§طŒ ط¯ط±ط¨â€Œظ‡ط§طŒ ط³طھظˆظ†â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ ظˆ ع¯ط²غŒظ†ظ‡â€Œظ‡ط§ ط±ط§ ط§ع¯ط± ظˆط¬ظˆط¯ ظ†ط¯ط§ط±ظ†ط¯طŒ ط¨ط§ ط³ط§ط®طھط§ط± ط¬ط¯غŒط¯ ظ…غŒâ€Œط³ط§ط²ط¯"""
    conn = None
    try:
        print(f"DEBUG: طھظ„ط§ط´ ط¨ط±ط§غŒ ط§طھطµط§ظ„ ط¨ظ‡ ط¯غŒطھط§ط¨غŒط³ '{DB_NAME}' (initialize_database)")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        print("DEBUG: ط§غŒط¬ط§ط¯ ط¬ط¯ظˆظ„ 'projects' (ط§ع¯ط± ظˆط¬ظˆط¯ ظ†ط¯ط§ط´طھظ‡ ط¨ط§ط´ط¯)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                customer_name TEXT,
                order_ref TEXT,
                date_shamsi TEXT
            )
        """
        )

        print("DEBUG: ط§غŒط¬ط§ط¯ ط¬ط¯ظˆظ„ 'doors' (ط§ع¯ط± ظˆط¬ظˆط¯ ظ†ط¯ط§ط´طھظ‡ ط¨ط§ط´ط¯)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS doors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                location TEXT,
                width REAL,
                height REAL,
                quantity INTEGER,
                direction TEXT,
                row_color_tag TEXT DEFAULT 'white',
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            )
        """
        )

        print("DEBUG: ط§غŒط¬ط§ط¯ ط¬ط¯ظˆظ„ 'custom_columns' (ط§ع¯ط± ظˆط¬ظˆط¯ ظ†ط¯ط§ط´طھظ‡ ط¨ط§ط´ط¯)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_columns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                column_name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        """
        )

        print("DEBUG: ط§غŒط¬ط§ط¯ ط¬ط¯ظˆظ„ 'custom_column_options' (ط§ع¯ط± ظˆط¬ظˆط¯ ظ†ط¯ط§ط´طھظ‡ ط¨ط§ط´ط¯)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_column_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                column_id INTEGER NOT NULL,
                option_value TEXT NOT NULL,
                FOREIGN KEY (column_id) REFERENCES custom_columns (id) ON DELETE CASCADE
            )
        """
        )

        print("DEBUG: ط§غŒط¬ط§ط¯ ط¬ط¯ظˆظ„ 'door_custom_values' (ط§ع¯ط± ظˆط¬ظˆط¯ ظ†ط¯ط§ط´طھظ‡ ط¨ط§ط´ط¯)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS door_custom_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                door_id INTEGER NOT NULL,
                column_id INTEGER NOT NULL,
                value TEXT,
                FOREIGN KEY (door_id) REFERENCES doors (id) ON DELETE CASCADE,
                FOREIGN KEY (column_id) REFERENCES custom_columns (id) ON DELETE CASCADE
            )
        """
        )
        
        # ط§ط¶ط§ظپظ‡ ع©ط±ط¯ظ† ط³طھظˆظ† طھط§ط±غŒط® ط¨ظ‡ ط¬ط¯ظˆظ„ projects ط§ع¯ط± ظˆط¬ظˆط¯ ظ†ط¯ط§ط´طھظ‡ ط¨ط§ط´ط¯
        try:
            cursor.execute("SELECT date_shamsi FROM projects LIMIT 1")
        except sqlite3.OperationalError:
            print("DEBUG: ط§ط¶ط§ظپظ‡ ع©ط±ط¯ظ† ط³طھظˆظ† 'date_shamsi' ط¨ظ‡ ط¬ط¯ظˆظ„ 'projects'...")
            cursor.execute("ALTER TABLE projects ADD COLUMN date_shamsi TEXT")
        
        # ط§ط¶ط§ظپظ‡ ع©ط±ط¯ظ† ط§غŒظ† ط®ط· ط¯ط± ط§ظ†طھظ‡ط§غŒ طھط§ط¨ط¹ ظ‚ط¨ظ„ ط§ط² conn.commit()
        ensure_base_columns_exist()

        conn.commit()
        print("DEBUG: طھط؛غŒغŒط±ط§طھ ط³ط§غŒطھ ط¨ظ‡ ط¯غŒطھط§ط¨غŒط³ ط¨ط§ ظ…ظˆظپظ‚غŒطھ Commit ط´ط¯.")
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± initialize_database: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()


def ensure_base_columns_exist():
    """ط§ط·ظ…غŒظ†ط§ظ† ط§ط² ظˆط¬ظˆط¯ ط³طھظˆظ†â€Œظ‡ط§غŒ ظ¾ط§غŒظ‡ ط¯ط± ط¯غŒطھط§ط¨غŒط³"""
    base_columns = [
        ("rang", "ط±ظ†ع¯ ظ¾ط±ظˆظپغŒظ„"),
        ("noe_profile", "ظ†ظˆط¹ ظ¾ط±ظˆظپغŒظ„"),
        ("vaziat", "ظˆط¶ط¹غŒطھ طھظˆظ„غŒط¯ ط¯ط±ط¨"),
        ("lola", "ظ„ظˆظ„ط§"),
        ("ghofl", "ظ‚ظپظ„"),
        ("accessory", "ط§ع©ط³ط³ظˆط±غŒ"),
        ("kolaft", "ع©ظ„ط§ظپ"),
        ("dastgire", "ط¯ط³طھع¯غŒط±ظ‡"),
        ("tozihat", "طھظˆط¶غŒط­ط§طھ")
    ]
    
    for column_key, display_name in base_columns:
        conn = None
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            # ط¨ط±ط±ط³غŒ ظˆط¬ظˆط¯ ط³طھظˆظ†
            cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
            result = cursor.fetchone()
            if not result:
                print(f"DEBUG: ط§ظپط²ظˆط¯ظ† ط³طھظˆظ† ظ¾ط§غŒظ‡ '{column_key}' ط¨ظ‡ ط¯غŒطھط§ط¨غŒط³")
                cursor.execute(
                    "INSERT INTO custom_columns (column_name, display_name, is_active) VALUES (?, ?, 1)",
                    (column_key, display_name)
                )
                conn.commit()
        except sqlite3.Error as e:
            print(f"ERROR ط¯ط± ensure_base_columns_exist ط¨ط±ط§غŒ ط³طھظˆظ† {column_key}: {e}")
        finally:
            if conn:
                conn.close()


def get_all_projects():
    """ظ„غŒط³طھغŒ ط§ط² طھظ…ط§ظ… ظ¾ط±ظˆعکظ‡â€Œظ‡ط§ (id, ظ†ط§ظ… ظ…ط´طھط±غŒطŒ ط´ظ…ط§ط±ظ‡ ط³ظپط§ط±ط´) ط±ط§ ط¨ط±ظ…غŒâ€Œع¯ط±ط¯ط§ظ†ط¯"""
    conn = None
    projects = []
    print("DEBUG: ظˆط±ظˆط¯ ط¨ظ‡ طھط§ط¨ط¹ get_all_projects")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, customer_name, order_ref, date_shamsi FROM projects ORDER BY id DESC"
        )
        projects = [
            {"id": row[0], "cust_name": row[1], "order_ref": row[2], "date_shamsi": row[3]}
            for row in cursor.fetchall()
        ]
        print(f"DEBUG: get_all_projects {len(projects)} ظ¾ط±ظˆعکظ‡ غŒط§ظپطھ.")
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± get_all_projects: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return projects


def add_project_db(customer_name, order_ref, date_shamsi=""):
    """ط§ط¶ط§ظپظ‡ ع©ط±ط¯ظ† غŒع© ظ¾ط±ظˆعکظ‡ ط¬ط¯غŒط¯ ط¨ظ‡ ط¯غŒطھط§ط¨غŒط³"""
    print(f"DEBUG: ظˆط±ظˆط¯ ط¨ظ‡ طھط§ط¨ط¹ add_project_dbطŒ customer_name: {customer_name}, order_ref: {order_ref}, date_shamsi: {date_shamsi}")
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO projects (customer_name, order_ref, date_shamsi) VALUES (?, ?, ?)",
            (customer_name, order_ref, date_shamsi),
        )
        project_id = cursor.lastrowid
        conn.commit()
        print(f"DEBUG: ظ¾ط±ظˆعکظ‡â€ŒغŒ ط¬ط¯غŒط¯ ط¨ط§ ط¢غŒâ€Œط¯غŒ {project_id} ط§ط¶ط§ظپظ‡ ط´ط¯.")
        return project_id
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± add_project_db: {e}")
        traceback.print_exc()
        return None
    finally:
        if conn:
            conn.close()


def get_project_details_db(project_id):
    """ط¬ط²ط¦غŒط§طھ غŒع© ظ¾ط±ظˆعکظ‡ ط®ط§طµ ط±ط§ ط¨ط± ط§ط³ط§ط³ ID ط¨ط±ظ…غŒâ€Œع¯ط±ط¯ط§ظ†ط¯"""
    conn = None
    project_details = None
    print(f"DEBUG: ظˆط±ظˆط¯ ط¨ظ‡ طھط§ط¨ط¹ get_project_details_db ط¨ط±ط§غŒ ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, customer_name, order_ref, date_shamsi FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        if row:
            project_details = {
                "id": row[0],
                "customer_name": row[1],
                "order_ref": row[2],
                "date_shamsi": row[3]
            }
            print(f"DEBUG: ط¬ط²ط¦غŒط§طھ ظ¾ط±ظˆعکظ‡ ID {project_id} غŒط§ظپطھ ط´ط¯.")
        else:
            print(f"DEBUG: ظ¾ط±ظˆعکظ‡ ID {project_id} غŒط§ظپطھ ظ†ط´ط¯.")
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± get_project_details_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return project_details


def get_doors_for_project_db(project_id):
    """ظ„غŒط³طھغŒ ط§ط² طھظ…ط§ظ… ط¯ط±ط¨â€Œظ‡ط§غŒ ظ…ط±ط¨ظˆط· ط¨ظ‡ غŒع© ظ¾ط±ظˆعکظ‡ ط®ط§طµ ط±ط§ ط¨ط±ظ…غŒâ€Œع¯ط±ط¯ط§ظ†ط¯"""
    conn = None
    doors = []
    print(f"DEBUG: ظˆط±ظˆط¯ ط¨ظ‡ طھط§ط¨ط¹ get_doors_for_project_db ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # ط§ط¨طھط¯ط§ ط§ط·ظ„ط§ط¹ط§طھ ظ¾ط§غŒظ‡ ط¯ط±ط¨â€Œظ‡ط§ ط±ط§ ظ…غŒâ€Œع¯غŒط±غŒظ…
        cursor.execute(
            """
            SELECT id, location, width, height, quantity, direction, row_color_tag 
            FROM doors 
            WHERE project_id = ? 
            ORDER BY id
        """,
            (project_id,),
        )

        base_doors_data = cursor.fetchall()
        print(f"DEBUG: طھط¹ط¯ط§ط¯ ط¯ط±ط¨â€Œظ‡ط§غŒ ظ¾ط§غŒظ‡ غŒط§ظپطھ ط´ط¯ظ‡: {len(base_doors_data)}")

        for row in base_doors_data:
            door_id = row[0]
            door_data = {
                "id": door_id,
                "location": row[1],
                "width": row[2],
                "height": row[3],
                "quantity": row[4],
                "direction": row[5],
                "row_color_tag": row[6] if row[6] else "white",
                # ظ¾ط± ع©ط±ط¯ظ† ظ…ظ‚ط§ط¯غŒط± ظ¾غŒط´â€Œظپط±ط¶ ط¨ط±ط§غŒ ط³ط§غŒط± ط³طھظˆظ†â€Œظ‡ط§
                "rang": "",
                "noe_profile": "",
                "vaziat": "",
                "lola": "",
                "ghofl": "",
                "accessory": "",
                "kolaft": "",
                "dastgire": "",
                "tozihat": ""
            }

            # ظ…ظ‚ط§ط¯غŒط± ط³طھظˆظ†â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ ط±ط§ ط¨ط±ط§غŒ ط§غŒظ† ط¯ط±ط¨ ط¯ط±غŒط§ظپطھ ظ…غŒâ€Œع©ظ†غŒظ…
            cursor.execute("""
                SELECT cc.column_name, dcv.value
                FROM door_custom_values dcv
                JOIN custom_columns cc ON dcv.column_id = cc.id
                WHERE dcv.door_id = ?
            """, (door_id,))
            
            for custom_col in cursor.fetchall():
                col_name = custom_col[0]
                col_value = custom_col[1]
                door_data[col_name] = col_value
                
            print(f"DEBUG: ظ…ظ‚ط§ط¯غŒط± ط³ظپط§ط±ط´غŒ ط¯ط±ط¨ {door_id}: ghofl={door_data.get('ghofl')}, rang={door_data.get('rang')}")

            doors.append(door_data)

        print(f"DEBUG: get_doors_for_project_db {len(doors)} ط¯ط±ط¨ غŒط§ظپطھ.")
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± get_doors_for_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return doors


def add_door_db(
    project_id, location, width, height, quantity, direction, row_color="white"
):
    """ط§ط·ظ„ط§ط¹ط§طھ غŒع© ط¯ط±ط¨ ط¬ط¯غŒط¯ ط±ط§ ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ ظ…ط´ط®طµ ط´ط¯ظ‡ ط¯ط± ط¯غŒطھط§ط¨غŒط³ ط°ط®غŒط±ظ‡ ظ…غŒâ€Œع©ظ†ط¯"""
    conn = None
    door_id = None
    print(f"DEBUG: ظˆط±ظˆط¯ ط¨ظ‡ طھط§ط¨ط¹ add_door_db ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO doors (project_id, location, width, height, quantity, direction, row_color_tag) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (project_id, location, width, height, quantity, direction, row_color),
        )
        door_id = cursor.lastrowid
        conn.commit()
        print(
            f"DEBUG: ط¯ط±ط¨ ط¬ط¯غŒط¯ ط¨ط§ ID {door_id} ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ ID {project_id} ط°ط®غŒط±ظ‡ ظˆ commit ط´ط¯."
        )
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± add_door_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return door_id


def get_all_custom_columns():
    """ظ„غŒط³طھ طھظ…ط§ظ… ط³طھظˆظ†â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ ط±ط§ ط¨ط±ظ…غŒâ€Œع¯ط±ط¯ط§ظ†ط¯"""
    conn = None
    columns = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, column_name, display_name, is_active FROM custom_columns ORDER BY id"
        )
        columns = [
            {"id": row[0], "key": row[1], "display": row[2], "is_active": row[3]}
            for row in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± get_all_custom_columns: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return columns


def get_active_custom_columns():
    """ظ„غŒط³طھ ط³طھظˆظ†â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ ظپط¹ط§ظ„ ط±ط§ ط¨ط±ظ…غŒâ€Œع¯ط±ط¯ط§ظ†ط¯"""
    conn = None
    columns = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, column_name, display_name FROM custom_columns WHERE is_active = 1 ORDER BY id"
        )
        columns = [
            {"id": row[0], "key": row[1], "display": row[2]}
            for row in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± get_active_custom_columns: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return columns


def add_custom_column(column_name, display_name):
    """ط§ظپط²ظˆط¯ظ† ط³طھظˆظ† ط³ظپط§ط±ط´غŒ ط¬ط¯غŒط¯"""
    conn = None
    new_id = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO custom_columns (column_name, display_name) VALUES (?, ?)",
            (column_name, display_name),
        )
        new_id = cursor.lastrowid
        conn.commit()
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± add_custom_column: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return new_id


def update_custom_column_status(column_id, is_active):
    """طھط؛غŒغŒط± ظˆط¶ط¹غŒطھ ظپط¹ط§ظ„/ط؛غŒط±ظپط¹ط§ظ„ ط³طھظˆظ† ط³ظپط§ط±ط´غŒ"""
    conn = None
    success = False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE custom_columns SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, column_id),
        )
        conn.commit()
        success = True
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± update_custom_column_status: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


def get_column_id_by_key(column_key):
    """غŒط§ظپطھظ† ط´ظ†ط§ط³ظ‡ ط³طھظˆظ† ط¨ط±ط§ط³ط§ط³ ع©ظ„غŒط¯ ط¢ظ†"""
    conn = None
    column_id = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM custom_columns WHERE column_name = ?", (column_key,)
        )
        result = cursor.fetchone()
        if result:
            column_id = result[0]
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± get_column_id_by_key: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return column_id


def get_custom_column_options(column_id):
    """ع¯ط²غŒظ†ظ‡â€Œظ‡ط§غŒ غŒع© ط³طھظˆظ† ط³ظپط§ط±ط´غŒ ط±ط§ ط¨ط±ظ…غŒâ€Œع¯ط±ط¯ط§ظ†ط¯"""
    conn = None
    options = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT option_value FROM custom_column_options WHERE column_id = ? ORDER BY id",
            (column_id,),
        )
        options = [row[0] for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± get_custom_column_options: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return options


def add_option_to_column(column_id, option_value):
    """ط§ظپط²ظˆط¯ظ† ع¯ط²غŒظ†ظ‡ ط¬ط¯غŒط¯ ط¨ظ‡ ط³طھظˆظ† ط³ظپط§ط±ط´غŒ"""
    conn = None
    success = False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO custom_column_options (column_id, option_value) VALUES (?, ?)",
            (column_id, option_value),
        )
        conn.commit()
        success = True
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± add_option_to_column: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


def delete_column_option(option_id):
    """ط­ط°ظپ غŒع© ع¯ط²غŒظ†ظ‡ ط§ط² ط³طھظˆظ† ط³ظپط§ط±ط´غŒ"""
    conn = None
    success = False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM custom_column_options WHERE id = ?", (option_id,))
        conn.commit()
        success = True
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± delete_column_option: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


def update_door_custom_value(door_id, column_id, value):
    """ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ظ…ظ‚ط¯ط§ط± غŒع© ط³طھظˆظ† ط³ظپط§ط±ط´غŒ ط¨ط±ط§غŒ غŒع© ط¯ط±ط¨"""
    conn = None
    success = False
    
    print(f"DEBUG: ط´ط±ظˆط¹ ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ظ…ظ‚ط¯ط§ط± ط³ظپط§ط±ط´غŒ - ط¯ط±ط¨: {door_id}, ط³طھظˆظ†: {column_id}, ظ…ظ‚ط¯ط§ط±: '{value}'")
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # ط§ط¨طھط¯ط§ ع†ع© ظ…غŒâ€Œع©ظ†غŒظ… ع©ظ‡ ط¢غŒط§ ط±ع©ظˆط±ط¯غŒ ظˆط¬ظˆط¯ ط¯ط§ط±ط¯
        cursor.execute(
            "SELECT id FROM door_custom_values WHERE door_id = ? AND column_id = ?",
            (door_id, column_id),
        )
        exists = cursor.fetchone()

        if exists:
            print(f"DEBUG: ط¨ط±ظˆط²ط±ط³ط§ظ†غŒ ظ…ظ‚ط¯ط§ط± ظ…ظˆط¬ظˆط¯ ط¨ط±ط§غŒ ط¯ط±ط¨ {door_id}, ط³طھظˆظ† {column_id}")
            cursor.execute(
                "UPDATE door_custom_values SET value = ? WHERE door_id = ? AND column_id = ?",
                (value, door_id, column_id),
            )
            print(f"DEBUG: طھط¹ط¯ط§ط¯ ط±ع©ظˆط±ط¯ظ‡ط§غŒ ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط´ط¯ظ‡: {cursor.rowcount}")
        else:
            print(f"DEBUG: ط¯ط±ط¬ ظ…ظ‚ط¯ط§ط± ط¬ط¯غŒط¯ ط¨ط±ط§غŒ ط¯ط±ط¨ {door_id}, ط³طھظˆظ† {column_id}")
            cursor.execute(
                "INSERT INTO door_custom_values (door_id, column_id, value) VALUES (?, ?, ?)",
                (door_id, column_id, value),
            )
            print(f"DEBUG: ط´ظ†ط§ط³ظ‡ ط¯ط±ط¬ ط´ط¯ظ‡: {cursor.lastrowid}")

        conn.commit()
        print(f"DEBUG: طھط؛غŒغŒط±ط§طھ ط¯ط± door_custom_values ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط°ط®غŒط±ظ‡ ط´ط¯ (commit).")
        
        # ط¨ط±ط§غŒ ط§ط·ظ…غŒظ†ط§ظ†طŒ ظ…ظ‚ط¯ط§ط± ظ†ظ‡ط§غŒغŒ ط±ط§ ط¨ط®ظˆط§ظ†غŒظ…
        cursor.execute(
            "SELECT value FROM door_custom_values WHERE door_id = ? AND column_id = ?",
            (door_id, column_id),
        )
        final_value = cursor.fetchone()
        print(f"DEBUG: ظ…ظ‚ط¯ط§ط± ظ†ظ‡ط§غŒغŒ ط°ط®غŒط±ظ‡ ط´ط¯ظ‡: {final_value[0] if final_value else 'NULL'}")
        
        success = True
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± update_door_custom_value: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    
    print(f"DEBUG: ظ¾ط§غŒط§ظ† ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ظ…ظ‚ط¯ط§ط± ط³ظپط§ط±ط´غŒ - ظ†طھغŒط¬ظ‡: {'ظ…ظˆظپظ‚' if success else 'ظ†ط§ظ…ظˆظپظ‚'}")
    return success


def get_door_custom_values(door_id):
    """طھظ…ط§ظ… ظ…ظ‚ط§ط¯غŒط± ط³طھظˆظ†â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ غŒع© ط¯ط±ط¨ ط±ط§ ط¨ط±ظ…غŒâ€Œع¯ط±ط¯ط§ظ†ط¯"""
    conn = None
    values = {}
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT cc.column_name, dcv.value
            FROM door_custom_values dcv
            JOIN custom_columns cc ON dcv.column_id = cc.id
            WHERE dcv.door_id = ?
        """,
            (door_id,),
        )

        for row in cursor.fetchall():
            values[row[0]] = row[1]
            
        # ط§ط¶ط§ظپظ‡ ع©ط±ط¯ظ† ط¯ط³طھظˆط± ط¯غŒط¨ط§ع¯ ط¨ط±ط§غŒ ط¨ط±ط±ط³غŒ ظ…ظ‚ط§ط¯غŒط± ط¨ط§ط²غŒط§ط¨غŒ ط´ط¯ظ‡
        print(f"DEBUG: ظ…ظ‚ط§ط¯غŒط± ط³ظپط§ط±ط´غŒ ط¨ط±ط§غŒ ط¯ط±ط¨ {door_id}: {values}")
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± get_door_custom_values: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return values


def update_project_db(project_id, customer_name, order_ref, date_shamsi=""):
    """ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط§ط·ظ„ط§ط¹ط§طھ غŒع© ظ¾ط±ظˆعکظ‡ ط¨ط§ ID ظ…ط´ط®طµ"""
    conn = None
    success = False
    print(f"DEBUG: ظˆط±ظˆط¯ ط¨ظ‡ طھط§ط¨ط¹ update_project_db ط¨ط±ط§غŒ ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE projects SET customer_name = ?, order_ref = ?, date_shamsi = ? WHERE id = ?",
            (customer_name, order_ref, date_shamsi, project_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        print(f"DEBUG: ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ظ¾ط±ظˆعکظ‡ ID {project_id} {'ط§ظ†ط¬ط§ظ… ط´ط¯' if success else 'ط§ظ†ط¬ط§ظ… ظ†ط´ط¯'}.")
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± update_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


def delete_project_db(project_id):
    """ط­ط°ظپ غŒع© ظ¾ط±ظˆعکظ‡ ظˆ طھظ…ط§ظ… ط¯ط±ط¨â€Œظ‡ط§غŒ ظ…ط±طھط¨ط· ط¨ط§ ط¢ظ† (ط¨ط§ ط§ط³طھظپط§ط¯ظ‡ ط§ط² ON DELETE CASCADE)"""
    conn = None
    success = False
    print(f"DEBUG: ظˆط±ظˆط¯ ط¨ظ‡ طھط§ط¨ط¹ delete_project_db ط¨ط±ط§غŒ ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        success = cursor.rowcount > 0
        print(f"DEBUG: ط­ط°ظپ ظ¾ط±ظˆعکظ‡ ID {project_id} {'ط§ظ†ط¬ط§ظ… ط´ط¯' if success else 'ط§ظ†ط¬ط§ظ… ظ†ط´ط¯'}.")
    except sqlite3.Error as e:
        print(f"!!!!!! ط®ط·ط§ ط¯ط± delete_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success


# --- Flask App Setup ---
app = Flask(__name__, template_folder='templates')
app.secret_key = "a_different_secret_key_now_for_sure"  # ع©ظ„غŒط¯ ظ…ط®ظپغŒ

# --- ظ…ظ‚ط¯ط§ط±ط¯ظ‡غŒ ط§ظˆظ„غŒظ‡ ط¯غŒطھط§ط¨غŒط³ ---
initialize_database()

# --- ط¨ط±ط±ط³غŒ ظˆط¬ظˆط¯ ط¬ط¯ط§ظˆظ„ ط¨ط¹ط¯ ط§ط² ظ…ظ‚ط¯ط§ط±ط¯ظ‡غŒ ط§ظˆظ„غŒظ‡ ---
print("\n--- ط´ط±ظˆط¹ ط¨ط±ط±ط³غŒ ط¬ط¯ط§ظˆظ„ ---")
check_table_exists("projects")
check_table_exists("doors")
check_table_exists("custom_columns")
check_table_exists("custom_column_options")
check_table_exists("door_custom_values")
print("--- ظ¾ط§غŒط§ظ† ط¨ط±ط±ط³غŒ ط¬ط¯ط§ظˆظ„ ---\n")


# --- Routes (ط¢ط¯ط±ط³â€Œظ‡ط§غŒ ظˆط¨) ---


@app.route("/")
def index():
    print("DEBUG: ط±ظˆطھ / (index) ظپط±ط§ط®ظˆط§ظ†غŒ ط´ط¯.")
    try:
        projects_list = get_all_projects()
        return render_template("index.html", projects=projects_list)
    except Exception as e:
        print(f"!!!!!! ط®ط·ط§غŒ ط؛غŒط±ظ…ظ†طھط¸ط±ظ‡ ط¯ط± ط±ظˆطھ index: {e}")
        traceback.print_exc()
        flash("ط®ط·ط§غŒغŒ ط¯ط± ظ†ظ…ط§غŒط´ ظ„غŒط³طھ ظ¾ط±ظˆعکظ‡â€Œظ‡ط§ ط±ط® ط¯ط§ط¯.", "error")
        return render_template("index.html", projects=[])


@app.route("/project/add", methods=["GET"])
def add_project_form():
    print("DEBUG: ط±ظˆطھ /project/add (GET - add_project_form) ظپط±ط§ط®ظˆط§ظ†غŒ ط´ط¯.")
    return render_template("add_project.html")


@app.route("/project/add", methods=["POST"])
def add_project_route():
    print("DEBUG: ط±ظˆطھ /project/add (POST - add_project_route) ظپط±ط§ط®ظˆط§ظ†غŒ ط´ط¯.")
    customer_name = request.form.get("customer_name")
    order_ref = request.form.get("order_ref")
    date_shamsi = request.form.get("date_shamsi", "")
    
    if not customer_name and not order_ref:
        flash("ظ„ط·ظپط§ظ‹ ط­ط¯ط§ظ‚ظ„ ظ†ط§ظ… ظ…ط´طھط±غŒ غŒط§ ط´ظ…ط§ط±ظ‡ ط³ظپط§ط±ط´ ط±ط§ ظˆط§ط±ط¯ ع©ظ†غŒط¯.", "error")
        return render_template("add_project.html")
    
    new_id = add_project_db(customer_name, order_ref, date_shamsi)
    if new_id:
        flash(
            f"ظ¾ط±ظˆعکظ‡ ط¬ط¯غŒط¯ ط¨ط±ط§غŒ ظ…ط´طھط±غŒ '{customer_name}' (ط´ظ…ط§ط±ظ‡ ط³ظپط§ط±ط´: {order_ref}) ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط§ط¶ط§ظپظ‡ ط´ط¯.",
            "success",
        )
        print(f"DEBUG: ظ¾ط±ظˆعکظ‡ ID {new_id} ط§ط¶ط§ظپظ‡ ط´ط¯طŒ ط±غŒط¯ط§غŒط±ع©طھ ط¨ظ‡ index.")
        return redirect(url_for("index"))
    else:
        flash("ط®ط·ط§غŒغŒ ط¯ط± ط°ط®غŒط±ظ‡ ظ¾ط±ظˆعکظ‡ ط±ط® ط¯ط§ط¯.", "error")
        return render_template("add_project.html")


@app.route("/project/<int:project_id>")
def view_project(project_id):
    print(f"DEBUG: >>>>>>> ظˆط±ظˆط¯ ط¨ظ‡ ط±ظˆطھ /project/{project_id} (view_project) <<<<<<<")
    print(f"DEBUG: Request Headers (view_project):\n{request.headers}")
    project_details = None
    door_list = []
    try:
        project_details = get_project_details_db(project_id)
        if not project_details:
            flash(f"ظ¾ط±ظˆعکظ‡ ط¨ط§ ID {project_id} غŒط§ظپطھ ظ†ط´ط¯.", "error")
            print(f"DEBUG: ظ¾ط±ظˆعکظ‡ {project_id} غŒط§ظپطھ ظ†ط´ط¯طŒ ط±غŒط¯ط§غŒط±ع©طھ ط¨ظ‡ index.")
            return redirect(url_for("index"))
        door_list = get_doors_for_project_db(project_id)
        print(
            f"DEBUG: ط±ظ†ط¯ط± ع©ط±ط¯ظ† project_details.html ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ {project_id} ط¨ط§ {len(door_list)} ط¯ط±ط¨."
        )
        return render_template(
            "project_details.html", project=project_details, doors=door_list
        )
    except Exception as e:
        print(f"!!!!!! ط®ط·ط§غŒ ط¬ط¯غŒ ط¯ط± ط±ظˆطھ view_project ط¨ط±ط§غŒ ID {project_id}: {e}")
        traceback.print_exc()
        flash("ط®ط·ط§غŒغŒ ط¯ط± ظ†ظ…ط§غŒط´ ط¬ط²ط¦غŒط§طھ ظ¾ط±ظˆعکظ‡ ط±ط® ط¯ط§ط¯. ظ„ط·ظپط§ظ‹ ط¯ظˆط¨ط§ط±ظ‡ طھظ„ط§ط´ ع©ظ†غŒط¯.", "error")
        print(f"DEBUG: ط®ط·ط§ ط¯ط± view_projectطŒ ط±غŒط¯ط§غŒط±ع©طھ ط¨ظ‡ index.")
        return redirect(url_for("index"))


@app.route("/project/<int:project_id>/add_door", methods=["GET"])
def add_door_form(project_id):
    print(
        f"DEBUG: ط±ظˆطھ /project/{project_id}/add_door (GET - add_door_form) ظپط±ط§ط®ظˆط§ظ†غŒ ط´ط¯."
    )
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash(f"ظ¾ط±ظˆعکظ‡ ط¨ط§ ID {project_id} غŒط§ظپطھ ظ†ط´ط¯.", "error")
        return redirect(url_for("index"))
    # <-- ع©ظ„غŒط¯ session ظ…ظ†ط­طµط± ط¨ظ‡ ظپط±ط¯ ط¨ط±ط§غŒ ظ‡ط± ظ¾ط±ظˆعکظ‡
    pending_doors = session.get(f"pending_doors_{project_id}", [])
    pending_count = len(pending_doors)
    print(
        f"DEBUG: ظ†ظ…ط§غŒط´ ظپط±ظ… ط§ظپط²ظˆط¯ظ† ط¯ط±ط¨ ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ {project_id}. طھط¹ط¯ط§ط¯ ظ…ظ†طھط¸ط±: {pending_count}"
    )
    return render_template(
        "add_door.html", project_info=project_info, pending_count=pending_count
    )


@app.route("/project/<int:project_id>/add_door", methods=["POST"])
def add_door_buffer(project_id):
    print(
        f"DEBUG: ط±ظˆطھ /project/{project_id}/add_door (POST - add_door_buffer) ظپط±ط§ط®ظˆط§ظ†غŒ ط´ط¯."
    )
    location = request.form.get("location")
    width_str = request.form.get("width")
    height_str = request.form.get("height")
    quantity_str = request.form.get("quantity")
    direction = request.form.get("direction")

    # ظپغŒظ„ط¯ظ‡ط§غŒ ط³ظپط§ط±ط´غŒ ط¬ط¯غŒط¯
    rang = request.form.get("rang", "")
    noe_profile = request.form.get("noe_profile", "")
    vaziat = request.form.get("vaziat", "")
    lola = request.form.get("lola", "")
    ghofl = request.form.get("ghofl", "")
    accessory = request.form.get("accessory", "")
    kolaft = request.form.get("kolaft", "")
    dastgire = request.form.get("dastgire", "")
    tozihat = request.form.get("tozihat", "")
    row_color_tag = request.form.get("row_color_tag", "white")

    project_info = get_project_details_db(project_id)
    if not project_info:
        flash(f"ظ¾ط±ظˆعکظ‡ ط¨ط§ ID {project_id} غŒط§ظپطھ ظ†ط´ط¯.", "error")
        return redirect(url_for("index"))

    width = None
    height = None
    quantity = None
    errors = False
    try:
        if width_str:
            width = float(width_str)
        if height_str:
            height = float(height_str)
        if quantity_str:
            quantity = int(quantity_str)
        if (
            (width is not None and width <= 0)
            or (height is not None and height <= 0)
            or (quantity is not None and quantity <= 0)
        ):
            flash("ظ…ظ‚ط§ط¯غŒط± ط¹ط±ط¶طŒ ط§ط±طھظپط§ط¹ ظˆ طھط¹ط¯ط§ط¯ ط¨ط§غŒط¯ ظ…ط«ط¨طھ ط¨ط§ط´ظ†ط¯.", "error")
            errors = True
    except ValueError:
        flash("ظ…ظ‚ط§ط¯غŒط± ط¹ط±ط¶طŒ ط§ط±طھظپط§ط¹ ظˆ طھط¹ط¯ط§ط¯ ط¨ط§غŒط¯ ط¨ظ‡ طµظˆط±طھ ط¹ط¯ط¯غŒ ظˆط§ط±ط¯ ط´ظˆظ†ط¯.", "error")
        errors = True

    if errors:
        pending_doors = session.get(f"pending_doors_{project_id}", [])
        pending_count = len(pending_doors)
        print(f"DEBUG: ط®ط·ط§غŒ ط§ط¹طھط¨ط§ط±ط³ظ†ط¬غŒ ط¯ط± ط§ظپط²ظˆط¯ظ† ط¯ط±ط¨. ط¨ط§ط²ع¯ط´طھ ط¨ظ‡ ظپط±ظ… ط¨ط§ ط¯ط§ط¯ظ‡â€Œظ‡ط§غŒ ظ‚ط¨ظ„غŒ.")
        return render_template(
            "add_door.html",
            project_info=project_info,
            pending_count=pending_count,
            form_data=request.form,
        )

    # <-- ع©ظ„غŒط¯ session ظ…ظ†ط­طµط± ط¨ظ‡ ظپط±ط¯
    pending_doors = session.get(f"pending_doors_{project_id}", [])
    new_door_data = {
        "location": location,
        "width": width,
        "height": height,
        "quantity": quantity,
        "direction": direction,
        "rang": rang,
        "noe_profile": noe_profile,
        "vaziat": vaziat,
        "lola": lola,
        "ghofl": ghofl,
        "accessory": accessory,
        "kolaft": kolaft,
        "dastgire": dastgire,
        "tozihat": tozihat,
        "row_color_tag": row_color_tag,
    }
    pending_doors.append(new_door_data)
    # <-- ع©ظ„غŒط¯ session ظ…ظ†ط­طµط± ط¨ظ‡ ظپط±ط¯
    session[f"pending_doors_{project_id}"] = pending_doors
    print(
        f"DEBUG: ط¯ط±ط¨ ط¨ظ‡ ظ„غŒط³طھ ظ…ظˆظ‚طھ ظ¾ط±ظˆعکظ‡ {project_id} ط§ط¶ط§ظپظ‡ ط´ط¯. طھط¹ط¯ط§ط¯ ظ…ظ†طھط¸ط±: {len(pending_doors)}"
    )
    flash(
        "ط¯ط±ط¨ ط¨ظ‡ ظ„غŒط³طھ ظ…ظˆظ‚طھ ط§ط¶ط§ظپظ‡ ط´ط¯. ط¨ط±ط§غŒ ط°ط®غŒط±ظ‡ ظ†ظ‡ط§غŒغŒ ط§ط² ط¯ع©ظ…ظ‡ 'ط§طھظ…ط§ظ…' ط§ط³طھظپط§ط¯ظ‡ ع©ظ†غŒط¯.",
        "success",
    )
    return redirect(url_for("add_door_form", project_id=project_id))


@app.route("/project/<int:project_id>/finish_doors", methods=["GET"])
def finish_adding_doors(project_id):
    print(
        f"DEBUG: ط±ظˆطھ /project/{project_id}/finish_doors (GET - finish_adding_doors) ظپط±ط§ط®ظˆط§ظ†غŒ ط´ط¯."
    )
    # <-- ع©ظ„غŒط¯ session ظ…ظ†ط­طµط± ط¨ظ‡ ظپط±ط¯
    pending_doors = session.get(f"pending_doors_{project_id}", [])
    saved_count = 0
    error_count = 0

    if not pending_doors:
        flash("ظ‡غŒع† ط¯ط±ط¨غŒ ط¯ط± ظ„غŒط³طھ ظ…ظˆظ‚طھ ط¨ط±ط§غŒ ط°ط®غŒط±ظ‡ ظˆط¬ظˆط¯ ظ†ط¯ط§ط±ط¯.", "warning")
        print(f"DEBUG: ظ„غŒط³طھ ظ…ظˆظ‚طھ ط®ط§ظ„غŒ ط¨ظˆط¯طŒ ط±غŒط¯ط§غŒط±ع©طھ ط¨ظ‡ view_project {project_id}")
        return redirect(url_for("view_project", project_id=project_id))

    project_info = get_project_details_db(project_id)
    if not project_info:
        flash(f"ظ¾ط±ظˆعکظ‡ ط¨ط§ ID {project_id} غŒط§ظپطھ ظ†ط´ط¯.", "error")
        session.pop(f"pending_doors_{project_id}", None)
        return redirect(url_for("index"))

    print(
        f"DEBUG: ط´ط±ظˆط¹ ط°ط®غŒط±ظ‡ {len(pending_doors)} ط¯ط±ط¨ ط§ط² ظ„غŒط³طھ ظ…ظˆظ‚طھ ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ {project_id}..."
    )
    for door_data in pending_doors:
        # ط§ط¶ط§ظپظ‡ ع©ط±ط¯ظ† غŒع© ط¯ط±ط¨ ط¬ط¯غŒط¯ ظˆ ط¯ط±غŒط§ظپطھ ID ط¢ظ†
        door_id = add_door_db(
            project_id=project_id,
            location=door_data.get("location"),
            width=door_data.get("width"),
            height=door_data.get("height"),
            quantity=door_data.get("quantity"),
            direction=door_data.get("direction"),
            row_color=door_data.get("row_color_tag", "white"),
        )

        if door_id:
            saved_count += 1

            # ط°ط®غŒط±ظ‡ ظ…ظ‚ط§ط¯غŒط± ط³طھظˆظ†â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ
            for key, value in door_data.items():
                # ط§ع¯ط± ع©ظ„غŒط¯ ظ…ط±ط¨ظˆط· ط¨ظ‡ ط³طھظˆظ†â€Œظ‡ط§غŒ ظ¾ط§غŒظ‡ ظ†ط¨ط§ط´ط¯
                if key not in [
                    "location",
                    "width",
                    "height",
                    "quantity",
                    "direction",
                    "row_color_tag",
                ]:
                    # ط§ط¨طھط¯ط§ ID ط³طھظˆظ† ط±ط§ ظ¾غŒط¯ط§ ظ…غŒâ€Œع©ظ†غŒظ…
                    column_id = get_column_id_by_key(key)
                    if column_id:
                        # ظ…ظ‚ط¯ط§ط± ط³طھظˆظ† ط³ظپط§ط±ط´غŒ ط±ط§ ط°ط®غŒط±ظ‡ ظ…غŒâ€Œع©ظ†غŒظ…
                        update_door_custom_value(door_id, column_id, value)
        else:
            error_count += 1

    # <-- ع©ظ„غŒط¯ session ظ…ظ†ط­طµط± ط¨ظ‡ ظپط±ط¯
    session.pop(f"pending_doors_{project_id}", None)
    print(f"DEBUG: ظ„غŒط³طھ ظ…ظˆظ‚طھ ظ¾ط±ظˆعکظ‡ {project_id} ط§ط² session ظ¾ط§ع© ط´ط¯.")

    if error_count == 0:
        flash(f"{saved_count} ط¯ط±ط¨ ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط¯ط± ط¯غŒطھط§ط¨غŒط³ ط°ط®غŒط±ظ‡ ط´ط¯.", "success")
    else:
        flash(
            f"{saved_count} ط¯ط±ط¨ ط°ط®غŒط±ظ‡ ط´ط¯طŒ ط§ظ…ط§ ط¯ط± ط°ط®غŒط±ظ‡ {error_count} ط¯ط±ط¨ ط®ط·ط§ ط±ط® ط¯ط§ط¯.",
            "error",
        )

    target_url = url_for("view_project", project_id=project_id)
    print(f"DEBUG: ط°ط®غŒط±ظ‡ ظ†ظ‡ط§غŒغŒ ط§ظ†ط¬ط§ظ… ط´ط¯. ط±غŒط¯ط§غŒط±ع©طھ ط¨ظ‡: {target_url}")
    return redirect(target_url)


def initialize_visible_columns(project_id):
    """طھظ†ط¸غŒظ… ظˆط¶ط¹غŒطھ ط§ظˆظ„غŒظ‡ ط³طھظˆظ†â€Œظ‡ط§غŒ ظ†ظ…ط§غŒط´غŒ ط§ع¯ط± ظ‚ط¨ظ„ط§ظ‹ طھظ†ط¸غŒظ… ظ†ط´ط¯ظ‡ ط¨ط§ط´ظ†ط¯"""
    session_key = f"visible_columns_{project_id}"
    if session_key not in session:
        # طھظ†ط¸غŒظ… ط³طھظˆظ†â€Œظ‡ط§غŒ ظ¾غŒط´â€Œظپط±ط¶ ط¨ط±ط§غŒ ظ†ظ…ط§غŒط´ (ظ‡ظ…ظ‡ ط³طھظˆظ†â€Œظ‡ط§ ط¨ظ‡ ط¬ط² طھظˆط¶غŒط­ط§طھ)
        session[session_key] = ["rang", "noe_profile", "vaziat", "lola", "ghofl", "accessory", "kolaft", "dastgire"]
        print(f"DEBUG: طھظ†ط¸غŒظ… ط§ظˆظ„غŒظ‡ ط³طھظˆظ†â€Œظ‡ط§غŒ ظ†ظ…ط§غŒط´غŒ ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ {project_id}: {session[session_key]}")


@app.route("/project/<int:project_id>/treeview")
def project_treeview(project_id):
    """ظ†ظ…ط§غŒط´ ط¯ط±ط¨â€Œظ‡ط§غŒ ظ¾ط±ظˆعکظ‡ ط¯ط± ظ‚ط§ظ„ط¨ TreeView ظ¾غŒط´ط±ظپطھظ‡"""
    print(f"DEBUG: ++++ ط´ط±ظˆط¹ ط±ظˆطھ project_treeview ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ {project_id}")
    
    # ط¨ط±ط§غŒ ط§ط·ظ…غŒظ†ط§ظ† ط§ط² ط¹ط¯ظ… ع©ط´â€Œط´ط¯ظ†طŒ غŒع© ظ¾ط§ط±ط§ظ…طھط± ط²ظ…ط§ظ†غŒ ط§ط¶ط§ظپظ‡ ع©ظ†غŒظ…
    refresh_param = int(time.time())
    print(f"DEBUG: ظ¾ط§ط±ط§ظ…طھط± ط²ظ…ط§ظ†غŒ ط¨ط±ط§غŒ ط¬ظ„ظˆع¯غŒط±غŒ ط§ط² ع©ط´: {refresh_param}")
    
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash(f"ظ¾ط±ظˆعکظ‡ ط¨ط§ ID {project_id} غŒط§ظپطھ ظ†ط´ط¯.", "error")
        return redirect(url_for("index"))

    # طھظ†ط¸غŒظ… ظˆط¶ط¹غŒطھ ط§ظˆظ„غŒظ‡ ط³طھظˆظ†â€Œظ‡ط§ ط§ع¯ط± ظ„ط§ط²ظ… ط¨ط§ط´ط¯
    initialize_visible_columns(project_id)
    
    # ط¯ط±ط¨â€Œظ‡ط§ ط±ط§ ط§ط² ط¯غŒطھط§ط¨غŒط³ ط¯ط±غŒط§ظپطھ ظ…غŒâ€Œع©ظ†غŒظ… 
    doors = get_doors_for_project_db(project_id)
    print(f"DEBUG: ط¯ط±غŒط§ظپطھ {len(doors)} ط¯ط±ط¨ ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ {project_id}")
    
    # ط¯ط±غŒط§ظپطھ ط³طھظˆظ†â€Œظ‡ط§غŒ ظ‚ط§ط¨ظ„ ظ†ظ…ط§غŒط´ ط§ط² ط¬ظ„ط³ظ‡ ع©ط§ط±ط¨ط±
    visible_columns = session.get(f"visible_columns_{project_id}", [])
    print(f"DEBUG: ط³طھظˆظ†â€Œظ‡ط§غŒ ظ†ظ…ط§غŒط´غŒ ط§ط² ط¬ظ„ط³ظ‡: {visible_columns}")
    
    # ط¨ط±ط±ط³غŒ ط³ط±غŒط¹ ظ…ظ‚ط§ط¯غŒط± ط³ظپط§ط±ط´غŒ
    for door in doors[:5]:  # ظپظ‚ط· 5 ط¯ط±ط¨ ط§ظˆظ„ ط±ط§ ط¨ط±ط§غŒ ط¯غŒط¨ط§ع¯ ط¨ط±ط±ط³غŒ ظ…غŒâ€Œع©ظ†غŒظ…
        print(f"DEBUG: ط¯ط±ط¨ {door['id']} - ط±ظ†ع¯: {door.get('rang', 'ظ†ط¯ط§ط±ط¯')}, ظ†ظˆط¹ ظ¾ط±ظˆظپغŒظ„: {door.get('noe_profile', 'ظ†ط¯ط§ط±ط¯')}")
    
    return render_template(
        "project_treeview.html", 
        project=project_info, 
        doors=doors, 
        refresh_param=refresh_param,
        visible_columns=visible_columns
    )


@app.route("/project/<int:project_id>/door/<int:door_id>/set_color", methods=["POST"])
def set_door_color(project_id, door_id):
    """طھط؛غŒغŒط± ط±ظ†ع¯ غŒع© ط¯ط±ط¨"""
    color = request.form.get("color", "white")

    # ط§طھطµط§ظ„ ط¨ظ‡ ط¯غŒطھط§ط¨غŒط³
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط±ظ†ع¯ ط¯ط± ط¬ط¯ظˆظ„ ط¯ط±ط¨â€Œظ‡ط§
        cursor.execute(
            "UPDATE doors SET row_color_tag = ? WHERE id = ? AND project_id = ?",
            (color, door_id, project_id),
        )
        conn.commit()
        return jsonify({"success": True})
    except sqlite3.Error as e:
        print(f"ط®ط·ط§ ط¯ط± طھط؛غŒغŒط± ط±ظ†ع¯: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/project/<int:project_id>/delete_door/<int:door_id>", methods=["POST"])
def delete_door(project_id, door_id):
    """ط­ط°ظپ غŒع© ط¯ط±ط¨ ط§ط² ظ¾ط±ظˆعکظ‡"""
    print(f"DEBUG: ط¯ط±ط®ظˆط§ط³طھ ط¨ط±ط§غŒ ط­ط°ظپ ط¯ط±ط¨ ط¨ط§ ID {door_id} ط§ط² ظ¾ط±ظˆعکظ‡ {project_id}")
    
    # ط§طھطµط§ظ„ ط¨ظ‡ ط¯غŒطھط§ط¨غŒط³
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # ط§ط¨طھط¯ط§ ط¨ط±ط±ط³غŒ ظ…غŒâ€Œع©ظ†غŒظ… ع©ظ‡ ط¢غŒط§ ط¯ط±ط¨ ظ…طھط¹ظ„ظ‚ ط¨ظ‡ ط§غŒظ† ظ¾ط±ظˆعکظ‡ ط§ط³طھ
        cursor.execute(
            "SELECT id FROM doors WHERE id = ? AND project_id = ?",
            (door_id, project_id),
        )
        door = cursor.fetchone()
        
        if not door:
            print(f"ERROR: ط¯ط±ط¨ ط¨ط§ ID {door_id} ط¯ط± ظ¾ط±ظˆعکظ‡ {project_id} غŒط§ظپطھ ظ†ط´ط¯")
            return jsonify({"success": False, "error": "ط¯ط±ط¨ ظ…ظˆط±ط¯ ظ†ط¸ط± غŒط§ظپطھ ظ†ط´ط¯"}), 404
        
        # ط­ط°ظپ ظ…ظ‚ط§ط¯غŒط± ط³طھظˆظ†â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ ظ…ط±ط¨ظˆط· ط¨ظ‡ ط§غŒظ† ط¯ط±ط¨
        cursor.execute("DELETE FROM door_custom_values WHERE door_id = ?", (door_id,))
        
        # ط­ط°ظپ ط¯ط±ط¨ ط§ط² ط¬ط¯ظˆظ„ ط§طµظ„غŒ
        cursor.execute("DELETE FROM doors WHERE id = ?", (door_id,))
        
        conn.commit()
        print(f"DEBUG: ط¯ط±ط¨ ط¨ط§ ID {door_id} ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط­ط°ظپ ط´ط¯")
        return jsonify({"success": True})
    except sqlite3.Error as e:
        print(f"ERROR: ط®ط·ط§ ط¯ط± ط­ط°ظپ ط¯ط±ط¨: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route("/project/<int:project_id>/export/excel", methods=["GET"])
def export_to_excel(project_id):
    """ط®ط±ظˆط¬غŒ ط§ع©ط³ظ„ ط§ط² ط¯ط§ط¯ظ‡â€Œظ‡ط§غŒ ظ¾ط±ظˆعکظ‡"""
    import pandas as pd
    import os
    from datetime import datetime

    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("ظ¾ط±ظˆعکظ‡ ظ…ظˆط±ط¯ ظ†ط¸ط± غŒط§ظپطھ ظ†ط´ط¯.", "error")
        return redirect(url_for("index"))

    doors = get_doors_for_project_db(project_id)
    if not doors:
        flash("ظ‡غŒع† ط¯ط±ط¨غŒ ط¨ط±ط§غŒ ط§غŒظ† ظ¾ط±ظˆعکظ‡ ط«ط¨طھ ظ†ط´ط¯ظ‡ ط§ط³طھ.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # طھط¨ط¯غŒظ„ ط¨ظ‡ ط¯غŒطھط§ظپط±غŒظ… ظ¾ط§ظ†ط¯ط§ط³
    df = pd.DataFrame(doors)

    # طھظ†ط¸غŒظ… ظ…ط³غŒط± ظپط§غŒظ„ ط®ط±ظˆط¬غŒ
    export_dir = "static/exports"
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    customer_name = project_info.get("customer_name", "unknown")
    excel_filename = f"{customer_name}_{timestamp}.xlsx"
    excel_path = os.path.join(export_dir, excel_filename)

    # ط°ط®غŒط±ظ‡ ط¨ظ‡ ظپط§غŒظ„ ط§ع©ط³ظ„
    df.to_excel(excel_path, index=False)

    # ط§ط±ط³ط§ظ„ ظپط§غŒظ„ ط¨ظ‡ ع©ط§ط±ط¨ط±
    return send_file(excel_path, as_attachment=True)


@app.route("/project/<int:project_id>/calculate_cutting", methods=["GET"])
def calculate_cutting(project_id):
    """ظ…ط­ط§ط³ط¨ظ‡ ط¨ط±ط´ ط¨ظ‡غŒظ†ظ‡ ط¨ط§ ظ¾غŒط´â€Œظ¾ط±ط¯ط§ط²ط´ ظ…ظ‚ط§ط¯غŒط± ط¨ط±ط§غŒ ظ‚ط§ظ„ط¨"""
    STOCK_LENGTH = 600  # ط·ظˆظ„ ط§ط³طھط§ظ†ط¯ط§ط±ط¯ ط´ط§ط®ظ‡
    WEIGHT_PER_METER = 1.9  # ظˆط²ظ† ظ‡ط± ظ…طھط±
    WASTE_THRESHOLD = 70  # ط¢ط³طھط§ظ†ظ‡ ط¶ط§غŒط¹ط§طھ ع©ظˆع†ع© (ط³ط§ظ†طھغŒâ€Œظ…طھط±)

    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("ظ¾ط±ظˆعکظ‡ ظ…ظˆط±ط¯ ظ†ط¸ط± غŒط§ظپطھ ظ†ط´ط¯.", "error")
        return redirect(url_for("index"))

    doors = get_doors_for_project_db(project_id)
    if not doors:
        flash("ظ‡غŒع† ط¯ط±ط¨غŒ ط¨ط±ط§غŒ ط§غŒظ† ظ¾ط±ظˆعکظ‡ ط«ط¨طھ ظ†ط´ط¯ظ‡ ط§ط³طھ.", "warning")
        return redirect(url_for("view_project", project_id=project_id))

    # --- ط¬ظ…ط¹â€Œط¢ظˆط±غŒ ظ‚ط·ط¹ط§طھ ظ…ظˆط±ط¯ ظ†غŒط§ط² ---
    required_pieces = []  # ظ„غŒط³طھ (ط·ظˆظ„طŒ طھط¹ط¯ط§ط¯)

    valid_rows = 0
    for door in doors:
        try:
            width = float(door["width"])
            height = float(door["height"])
            quantity = int(door["quantity"])

            if width <= 0 or height <= 0 or quantity <= 0:
                continue  # ط±ط¯ ع©ط±ط¯ظ† ط¯ط§ط¯ظ‡â€Œظ‡ط§غŒ ظ†ط§ظ…ط¹طھط¨ط±

            # ظ…ط­ط§ط³ط¨ظ‡ ظ…ط´ط§ط¨ظ‡ ظ†ط³ط®ظ‡ ط¯ط³ع©طھط§ظ¾
            # ط¯ظˆ ظ‚ط·ط¹ظ‡ ط¹ظ…ظˆط¯غŒ ط¨ط±ط§غŒ ظ‡ط± ط¯ط±ط¨
            required_pieces.append((height, quantity * 2))
            # غŒع© ظ‚ط·ط¹ظ‡ ط§ظپظ‚غŒ ط¨ط±ط§غŒ ظ‡ط± ط¯ط±ط¨
            required_pieces.append((width, quantity * 1))

            valid_rows += 1

        except (ValueError, TypeError, KeyError) as e:
            print(f"ط®ط·ط§ ط¯ط± ظ¾ط±ط¯ط§ط²ط´ ط¯ط±ط¨ {door.get('id')}: {e}")
            continue

    if not required_pieces:
        flash(
            "ظ‡غŒع† ط¯ط±ط¨ ظ…ط¹طھط¨ط±غŒ (ط¨ط§ ط¹ط±ط¶طŒ ط§ط±طھظپط§ط¹ ظˆ طھط¹ط¯ط§ط¯ ط¹ط¯ط¯غŒ ظ…ط«ط¨طھ) ط¯ط± ط¬ط¯ظˆظ„ ط¨ط±ط§غŒ ظ…ط­ط§ط³ط¨ظ‡ ط¨ط±ط´ غŒط§ظپطھ ظ†ط´ط¯.",
            "warning",
        )
        return redirect(url_for("view_project", project_id=project_id))

    if valid_rows < len(doors):
        flash(
            "ط¨ط±ط®غŒ ط±ط¯غŒظپâ€Œظ‡ط§ ط¨ظ‡ ط¯ظ„غŒظ„ ط¯ط§ط´طھظ† ظ…ظ‚ط§ط¯غŒط± ظ†ط§ظ…ط¹طھط¨ط± (ط؛غŒط±ط¹ط¯ط¯غŒ غŒط§ طµظپط±) ط¯ط± ط¹ط±ط¶طŒ ط§ط±طھظپط§ط¹ غŒط§ طھط¹ط¯ط§ط¯طŒ ط¯ط± ظ…ط­ط§ط³ط¨ظ‡ ظ†ط§ط¯غŒط¯ظ‡ ع¯ط±ظپطھظ‡ ط´ط¯ظ†ط¯.",
            "warning",
        )

    # --- ط§ظ„ع¯ظˆط±غŒطھظ… ط¨ط³طھظ‡â€Œط¨ظ†ط¯غŒ (First Fit Decreasing) ---
    bins = []  # ظ‡ط± ط´ط§ط®ظ‡ ط¨ظ‡ طµظˆط±طھ: {"pieces": [], "remaining": float}

    # طھط¨ط¯غŒظ„ ط¨ظ‡ ظ„غŒط³طھ طµط§ظپ: [(length1, 1), (length1, 1), ... (length2, 1), ...]
    flat_pieces = []
    for length, count in required_pieces:
        flat_pieces.extend([length] * count)

    # ظ…ط±طھط¨â€Œط³ط§ط²غŒ ظ†ط²ظˆظ„غŒ ط¨ط±ط§ط³ط§ط³ ط·ظˆظ„
    sorted_pieces = sorted(flat_pieces, reverse=True)

    for piece_length in sorted_pieces:
        if piece_length > STOCK_LENGTH:
            flash(
                f"ط§ظ…ع©ط§ظ† ط¨ط±ط´ ظ‚ط·ط¹ظ‡â€Œط§غŒ ط¨ظ‡ ط·ظˆظ„ {piece_length}cm ط§ط² ط´ط§ط®ظ‡ {STOCK_LENGTH}cm ظˆط¬ظˆط¯ ظ†ط¯ط§ط±ط¯!",
                "error",
            )
            return redirect(url_for("view_project", project_id=project_id))

        placed = False
        # ط³ط¹غŒ ط¯ط± ظ‚ط±ط§ط± ط¯ط§ط¯ظ† ط¯ط± ط´ط§ط®ظ‡â€Œظ‡ط§غŒ ظ…ظˆط¬ظˆط¯
        for bin_data in bins:
            if bin_data["remaining"] >= piece_length:
                bin_data["pieces"].append(piece_length)
                bin_data["remaining"] -= piece_length
                placed = True
                break

        # ط§ع¯ط± ط¯ط± ظ‡غŒع† ط´ط§ط®ظ‡â€Œط§غŒ ط¬ط§ ظ†ط´ط¯طŒ غŒع© ط´ط§ط®ظ‡ ط¬ط¯غŒط¯ ط§غŒط¬ط§ط¯ ع©ظ†
        if not placed:
            bins.append(
                {"pieces": [piece_length], "remaining": STOCK_LENGTH - piece_length}
            )

    # --- ظ…ط­ط§ط³ط¨ظ‡ ط¢ظ…ط§ط± ---
    total_bins_used = len(bins)

    # ط§ط·ظ„ط§ط¹ط§طھ ظ‚ط·ط¹ط§طھ ع©ظˆع†ع© (ط¶ط§غŒط¹ط§طھ)
    small_pieces_info = [
        (i + 1, bin_data["remaining"])
        for i, bin_data in enumerate(bins)
        if 0 < bin_data["remaining"] < WASTE_THRESHOLD
    ]
    small_pieces_count = len(small_pieces_info)
    total_small_waste_length = sum(rem for _, rem in small_pieces_info)
    total_small_waste_weight = (
        total_small_waste_length / 100
    ) * WEIGHT_PER_METER  # طھط¨ط¯غŒظ„ ط³ط§ظ†طھغŒâ€Œظ…طھط± ط¨ظ‡ ظ…طھط±

    # ظ…ط´ط§ظ‡ط¯ظ‡ ط§ط·ظ„ط§ط¹ط§طھ ط¶ط§غŒط¹ط§طھ ظ…طھظˆط³ط· ظˆ ط¨ط²ط±ع¯ ط¨ط±ط§غŒ طھط­ظ„غŒظ„ ط¨غŒط´طھط±
    medium_pieces_info = [
        (i + 1, bin_data["remaining"])
        for i, bin_data in enumerate(bins)
        if WASTE_THRESHOLD <= bin_data["remaining"] < (STOCK_LENGTH / 2)
    ]
    large_pieces_info = [
        (i + 1, bin_data["remaining"])
        for i, bin_data in enumerate(bins)
        if (STOCK_LENGTH / 2) <= bin_data["remaining"] < STOCK_LENGTH
    ]

    medium_pieces_count = len(medium_pieces_info)
    large_pieces_count = len(large_pieces_info)
    total_medium_waste_length = sum(rem for _, rem in medium_pieces_info)
    total_large_waste_length = sum(rem for _, rem in large_pieces_info)

    # ظ…ط­ط§ط³ط¨ظ‡ ع©ظ„ ط¶ط§غŒط¹ط§طھ
    total_waste_length = sum(bin_data["remaining"] for bin_data in bins)
    total_waste_weight = (total_waste_length / 100) * WEIGHT_PER_METER
    total_waste_percentage = (
        total_waste_length / (STOCK_LENGTH * total_bins_used)
    ) * 100

    # ---------- ظ¾غŒط´â€Œظ¾ط±ط¯ط§ط²ط´ ط¯ط§ط¯ظ‡â€Œظ‡ط§ ط¨ط±ط§غŒ ظ‚ط§ظ„ط¨ ----------
    # ط§غŒظ† ط¨ط®ط´ ط¨ظ‡ ظ…ظ†ط¸ظˆط± ط¬ظ„ظˆع¯غŒط±غŒ ط§ط² ط®ط·ط§غŒ ط³غŒظ†طھع©ط³غŒ ط¯ط± ظ‚ط§ظ„ط¨ ط§ط¶ط§ظپظ‡ ط´ط¯ظ‡ ط§ط³طھ

    # ع¯ط±ط¯ ع©ط±ط¯ظ† ظ…ظ‚ط§ط¯غŒط± ط§طµظ„غŒ
    small_waste_length_rounded = round(total_small_waste_length, 1)
    small_waste_weight_rounded = round(total_small_waste_weight, 2)
    total_waste_percentage_rounded = round(total_waste_percentage, 1)

    # ظ¾غŒط´â€Œظ¾ط±ط¯ط§ط²ط´ ط¯ط§ط¯ظ‡â€Œظ‡ط§غŒ ط´ط§ط®ظ‡â€Œظ‡ط§
    processed_bins = []
    for i, bin_data in enumerate(bins):
        used_length = STOCK_LENGTH - bin_data["remaining"]
        used_percent = int((used_length / STOCK_LENGTH) * 100)
        waste_percent = int((bin_data["remaining"] / STOCK_LENGTH) * 100)
        # ظپط±ظ…طھâ€Œط¨ظ†ط¯غŒ ط¯ط±طµط¯ظ‡ط§ ط¨ظ‡ طµظˆط±طھ ط±ط´طھظ‡â€Œط§غŒ ط¨ط§ % ط¨ط±ط§غŒ CSS
        used_percent_style = f"{used_percent}%"
        waste_percent_style = f"{waste_percent}%"
        # ع¯ط±ط¯ ع©ط±ط¯ظ† ط§ط¹ط¯ط§ط¯ ظ‚ط·ط¹ط§طھ
        rounded_pieces = [round(piece, 1) for piece in bin_data["pieces"]]

        processed_bins.append(
            {
                "index": i + 1,
                "pieces": [round(piece, 1) for piece in bin_data["pieces"]],
                "remaining": round(bin_data["remaining"], 1),
                "used_length": round(used_length, 1),
                "used_percent": used_percent,
                "waste_percent": waste_percent,
                "used_percent_style": used_percent_style,  # ط§غŒظ† ط®ط· ط§ط¶ط§ظپظ‡ ط´ط¯ظ‡
                "waste_percent_style": waste_percent_style,  # ط§غŒظ† ط®ط· ط§ط¶ط§ظپظ‡ ط´ط¯ظ‡
                "waste_type": (
                    "small"
                    if bin_data["remaining"] < WASTE_THRESHOLD
                    else (
                        "medium"
                        if bin_data["remaining"] < (STOCK_LENGTH / 2)
                        else "large"
                    )
                ),
            }
        )
    # ط±ظ†ط¯ط± ظ†طھغŒط¬ظ‡ ط¯ط± ظ‚ط§ظ„ط¨ HTML ط¨ط§ ظ…ظ‚ط§ط¯غŒط± ط§ط² ظ¾غŒط´ ظ…ط­ط§ط³ط¨ظ‡ ط´ط¯ظ‡
    return render_template(
        "cutting_result.html",
        project=project_info,
        bins=processed_bins,
        total_bins=total_bins_used,
        stock_length=STOCK_LENGTH,
        waste_threshold=WASTE_THRESHOLD,
        small_pieces_count=small_pieces_count,
        small_waste_length=small_waste_length_rounded,
        small_waste_weight=small_waste_weight_rounded,
        medium_pieces_count=medium_pieces_count,
        medium_waste_length=round(total_medium_waste_length, 1),
        large_pieces_count=large_pieces_count,
        large_waste_length=round(total_large_waste_length, 1),
        total_waste_length=round(total_waste_length, 1),
        total_waste_weight=round(total_waste_weight, 2),
        total_waste_percentage=total_waste_percentage_rounded,
    )


@app.route("/project/<int:project_id>/batch_edit", methods=["GET"])
def batch_edit_form(project_id):
    """ظ†ظ…ط§غŒط´ ظپط±ظ… ظˆغŒط±ط§غŒط´ ع¯ط±ظˆظ‡غŒ"""
    door_ids = request.args.get("door_ids")
    if not door_ids:
        flash("ظ‡غŒع† ط¯ط±ط¨غŒ ط¨ط±ط§غŒ ظˆغŒط±ط§غŒط´ ط§ظ†طھط®ط§ط¨ ظ†ط´ط¯ظ‡ ط§ط³طھ.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # طھط¨ط¯غŒظ„ ط±ط´طھظ‡ ط¨ظ‡ ظ„غŒط³طھ
    door_ids = door_ids.split(",")

    # ط¨ط§ط²غŒط§ط¨غŒ ط§ط·ظ„ط§ط¹ط§طھ ظ¾ط§غŒظ‡
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("ظ¾ط±ظˆعکظ‡ ظ…ظˆط±ط¯ ظ†ط¸ط± غŒط§ظپطھ ظ†ط´ط¯.", "error")
        return redirect(url_for("index"))

    # ط¯ط±غŒط§ظپطھ ظˆط¶ط¹غŒطھ ط³طھظˆظ†â€Œظ‡ط§غŒ ظ†ظ…ط§غŒط´غŒ ط§ط² ط¬ظ„ط³ظ‡
    visible_columns = session.get(f"visible_columns_{project_id}", [])
    print(f"DEBUG: ط³طھظˆظ†â€Œظ‡ط§غŒ ظ†ظ…ط§غŒط´غŒ ط¨ط±ط§غŒ ظ¾ط±ظˆعکظ‡ {project_id}: {visible_columns}")

    # ط¯ط±غŒط§ظپطھ ع¯ط²غŒظ†ظ‡â€Œظ‡ط§غŒ ط³طھظˆظ†â€Œظ‡ط§غŒ ظ‚ط§ط¨ظ„ ظˆغŒط±ط§غŒط´
    columns_info = get_active_custom_columns()
    column_options = {}

    # ع¯ط²غŒظ†ظ‡â€Œظ‡ط§غŒ ظ¾غŒط´â€Œظپط±ط¶ ط¨ط± ط§ط³ط§ط³ cutting_tool.py
    default_options = {
        "rang": ["ط³ظپغŒط¯", "ط¢ظ†ط§ط¯ط§غŒط²"],
        "noe_profile": [
            "ظپط±غŒظ… ظ„ط³ ط¢ظ„ظˆظ…غŒظ†غŒظˆظ…غŒ",
            "ظپط±غŒظ… ظ‚ط¯غŒظ…غŒ",
            "ظپط±غŒظ… ط¯ط§ط®ظ„ ع†ظˆط¨ ط¯ط§ط±",
            "ط¯ط§ط®ظ„ ع†ظˆط¨ ط¯ط§ط± ط¯ظˆ ط¢ظ„ظˆظ…غŒظ†غŒظˆظ… ط¯ط±ط¨",
        ],
        "vaziat": [
            "ظ‡ظ…ط²ظ…ط§ظ† ط¨ط§ طھظˆظ„غŒط¯ ع†ظ‡ط§ط±ع†ظˆط¨",
            "طھظˆظ„غŒط¯ ط¯ط±ط¨ ط¯ط± ط¢غŒظ†ط¯ظ‡",
            "ط¨ط¯ظˆظ† ط¯ط±ط¨",
        ],
        "lola": ["OTLAV", "HTH", "NHN", "ظ…طھظپط±ظ‚ظ‡"],
        "ghofl": ["STV", "ط§غŒط²ط¯ظˆ", "NHN", "HTN"],
        "accessory": [
            "ط¢ظ„ظˆظ…غŒظ†غŒظˆظ… ط¢ط³طھط§ظ†ظ‡ ظپط§ظ‚ ظˆ ط²ط¨ط§ظ†ظ‡",
            "ط¢ط±ط§ظ…ط¨ظ†ط¯ ظ…ط±ظˆظ†غŒ",
            "ظ‚ظپظ„ ط¨ط±ظ‚ ط³ط§ط±ظˆ ط¨ط§ ظپظ†ط±",
            "ط¢ط±ط§ظ…ط¨ظ†ط¯ NHN",
        ],
        "kolaft": ["ط¯ظˆ ط·ط±ظپظ‡", "ط³ظ‡ ط·ط±ظپظ‡"],
        "dastgire": ["ط¯ظˆ طھغŒع©ظ‡", "ط§غŒط²ط¯ظˆ", "ع¯ط±غŒظپ ظˆط±ع©", "ظ…طھظپط±ظ‚ظ‡"],
    }

    # ط¨ط±ط§غŒ ظ‡ط± ط³طھظˆظ†طŒ ع¯ط²غŒظ†ظ‡â€Œظ‡ط§غŒ ط¢ظ† ط±ط§ ط¯ط±غŒط§ظپطھ ع©ظ†غŒظ…
    for column in columns_info:
        column_key = column["key"]
        # طھط±ع©غŒط¨ ع¯ط²غŒظ†ظ‡â€Œظ‡ط§غŒ ظ¾غŒط´â€Œظپط±ط¶ ط¨ط§ ع¯ط²غŒظ†ظ‡â€Œظ‡ط§غŒ ط¯غŒطھط§ط¨غŒط³
        options = []
        
        # ط§ع¯ط± ع¯ط²غŒظ†ظ‡â€Œظ‡ط§غŒ ظ¾غŒط´â€Œظپط±ط¶ ط¨ط±ط§غŒ ط§غŒظ† ط³طھظˆظ† ظˆط¬ظˆط¯ ط¯ط§ط±ط¯
        if column_key in default_options:
            options = default_options[column_key]
        else:
            # ع¯ط²غŒظ†ظ‡â€Œظ‡ط§غŒ ط¯غŒطھط§ط¨غŒط³ ط±ط§ ط¯ط±غŒط§ظپطھ ع©ظ†غŒظ…
            db_options = get_custom_column_options(column["id"])
            if db_options:
                options = db_options
        
        # ط¨ط±ط±ط³غŒ ظˆط¶ط¹غŒطھ ظ†ظ…ط§غŒط´ ط³طھظˆظ†
        is_visible = column_key in visible_columns
        
        column_options[column_key] = {
            "display": column["display"],
            "options": options,
            "visible": is_visible  # ظˆط¶ط¹غŒطھ ظ†ظ…ط§غŒط´ ط³طھظˆظ†
        }
        
    # ط§ظپط²ظˆط¯ظ† ظ¾ط§ط±ط§ظ…طھط± ط²ظ…ط§ظ†غŒ ط¨ط±ط§غŒ ط¬ظ„ظˆع¯غŒط±غŒ ط§ط² ع©ط´ ط´ط¯ظ† طµظپط­ظ‡
    timestamp = int(time.time())

    return render_template(
        "batch_edit.html",
        project=project_info,
        door_ids=door_ids,
        column_options=column_options,
        visible_columns=visible_columns,
        timestamp=timestamp
    )


@app.route("/project/<int:project_id>/batch_edit", methods=["POST"])
def apply_batch_edit(project_id):
    """ط§ط¹ظ…ط§ظ„ طھط؛غŒغŒط±ط§طھ ع¯ط±ظˆظ‡غŒ ط±ظˆغŒ ط¯ط±ط¨â€Œظ‡ط§غŒ ط§ظ†طھط®ط§ط¨ ط´ط¯ظ‡"""
    door_ids = request.form.get("door_ids")
    if not door_ids:
        flash("ظ‡غŒع† ط¯ط±ط¨غŒ ط¨ط±ط§غŒ ظˆغŒط±ط§غŒط´ ط§ظ†طھط®ط§ط¨ ظ†ط´ط¯ظ‡ ط§ط³طھ.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    door_ids = door_ids.split(",")

    # ط¨ط±ط±ط³غŒ ط§غŒظ†ع©ظ‡ ع©ط¯ط§ظ… ط³طھظˆظ†â€Œظ‡ط§ ط¨ط§غŒط¯ ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط´ظˆظ†ط¯
    columns_to_update = {}
    for key, value in request.form.items():
        # ط§ع¯ط± غŒع© checkbox ط¨ط±ط§غŒ ط³طھظˆظ† ظپط¹ط§ظ„ ط¨ظˆط¯ ظˆ ظ…ظ‚ط¯ط§ط± ظˆط§ط±ط¯ ط´ط¯ظ‡ ط¨ظˆط¯
        if key.startswith("update_") and value == "on":
            column_key = key.replace("update_", "")
            if f"value_{column_key}" in request.form:
                new_value = request.form.get(f"value_{column_key}")
                columns_to_update[column_key] = new_value

    if not columns_to_update:
        flash("ظ‡غŒع† ظپغŒظ„ط¯غŒ ط¨ط±ط§غŒ ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط§ظ†طھط®ط§ط¨ ظ†ط´ط¯ظ‡ ط§ط³طھ.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # ط§ط¹ظ…ط§ظ„ طھط؛غŒغŒط±ط§طھ ط±ظˆغŒ ط¯ط±ط¨â€Œظ‡ط§غŒ ط§ظ†طھط®ط§ط¨ ط´ط¯ظ‡
    update_count = 0
    print(f"DEBUG: ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ {len(door_ids)} ط¯ط±ط¨ ط¨ط§ ط³طھظˆظ†â€Œظ‡ط§غŒ: {columns_to_update}")
    
    for door_id in door_ids:
        try:
            door_id = int(door_id)
            
            # ط¨ط±ط§غŒ ظ‡ط± ط³طھظˆظ†طŒ ظ…ظ‚ط¯ط§ط± ط¬ط¯غŒط¯ ط±ط§ ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ع©ظ†غŒظ…
            for column_key, new_value in columns_to_update.items():
                # ظ¾غŒط¯ط§ ع©ط±ط¯ظ† ID ط³طھظˆظ†
                column_id = get_column_id_by_key(column_key)
                print(f"DEBUG: ط³طھظˆظ† '{column_key}' ط¨ط§ ID={column_id}, ظ…ظ‚ط¯ط§ط± ط¬ط¯غŒط¯='{new_value}'")
                
                if column_id:
                    result = update_door_custom_value(door_id, column_id, new_value)
                    print(f"DEBUG: ظ†طھغŒط¬ظ‡ ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط³طھظˆظ† '{column_key}' ط¨ط±ط§غŒ ط¯ط±ط¨ {door_id}: {result}")
                else:
                    print(f"ERROR: ط³طھظˆظ† ط¨ط§ ع©ظ„غŒط¯ '{column_key}' غŒط§ظپطھ ظ†ط´ط¯")

            update_count += 1

        except Exception as e:
            print(f"ERROR ط¯ط± ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط¯ط±ط¨ {door_id}: {e}")
            traceback.print_exc()

    if update_count > 0:
        flash(f"{update_count} ط¯ط±ط¨ ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط´ط¯.", "success")
    else:
        flash("ط®ط·ط§ ط¯ط± ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط¯ط±ط¨â€Œظ‡ط§.", "error")

    # ط§ظپط²ظˆط¯ظ† ظ¾ط§ط±ط§ظ…طھط± ط²ظ…ط§ظ†غŒ ط¨ط±ط§غŒ ط¬ظ„ظˆع¯غŒط±غŒ ط§ط² ع©ط´ ط´ط¯ظ† طµظپط­ظ‡
    timestamp = int(time.time())
    return redirect(url_for("project_treeview", project_id=project_id, t=timestamp))


@app.route("/project/<int:project_id>/toggle_column_display", methods=["POST"])
def toggle_column_display(project_id):
    """طھط؛غŒغŒط± ظˆط¶ط¹غŒطھ ظ†ظ…ط§غŒط´ ط³طھظˆظ† ط¯ط± ط¬ظ„ط³ظ‡ ع©ط§ط±ط¨ط±"""
    column_key = request.form.get("column_key")
    is_visible = request.form.get("is_visible") == "1"
    
    print(f"DEBUG: طھط؛غŒغŒط± ظˆط¶ط¹غŒطھ ظ†ظ…ط§غŒط´ ط³طھظˆظ† '{column_key}' ط¨ظ‡ {is_visible}")
    
    # ط°ط®غŒط±ظ‡ ظˆط¶ط¹غŒطھ ظ†ظ…ط§غŒط´ ط³طھظˆظ† ط¯ط± ط¬ظ„ط³ظ‡ ع©ط§ط±ط¨ط±
    session_key = f"visible_columns_{project_id}"
    visible_columns = session.get(session_key, [])
    
    if is_visible and column_key not in visible_columns:
        visible_columns.append(column_key)
        print(f"DEBUG: ط³طھظˆظ† '{column_key}' ط¨ظ‡ ظ„غŒط³طھ ظ†ظ…ط§غŒط´ ط§ط¶ط§ظپظ‡ ط´ط¯")
    elif not is_visible and column_key in visible_columns:
        visible_columns.remove(column_key)
        print(f"DEBUG: ط³طھظˆظ† '{column_key}' ط§ط² ظ„غŒط³طھ ظ†ظ…ط§غŒط´ ط­ط°ظپ ط´ط¯")
    
    session[session_key] = visible_columns
    print(f"DEBUG: ظ„غŒط³طھ ط³طھظˆظ†â€Œظ‡ط§غŒ ظ†ظ…ط§غŒط´غŒ ط¨ظ‡â€Œط±ظˆط² ط´ط¯: {visible_columns}")
    
    return jsonify({"success": True})


@app.route("/settings/columns/<int:project_id>")
def settings_columns(project_id):
    """طµظپط­ظ‡ طھظ†ط¸غŒظ…ط§طھ ط³طھظˆظ†â€Œظ‡ط§"""
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("ظ¾ط±ظˆعکظ‡ ظ…ظˆط±ط¯ ظ†ط¸ط± غŒط§ظپطھ ظ†ط´ط¯.", "error")
        return redirect(url_for("index"))

    # ط¯ط±غŒط§ظپطھ ط§ط·ظ„ط§ط¹ط§طھ ظ‡ظ…ظ‡ ط³طھظˆظ†â€Œظ‡ط§ (ظ¾ط§غŒظ‡ ظˆ ط³ظپط§ط±ط´غŒ)
    all_columns = get_all_custom_columns()

    return render_template(
        "settings_columns.html", project=project_info, columns=all_columns
    )


@app.route("/settings/add_custom_column/<int:project_id>", methods=["POST"])
def add_custom_column_route(project_id):
    """ط§ظپط²ظˆط¯ظ† ط³طھظˆظ† ط³ظپط§ط±ط´غŒ ط¬ط¯غŒط¯"""
    display_name = request.form.get("display_name")
    if not display_name:
        flash("ظ†ط§ظ… ظ†ظ…ط§غŒط´غŒ ط³طھظˆظ† ظ†ظ…غŒâ€Œطھظˆط§ظ†ط¯ ط®ط§ظ„غŒ ط¨ط§ط´ط¯.", "error")
        return redirect(url_for("settings_columns", project_id=project_id))

    # طھظˆظ„غŒط¯ ظ†ط§ظ… ع©ظ„غŒط¯ ط¯ط§ط®ظ„غŒ ط¨ط±ط§ط³ط§ط³ ظ†ط§ظ… ظ†ظ…ط§غŒط´غŒ
    internal_key = "".join(c if c.isalnum() else "_" for c in display_name.lower())

    # ط¨ط±ط±ط³غŒ غŒع©طھط§ ط¨ظˆط¯ظ† ع©ظ„غŒط¯
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT column_name FROM custom_columns")
    existing_keys = [row[0] for row in cursor.fetchall()]
    conn.close()

    # ط§ع¯ط± ع©ظ„غŒط¯ طھع©ط±ط§ط±غŒ ط¨ظˆط¯طŒ ظ¾ط³ظˆظ†ط¯ ط§ط¶ط§ظپظ‡ ع©ظ†غŒظ…
    base_key = internal_key
    counter = 1
    while internal_key in existing_keys:
        internal_key = f"{base_key}_{counter}"
        counter += 1

    # ط§ظپط²ظˆط¯ظ† ط³طھظˆظ† ط¬ط¯غŒط¯
    try:
        new_id = add_custom_column(internal_key, display_name)
        if new_id:
            flash(f"ط³طھظˆظ† '{display_name}' ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط§ط¶ط§ظپظ‡ ط´ط¯.", "success")
        else:
            flash("ط®ط·ط§ ط¯ط± ط§ظپط²ظˆط¯ظ† ط³طھظˆظ† ط¬ط¯غŒط¯.", "error")
    except Exception as e:
        flash(f"ط®ط·ط§ ط¯ط± ط§ظپط²ظˆط¯ظ† ط³طھظˆظ† ط¬ط¯غŒط¯: {e}", "error")

    return redirect(url_for("settings_columns", project_id=project_id))


@app.route("/settings/toggle_column/<int:column_id>", methods=["POST"])
def toggle_column_status(column_id):
    """طھط؛غŒغŒط± ظˆط¶ط¹غŒطھ ظپط¹ط§ظ„/ط؛غŒط±ظپط¹ط§ظ„ ط³طھظˆظ†"""
    is_active = request.form.get("is_active", "0") == "1"

    try:
        success = update_custom_column_status(column_id, is_active)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "ط®ط·ط§ ط¯ط± ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ظˆط¶ط¹غŒطھ ط³طھظˆظ†"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/settings/update_column_name/<int:column_id>", methods=["POST"])
def update_column_name(column_id):
    """ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ظ†ط§ظ… ظ†ظ…ط§غŒط´غŒ ط³طھظˆظ†"""
    display_name = request.form.get("display_name")
    project_id = request.args.get("project_id")

    if not display_name:
        flash("ظ†ط§ظ… ظ†ظ…ط§غŒط´غŒ ط³طھظˆظ† ظ†ظ…غŒâ€Œطھظˆط§ظ†ط¯ ط®ط§ظ„غŒ ط¨ط§ط´ط¯.", "error")
        return redirect(url_for("settings_columns", project_id=project_id))

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE custom_columns SET display_name = ? WHERE id = ?",
            (display_name, column_id),
        )
        conn.commit()
        conn.close()
        flash(f"ظ†ط§ظ… ط³طھظˆظ† ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط¨ظ‡ '{display_name}' طھط؛غŒغŒط± غŒط§ظپطھ.", "success")
    except Exception as e:
        flash(f"ط®ط·ط§ ط¯ط± ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ظ†ط§ظ… ط³طھظˆظ†: {e}", "error")

    return redirect(url_for("settings_columns", project_id=project_id))


@app.route("/settings/delete_column/<int:column_id>")
def delete_column_route(column_id):
    """ط­ط°ظپ ط³طھظˆظ† ط³ظپط§ط±ط´غŒ"""
    project_id = request.args.get("redirect_to")

    try:
        # ط§ط¨طھط¯ط§ ط¨ط§غŒط¯ ط¨ط±ط±ط³غŒ ع©ظ†غŒظ… ع©ظ‡ ط¢غŒط§ ط³طھظˆظ† ط§ط² ط³طھظˆظ†â€Œظ‡ط§غŒ ظ¾ط§غŒظ‡ ط­غŒط§طھغŒ ظ†غŒط³طھ
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT column_name FROM custom_columns WHERE id = ?", (column_id,)
        )
        column_data = cursor.fetchone()

        if column_data:
            column_key = column_data[0]
            # ط¨ط±ط®غŒ ط³طھظˆظ†â€Œظ‡ط§غŒ ظ¾ط§غŒظ‡ ع©ظ‡ ظ†ط¨ط§غŒط¯ ط­ط°ظپ ط´ظˆظ†ط¯
            critical_base_keys = ["rang", "noe_profile", "vaziat", "tozihat"]

            if column_key in critical_base_keys:
                flash(
                    f"ط³طھظˆظ† '{column_key}' غŒع© ط³طھظˆظ† ظ¾ط§غŒظ‡ ط§ط³طھ ظˆ ظ†ظ…غŒâ€Œطھظˆط§ظ†ط¯ ط­ط°ظپ ط´ظˆط¯.", "error"
                )
                return redirect(url_for("settings_columns", project_id=project_id))

            # ط­ط°ظپ ط³طھظˆظ†
            cursor.execute("DELETE FROM custom_columns WHERE id = ?", (column_id,))
            conn.commit()
            conn.close()

            flash("ط³طھظˆظ† ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط­ط°ظپ ط´ط¯.", "success")
        else:
            flash("ط³طھظˆظ† ظ…ظˆط±ط¯ ظ†ط¸ط± غŒط§ظپطھ ظ†ط´ط¯.", "error")
    except Exception as e:
        flash(f"ط®ط·ط§ ط¯ط± ط­ط°ظپ ط³طھظˆظ†: {e}", "error")


@app.route("/project/<int:project_id>/update", methods=["POST"])
def update_project(project_id):
    """ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط§ط·ظ„ط§ط¹ط§طھ غŒع© ظ¾ط±ظˆعکظ‡"""
    print(f"DEBUG: ظˆط±ظˆط¯ ط¨ظ‡ route ط¨ط±ظˆط²ط±ط³ط§ظ†غŒ ظ¾ط±ظˆعکظ‡ ط¨ط§ ID: {project_id}")
    
    customer_name = request.form.get("customer_name", "")
    order_ref = request.form.get("order_ref", "")
    date_shamsi = request.form.get("date_shamsi", "")
    
    print(f"DEBUG: ط§ط·ظ„ط§ط¹ط§طھ ط¯ط±غŒط§ظپطھغŒ ط§ط² ظپط±ظ… - ظ…ط´طھط±غŒ: {customer_name}, ط³ظپط§ط±ط´: {order_ref}, طھط§ط±غŒط®: {date_shamsi}")
    
    success = update_project_db(project_id, customer_name, order_ref, date_shamsi)
    
    if success:
        flash("ط§ط·ظ„ط§ط¹ط§طھ ظ¾ط±ظˆعکظ‡ ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط´ط¯", "success")
    else:
        flash("ط®ط·ط§ ط¯ط± ط¨ظ‡â€Œط±ظˆط²ط±ط³ط§ظ†غŒ ط§ط·ظ„ط§ط¹ط§طھ ظ¾ط±ظˆعکظ‡", "error")
    
    return redirect(url_for("view_project", project_id=project_id))


@app.route("/project/<int:project_id>/delete", methods=["POST"])
def delete_project(project_id):
    """ط­ط°ظپ غŒع© ظ¾ط±ظˆعکظ‡ ط§ط² ط¯غŒطھط§ط¨غŒط³"""
    print(f"DEBUG: ظˆط±ظˆط¯ ط¨ظ‡ route ط­ط°ظپ ظ¾ط±ظˆعکظ‡ ط¨ط§ ID: {project_id}")
    
    success = delete_project_db(project_id)
    
    if success:
        flash("ظ¾ط±ظˆعکظ‡ ط¨ط§ ظ…ظˆظپظ‚غŒطھ ط­ط°ظپ ط´ط¯", "success")
    else:
        flash("ط®ط·ط§ ط¯ط± ط­ط°ظپ ظ¾ط±ظˆعکظ‡", "error")
    
    return redirect(url_for("index"))


def fix_persian_text(text):
    """طھط¨ط¯غŒظ„ ظ…طھظ† ظپط§ط±ط³غŒ ط¨ط±ط§غŒ ظ†ظ…ط§غŒط´ طµط­غŒط­ ط¯ط± PDF"""
    if not text:
        return ""
    reshaped_text = arabic_reshaper.reshape(str(text))
    return get_display(reshaped_text)


@app.route("/project/<int:project_id>/export_pdf", methods=["GET"])
def export_table_to_pdf_web(project_id):
    """ط®ط±ظˆط¬غŒ PDF ط§ط² ط¯ط§ط¯ظ‡â€Œظ‡ط§غŒ ظ¾ط±ظˆعکظ‡"""
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("ظ¾ط±ظˆعکظ‡ ظ…ظˆط±ط¯ ظ†ط¸ط± غŒط§ظپطھ ظ†ط´ط¯.", "error")
        return redirect(url_for("index"))

    doors = get_doors_for_project_db(project_id)
    if not doors:
        flash("ظ‡غŒع† ط¯ط±ط¨غŒ ط¨ط±ط§غŒ ط§غŒظ† ظ¾ط±ظˆعکظ‡ ط«ط¨طھ ظ†ط´ط¯ظ‡ ط§ط³طھ.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # ط¯ط±غŒط§ظپطھ ط³طھظˆظ†â€Œظ‡ط§غŒ ظپط¹ط§ظ„
    visible_columns = session.get(f"visible_columns_{project_id}", [])
    
    try:
        # ط§ط·ظ…غŒظ†ط§ظ† ط§ط² ظˆط¬ظˆط¯ ظ¾ظˆط´ظ‡ ط®ط±ظˆط¬غŒ
        os.makedirs("static/exports", exist_ok=True)
        
        # ط§غŒط¬ط§ط¯ PDF ط¬ط¯غŒط¯ (ط§ظپظ‚غŒ)
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # ط§ظپط²ظˆط¯ظ† ظپظˆظ†طھ ظپط§ط±ط³غŒ
        pdf.add_font('Vazir', '', './static/Vazir.ttf', uni=True)
        pdf.set_font('Vazir', '', 10)
        
        # ط¹ظ†ظˆط§ظ†
        title_txt = fix_persian_text("ظ„غŒط³طھ ط³ظپط§ط±ط´ط§طھ ط¯ط±ط¨")
        pdf.cell(0, 10, txt=title_txt, border=0, ln=1, align="C")
        
        # ط§ط·ظ„ط§ط¹ط§طھ ظ…ط´طھط±غŒ
        pdf.set_font('Vazir', '', 9)
        pdf.ln(2)
        
        # ط§ط·ظ„ط§ط¹ط§طھ ظ…ط´طھط±غŒ
        customer_name = project_info.get("customer_name", "")
        order_ref = project_info.get("order_ref", "")
        date_shamsi = project_info.get("date_shamsi", "")
        
        # ط¬ط¯ظˆظ„ ط§ط·ظ„ط§ط¹ط§طھ ظ…ط´طھط±غŒ
        info_cell_width = 45
        info_cell_height = 7
        pdf.set_fill_color(240, 248, 255)  # ط±ظ†ع¯ ظ¾ط³â€Œط²ظ…غŒظ†ظ‡ ط¢ط¨غŒ ط±ظˆط´ظ†
        
        # ط±ط¯غŒظپ ط§ظˆظ„
        pdf.set_font('Vazir', '', 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(25, info_cell_height, fix_persian_text("ظ†ط§ظ… ظ…ط´طھط±غŒ:"), 1, 0, "R", 1)
        pdf.set_font('Vazir', '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(info_cell_width, info_cell_height, fix_persian_text(customer_name), 1, 0, "R", 1)
        
        pdf.set_font('Vazir', '', 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(25, info_cell_height, fix_persian_text("ط´ظ…ط§ط±ظ‡ ط³ظپط§ط±ط´:"), 1, 0, "R", 1)
        pdf.set_font('Vazir', '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(info_cell_width, info_cell_height, fix_persian_text(order_ref), 1, 1, "R", 1)
        
        # ط±ط¯غŒظپ ط¯ظˆظ…
        pdf.set_font('Vazir', '', 8)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(25, info_cell_height, fix_persian_text("طھط§ط±غŒط®:"), 1, 0, "R", 1)
        pdf.set_font('Vazir', '', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(info_cell_width, info_cell_height, fix_persian_text(date_shamsi), 1, 0, "R", 1)
        
        # ظپط¶ط§غŒ ط®ط§ظ„غŒ ط¨ط±ط§غŒ طھع©ظ…غŒظ„ ط±ط¯غŒظپ
        remaining_width = pdf.w - pdf.get_x() - pdf.r_margin
        pdf.cell(remaining_width, info_cell_height, "", 1, 1, "C", 1)
        
        pdf.ln(5)
        pdf.set_font('Vazir', '', 10)
        pdf.set_text_color(0, 0, 0)
        
        # طھط¹غŒغŒظ† ط³طھظˆظ†â€Œظ‡ط§غŒ ط¬ط¯ظˆظ„ ط§طµظ„غŒ
        headers = ["ظ…ع©ط§ظ† ظ†طµط¨", "ط¹ط±ط¶", "ط§ط±طھظپط§ط¹", "طھط¹ط¯ط§ط¯", "ط¬ظ‡طھ"]
        keys_for_columns = ["location", "width", "height", "quantity", "direction"]
        
        # ط§ظپط²ظˆط¯ظ† ط³طھظˆظ†â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ ظپط¹ط§ظ„
        for col_key in visible_columns:
            if col_key in ["rang", "noe_profile", "vaziat", "lola", "ghofl", "accessory", "kolaft", "dastgire"]:
                # غŒط§ظپطھظ† ظ†ط§ظ… ظ†ظ…ط§غŒط´غŒ
                for col in get_active_custom_columns():
                    if col['key'] == col_key:
                        headers.append(col['display'])
                        keys_for_columns.append(col_key)
                        break
        
        # ط§ظپط²ظˆط¯ظ† ط³طھظˆظ† طھظˆط¶غŒط­ط§طھ ط¯ط± ط§ظ†طھظ‡ط§ (ط§ع¯ط± ظپط¹ط§ظ„ ط¨ط§ط´ط¯)
        if "tozihat" in visible_columns:
            headers.append("طھظˆط¶غŒط­ط§طھ")
            keys_for_columns.append("tozihat")
        
        # ظ…ط­ط§ط³ط¨ظ‡ ط¹ط±ط¶ ط³طھظˆظ†â€Œظ‡ط§
        page_width = pdf.w - 2 * pdf.l_margin
        col_widths = []
        total_width = 0
        
        # طھط¹غŒغŒظ† ط¹ط±ط¶ ظ‡ط± ط³طھظˆظ† ط¨ط±ط§ط³ط§ط³ ط·ظˆظ„ ط¹ظ†ظˆط§ظ† ظˆ ظ…ط­طھظˆط§
        for i, header in enumerate(headers):
            key = keys_for_columns[i]
            # ظ…ط­ط§ط³ط¨ظ‡ ط­ط¯ط§ع©ط«ط± ط·ظˆظ„ ط¨ط±ط§غŒ ط¹ظ†ظˆط§ظ† ظˆ ظ…ط­طھظˆط§
    except Exception as e:
        flash(f"ط®ط·ط§ ط¯ط± ط§غŒط¬ط§ط¯ ظپط§غŒظ„ PDF: {str(e)}", "error")
        return redirect(url_for("view_project", project_id=project_id))

@app.route("/project/<int:project_id>/export_pdf_html", methods=["GET"])
def export_table_to_pdf_html(project_id):
    """ط®ط±ظˆط¬غŒ HTML ط§ط² ط¯ط§ط¯ظ‡â€Œظ‡ط§غŒ ظ¾ط±ظˆعکظ‡ ط¨ظ‡â€Œطµظˆط±طھ PDF"""
    project_info = get_project_details_db(project_id)
    if not project_info:
        flash("ظ¾ط±ظˆعکظ‡ ظ…ظˆط±ط¯ ظ†ط¸ط± غŒط§ظپطھ ظ†ط´ط¯.", "error")
        return redirect(url_for("index"))

    doors = get_doors_for_project_db(project_id)
    if not doors:
        flash("ظ‡غŒع† ط¯ط±ط¨غŒ ط¨ط±ط§غŒ ط§غŒظ† ظ¾ط±ظˆعکظ‡ ط«ط¨طھ ظ†ط´ط¯ظ‡ ط§ط³طھ.", "warning")
        return redirect(url_for("project_treeview", project_id=project_id))

    # ط¯ط±غŒط§ظپطھ ط³طھظˆظ†â€Œظ‡ط§غŒ ظپط¹ط§ظ„
    visible_columns = session.get(f"visible_columns_{project_id}", [])
    
    # ط¢ظ…ط§ط¯ظ‡â€Œط³ط§ط²غŒ ظ„غŒط³طھ ظ‡ط¯ط±ظ‡ط§غŒ ط³طھظˆظ†â€Œظ‡ط§ ظˆ ع©ظ„غŒط¯ظ‡ط§غŒ ظ…ط±ط¨ظˆط· ط¨ظ‡ ط¢ظ†â€Œظ‡ط§
    custom_headers = []
    custom_keys = []
    
    # ط§ظپط²ظˆط¯ظ† ط³طھظˆظ†â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ ظپط¹ط§ظ„
    for col_key in visible_columns:
        if col_key in ["rang", "noe_profile", "vaziat", "lola", "ghofl", "accessory", "kolaft", "dastgire"]:
            # غŒط§ظپطھظ† ظ†ط§ظ… ظ†ظ…ط§غŒط´غŒ
            for col in get_active_custom_columns():
                if col['key'] == col_key:
                    custom_headers.append(col['display'])
                    custom_keys.append(col_key)
                    break
    
    # ط¢غŒط§ ط³طھظˆظ† طھظˆط¶غŒط­ط§طھ ظ†ظ…ط§غŒط´ ط¯ط§ط¯ظ‡ ط´ظˆط¯
    show_notes = "tozihat" in visible_columns
    
    # طھط§ط±غŒط® ط§ظ…ط±ظˆط²
    today_date = jdatetime.datetime.now().strftime("%Y/%m/%d")
    
    # ظ…ط³غŒط± ظپظˆظ†طھ ظˆط²غŒط±
    font_path = os.path.abspath("static/Vazir.ttf")
    
    # ط§غŒط¬ط§ط¯ غŒع© ع©ظ¾غŒ ط§ط² ظ‚ط§ظ„ط¨ ط§طµظ„غŒ ط§ظ…ط§ ط¨ط§ طھط؛غŒغŒط±ط§طھ CSS ط¨ظ‡غŒظ†ظ‡â€Œط³ط§ط²غŒ ط´ط¯ظ‡
    optimized_template = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ط¬ط¯ظˆظ„ ط¯ط±ط¨â€Œظ‡ط§ - {{ project.customer_name }}</title>
    <style>
        @font-face {
            font-family: 'Vazir';
            src: url('file:///{{ font_path }}') format('truetype');
            font-weight: normal;
            font-style: normal;
        }
        
        body {
            font-family: 'Vazir', sans-serif;
            margin: 20px;
            color: #333;
        }
        
        .header {
            text-align: center;
            margin-bottom: 25px;
        }
        
        .customer-info {
            display: table;
            width: 100%;
            margin-bottom: 20px;
            background-color: #f8f9fa;
            border-radius: 5px;
            padding: 10px;
        }
        
        .info-row {
            display: table-row;
        }
        
        .info-cell {
            display: table-cell;
            padding: 5px 10px;
        }
        
        .info-label {
            font-weight: bold;
            color: #555;
        }
        
        table.doors-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            table-layout: fixed;
        }
        
        table.doors-table th {
            background-color: #3498db;
            color: white;
            font-weight: bold;
            text-align: center;
            padding: 10px;
            border: 1px solid #ddd;
        }
        
        table.doors-table td {
            padding: 8px;
            border: 1px solid #ddd;
            text-align: center;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        table.doors-table tr:nth-child(even) {
            background-color: #f2f2f2;
        }
        
        /* ط±ظ†ع¯â€Œظ‡ط§غŒ ط³ظپط§ط±ط´غŒ */
        .yellow {
            background-color: #fff9c4 !important;
        }
        
        .lightgreen {
            background-color: #c8e6c9 !important;
        }
        
        .lightblue {
            background-color: #bbdefb !important;
        }
        
        .footer {
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>ظ„غŒط³طھ ط¯ط±ط¨â€Œظ‡ط§غŒ ظ¾ط±ظˆعکظ‡ {{ project.customer_name }}</h1>
    </div>
    
    <div class="customer-info">
        <div class="info-row">
            <div class="info-cell"><span class="info-label">ظ†ط§ظ… ظ…ط´طھط±غŒ:</span> {{ project.customer_name }}</div>
            <div class="info-cell"><span class="info-label">ط´ظ…ط§ط±ظ‡ طھظ…ط§ط³:</span> {{ project.phone_number }}</div>
            <div class="info-cell"><span class="info-label">طھط§ط±غŒط®:</span> {{ today_date }}</div>
        </div>
        <div class="info-row">
            <div class="info-cell"><span class="info-label">ط¢ط¯ط±ط³:</span> {{ project.address }}</div>
        </div>
    </div>
    
    <table class="doors-table">
        <thead>
            <tr>
                <th>ط±ط¯غŒظپ</th>
                <th>ع©ط¯</th>
                <th>ط¹ط±ط¶</th>
                <th>ط§ط±طھظپط§ط¹</th>
                {% for header in custom_headers %}
                <th>{{ header }}</th>
                {% endfor %}
                {% if show_notes %}
                <th>طھظˆط¶غŒط­ط§طھ</th>
                {% endif %}
            </tr>
        </thead>
        <tbody>
            {% for door in doors %}
            <tr>
                <td>{{ loop.index }}</td>
                <td>{{ door.code }}</td>
                <td>{{ door.width }}</td>
                <td>{{ door.height }}</td>
                {% for key in custom_keys %}
                <td>{{ door[key] }}</td>
                {% endfor %}
                {% if show_notes %}
                <td>{{ door.notes }}</td>
                {% endif %}
            </tr>
            {% endfor %}
        </tbody>
    </table>
    
    <div class="footer">
        <p>طھظˆظ„غŒط¯ ط´ط¯ظ‡ طھظˆط³ط· ظ†ط±ظ…â€Œط§ظپط²ط§ط± ظ…ط¯غŒط±غŒطھ ط¨ط±ط´</p>
    </div>
</body>
</html>"""

    return render_template_string(
        optimized_template,
        project=project_info,
        doors=doors,
        custom_headers=custom_headers,
        custom_keys=custom_keys,
        show_notes=show_notes,
        today_date=today_date,
        font_path=font_path
    )

if __name__ == "__main__":
if __name__ == "__main__":
    print("INFO: Starting Flask application...")
    app.run(debug=True, host="0.0.0.0", port=8080)
