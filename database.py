import sqlite3
import traceback
import os
from config import Config
from db_migrations import apply_migrations
from datetime import datetime

DB_NAME = Config.DB_NAME

def get_db_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    apply_migrations(conn)
    return conn

def check_table_exists(table_name):
    conn_check = None
    exists = False
    print(f"DEBUG: Starting check for table '{table_name}'...")
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
            print(f"DEBUG: Table '{table_name}' found in '{DB_NAME}'.")
        else:
            print(f"DEBUG: Table '{table_name}' NOT found in '{DB_NAME}'.")
    except sqlite3.Error as e:
        print(f"!!!!!! Error in check_table_exists: {e}")
        traceback.print_exc()
    finally:
        if conn_check:
            conn_check.close()
    return exists

def get_all_projects():
    """Return all projects."""
    conn = None
    projects = []
    print("DEBUG: Entering get_all_projects")
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
        print(f"DEBUG: get_all_projects found {len(projects)} projects.")
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_all_projects: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return projects

def add_project_db(customer_name, order_ref, date_shamsi=""):
    """Add a new project."""
    print(f"DEBUG: Entering add_project_db, customer_name: {customer_name}, order_ref: {order_ref}")
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
        print(f"DEBUG: New project added with ID {project_id}.")
        return project_id
    except sqlite3.Error as e:
        print(f"!!!!!! Error in add_project_db: {e}")
        traceback.print_exc()
        return None
    finally:
        if conn:
            conn.close()

def get_project_details_db(project_id):
    """Get project details by ID."""
    conn = None
    project_details = None
    print(f"DEBUG: Entering get_project_details_db for ID: {project_id}")
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
            print(f"DEBUG: Project details found for ID {project_id}.")
        else:
            print(f"DEBUG: Project ID {project_id} not found.")
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_project_details_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return project_details

def get_doors_for_project_db(project_id):
    """Get all doors for a project with custom values."""
    conn = None
    doors_dict = {}
    print(f"DEBUG: Entering get_doors_for_project_db for project ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        query = """
            SELECT
                d.id, d.location, d.width, d.height, d.quantity, d.direction, d.row_color_tag,
                cc.column_name,
                dcv.value
            FROM doors d
            LEFT JOIN door_custom_values dcv ON d.id = dcv.door_id
            LEFT JOIN custom_columns cc ON dcv.column_id = cc.id
            WHERE d.project_id = ?
            ORDER BY d.id
        """
        cursor.execute(query, (project_id,))

        for row in cursor.fetchall():
            door_id, location, width, height, quantity, direction, row_color_tag, col_key, col_value = row

            if door_id not in doors_dict:
                doors_dict[door_id] = {
                    "id": door_id,
                    "location": location,
                    "width": width,
                    "height": height,
                    "quantity": quantity,
                    "direction": direction,
                    "row_color_tag": row_color_tag if row_color_tag else "white",
                }

            if col_key and col_value is not None:
                doors_dict[door_id][col_key] = col_value

        doors = list(doors_dict.values())
        print(f"DEBUG: get_doors_for_project_db found {len(doors)} doors.")
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_doors_for_project_db: {e}")
        traceback.print_exc()
        return []
    finally:
        if conn:
            conn.close()
    return doors

def add_door_db(project_id, location, width, height, quantity, direction, row_color="white"):
    """Add a new door to the database."""
    conn = None
    door_id = None
    print(f"DEBUG: Entering add_door_db for project ID: {project_id}")
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
        print(f"DEBUG: New door saved with ID {door_id} for project {project_id}.")
    except sqlite3.Error as e:
        print(f"!!!!!! Error in add_door_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return door_id

def get_all_custom_columns():
    """Get all custom columns."""
    conn = None
    columns = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, column_name, display_name, is_active, column_type FROM custom_columns ORDER BY id"
        )
        columns = [
            {"id": row[0], "key": row[1], "display": row[2], "is_active": row[3], "type": row[4]}
            for row in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_all_custom_columns: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return columns

def get_active_custom_columns():
    """Get active custom columns."""
    conn = None
    columns = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, column_name, display_name, column_type FROM custom_columns WHERE is_active = 1 ORDER BY id"
        )
        columns = [
            {"id": row[0], "key": row[1], "display": row[2], "type": row[3]}
            for row in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_active_custom_columns: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return columns

def get_active_custom_columns_values():
    """Get keys of active custom columns."""
    active_columns = get_active_custom_columns()
    return [column["key"] for column in active_columns]

def add_custom_column(column_name, display_name, column_type='text'):
    """Add a new custom column."""
    conn = None
    new_id = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO custom_columns (column_name, display_name, is_active, column_type) VALUES (?, ?, 1, ?)",
            (column_name, display_name, column_type),
        )
        new_id = cursor.lastrowid
        conn.commit()
    except sqlite3.Error as e:
        print(f"!!!!!! Error in add_custom_column: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return new_id

def update_custom_column_status(column_id, is_active):
    """Update custom column status."""
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
        print(f"!!!!!! Error in update_custom_column_status: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success

def get_column_id_by_key(column_key):
    """Find column ID by key."""
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
        print(f"!!!!!! Error in get_column_id_by_key: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return column_id

def get_custom_column_options(column_id):
    """Get options for a custom column."""
    conn = None
    options = []
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, option_value FROM custom_column_options WHERE column_id = ? ORDER BY id",
            (column_id,),
        )
        options = [{"id": row[0], "value": row[1]} for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_custom_column_options: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return options

def add_option_to_column(column_id, option_value):
    """Add option to custom column."""
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
        print(f"!!!!!! Error in add_option_to_column: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success

def delete_column_option(option_id):
    """Delete a column option."""
    conn = None
    success = False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM custom_column_options WHERE id = ?", (option_id,))
        conn.commit()
        success = True
    except sqlite3.Error as e:
        print(f"!!!!!! Error in delete_column_option: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success

def update_custom_column_option(option_id, new_value):
    """Update custom column option value."""
    conn = None
    success = False
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE custom_column_options SET option_value = ? WHERE id = ?",
            (new_value, option_id)
        )
        conn.commit()
        success = cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"!!!!!! Error in update_custom_column_option: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success

def update_door_custom_value(cursor, door_id, column_id, value):
    """Update or insert custom value for a door (using existing cursor)."""
    print(f"DEBUG: Start UPSERT custom value - Door: {door_id}, Col: {column_id}, Value: '{value}'")
    if value is None:
        value = ""
    
    cursor.execute(
        "DELETE FROM door_custom_values WHERE door_id = ? AND column_id = ?",
        (door_id, column_id)
    )
    
    if value != "":
        cursor.execute(
            "INSERT INTO door_custom_values (door_id, column_id, value) VALUES (?, ?, ?)",
            (door_id, column_id, value)
        )
        print(f"DEBUG: Inserted '{value}' for door {door_id}, col {column_id}.")
    else:
        print(f"DEBUG: Value empty, no record inserted for door {door_id}, col {column_id}.")

def get_door_custom_values(door_id):
    """Get custom values for a door."""
    conn = None
    custom_values = {}
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
            custom_values[row[0]] = row[1]
        
        all_columns = get_all_custom_columns()
        for col in all_columns:
            if col["key"] not in custom_values:
                custom_values[col["key"]] = ""
                
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_door_custom_values: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return custom_values

def update_project_db(project_id, customer_name, order_ref, date_shamsi=""):
    """Update project details."""
    conn = None
    success = False
    print(f"DEBUG: Entering update_project_db for ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE projects SET customer_name = ?, order_ref = ?, date_shamsi = ? WHERE id = ?",
            (customer_name, order_ref, date_shamsi, project_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        print(f"DEBUG: Update project ID {project_id} {'successful' if success else 'failed'}.")
    except sqlite3.Error as e:
        print(f"!!!!!! Error in update_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success

def delete_project_db(project_id):
    """Delete a project."""
    conn = None
    success = False
    print(f"DEBUG: Entering delete_project_db for ID: {project_id}")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        success = cursor.rowcount > 0
        print(f"DEBUG: Delete project ID {project_id} {'successful' if success else 'failed'}.")
    except sqlite3.Error as e:
        print(f"!!!!!! Error in delete_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success

def ensure_default_custom_columns():
    """Ensure default custom columns exist."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM custom_columns WHERE is_active = 1")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print("DEBUG: No active custom columns found. Adding defaults...")
            default_columns = [
                ("rang", "رنگ پروفیل"),
                ("noe_profile", "نوع پروفیل"),
                ("vaziat", "وضعیت تولید درب"),
                ("lola", "لولا"),
                ("ghofl", "قفل"),
                ("accessory", "اکسسوری"),
                ("kolaft", "کلافت"),
                ("dastgire", "دستگیره"),
                ("tozihat", "توضیحات")
            ]
            
            for column_key, display_name in default_columns:
                cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
                column = cursor.fetchone()
                
                if column:
                    cursor.execute("UPDATE custom_columns SET is_active = 1 WHERE id = ?", (column[0],))
                    print(f"DEBUG: Column '{column_key}' activated")
                else:
                    cursor.execute(
                        "INSERT INTO custom_columns (column_name, display_name, is_active) VALUES (?, ?, 1)",
                        (column_key, display_name)
                    )
                    print(f"DEBUG: Column '{column_key}' added")
            
            conn.commit()
            print("DEBUG: Default columns added/activated successfully")
        
    except sqlite3.Error as e:
        print(f"ERROR: Error in ensure_default_custom_columns: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

def check_column_can_hide_internal(project_id, column_key):
    """Check if a column can be hidden."""
    if not column_key:
        return {"can_hide": True, "reason": "Empty column key"}
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", (column_key,))
        result = cursor.fetchone()
        if not result:
            return {"can_hide": True, "reason": "Column not in DB"}
        
        column_id = result[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM door_custom_values 
            JOIN doors ON door_custom_values.door_id = doors.id
            WHERE door_custom_values.column_id = ? 
            AND doors.project_id = ?
            AND door_custom_values.value IS NOT NULL 
            AND door_custom_values.value != ''
        """, (column_id, project_id))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        if count > 0:
            return {
                "can_hide": False, 
                "reason": f"Column '{column_key}' has {count} values in this project"
            }
        
        return {"can_hide": True, "reason": "No data in column"}
        
    except sqlite3.Error as e:
        print(f"Error checking column {column_key}: {e}")
        return {"can_hide": False, "reason": f"Database error: {e}"}
    except Exception as e:
        print(f"Unexpected error checking column {column_key}: {e}")
        return {"can_hide": False, "reason": f"Unexpected error: {e}"}

def get_non_empty_custom_columns_for_project(project_id, base_keys):
    """
    Get list of custom column keys that have data for the project.
    Used for refresh_project_visible_columns logic.
    """
    conn = None
    non_empty_cols = []
    try:
        active_custom_columns_data = get_active_custom_columns()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for col_data in active_custom_columns_data:
            column_key = col_data["key"]
            column_id = col_data["id"]

            if column_key in base_keys:
                continue

            cursor.execute("""
                SELECT 1 FROM door_custom_values dcv
                JOIN doors d ON dcv.door_id = d.id
                WHERE d.project_id = ? AND dcv.column_id = ? AND dcv.value IS NOT NULL AND dcv.value != ''
                LIMIT 1
            """, (project_id, column_id))
            
            if cursor.fetchone(): 
                non_empty_cols.append(column_key)
                
    except sqlite3.Error as e:
        print(f"ERROR in get_non_empty_custom_columns_for_project: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"ERROR in get_non_empty_custom_columns_for_project: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return non_empty_cols

def get_price_settings_db():
    """Get price settings from DB."""
    conn = None
    settings = {}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM price_settings")
        rows = cursor.fetchall()
        settings = {row['key']: row['value'] for row in rows}
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_price_settings_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return settings

def save_quote_db(data):
    """Save a quote to the database."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO saved_quotes 
            (customer_name, customer_mobile, input_width, input_height, profile_type, aluminum_color, door_material, paint_condition, paint_brand, selections_details, final_calculated_price, timestamp, shamsi_order_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get('customer_name'), data.get('customer_mobile'), data.get('input_width'), 
            data.get('input_height'), data.get('profile_type'), data.get('aluminum_color'), 
            data.get('door_material'), data.get('paint_condition'), data.get('paint_brand'), 
            data.get('selections_details'), data.get('final_price'), datetime.now(), 
            data.get('shamsi_order_date')
        ))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"SQLite error in save_quote_db: {e}") 
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()

def get_all_saved_quotes_db():
    """Get all saved quotes."""
    conn = None
    quotes = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, customer_name, customer_mobile, input_width, input_height, profile_type, 
                   aluminum_color, door_material, paint_condition, paint_brand, 
                   timestamp, selections_details, final_calculated_price, shamsi_order_date
            FROM saved_quotes 
            ORDER BY customer_name, timestamp DESC
        """)
        # Convert rows to dicts for easier usage
        quotes = [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_all_saved_quotes_db: {e}") 
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return quotes

def delete_quote_db(quote_id):
    """Delete a saved quote."""
    conn = None
    success = False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Check if exists (optional, but good for returning false if not found)
        cursor.execute("SELECT id FROM saved_quotes WHERE id = ?", (quote_id,))
        if not cursor.fetchone():
            return False
            
        cursor.execute("DELETE FROM saved_quotes WHERE id = ?", (quote_id,))
        conn.commit()
        success = True
    except sqlite3.Error as e:
        print(f"Error in delete_quote_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success

def delete_multiple_quotes_db(quote_ids):
    """Delete multiple saved quotes."""
    conn = None
    deleted_count = 0
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        for q_id in quote_ids:
            try:
                q_id_int = int(q_id)
                cursor.execute("DELETE FROM saved_quotes WHERE id = ?", (q_id_int,))
                deleted_count += cursor.rowcount
            except ValueError:
                continue
            
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error in delete_multiple_quotes_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return deleted_count
