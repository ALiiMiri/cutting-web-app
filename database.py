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
    # apply_migrations(conn)  <-- Removed for performance
    return conn

def init_db():
    """Initialize the database with schema migrations and inventory tables."""
    print("DEBUG: Initializing database system...")
    
    # 1. Run Core Migrations (projects, doors, pricing, etc.)
    conn = sqlite3.connect(DB_NAME)
    try:
        apply_migrations(conn)
        print("DEBUG: Core schema migrations applied successfully.")
    except Exception as e:
        print(f"!!!!!! Error applying migrations: {e}")
        traceback.print_exc()
    finally:
        conn.close()
    
    # 2. Initialize Inventory Tables (managed separately)
    try:
        initialize_inventory_tables()
        print("DEBUG: Inventory tables initialized.")
    except Exception as e:
        print(f"!!!!!! Error initializing inventory tables: {e}")
        traceback.print_exc()
    
    print("DEBUG: Database initialization process completed.")

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

def save_doors_batch_db(project_id, doors_data):
    """
    Save multiple doors and their custom values in a transaction.
    doors_data: list of dicts
    Returns (saved_count, error_count)
    """
    conn = None
    saved_count = 0
    error_count = 0
    
    # Define standard columns to exclude from custom values logic
    standard_columns = ["location", "width", "height", "quantity", "direction", "row_color_tag"]
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for door_data in doors_data:
            try:
                # Insert door
                cursor.execute(
                    """
                    INSERT INTO doors (project_id, location, width, height, quantity, direction, row_color_tag) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        door_data.get("location"),
                        door_data.get("width"),
                        door_data.get("height"),
                        door_data.get("quantity"),
                        door_data.get("direction"),
                        door_data.get("row_color_tag", "white"),
                    ),
                )
                door_id = cursor.lastrowid
                
                if door_id:
                    saved_count += 1
                    # Save custom values
                    for key, value in door_data.items():
                        if key not in standard_columns:
                            column_id = get_column_id_by_key(key)
                            if column_id:
                                update_door_custom_value(cursor, door_id, column_id, value)
                                
            except sqlite3.Error as e:
                error_count += 1
                print(f"!!!!!! Error saving door in batch: {e}")
                traceback.print_exc()
                
        conn.commit()
        print(f"DEBUG: Committed batch save for project {project_id}.")
        
    except sqlite3.Error as e:
        print(f"!!!!!! Error in save_doors_batch_db: {e}")
        traceback.print_exc()
        if conn:
            conn.rollback()
        error_count = len(doors_data)
        saved_count = 0
    finally:
        if conn:
            conn.close()
            
    return saved_count, error_count

def get_column_type_db(column_id):
    """Get the type of a custom column."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT column_type FROM custom_columns WHERE id = ?", (column_id,))
    result = cursor.fetchone()
    conn.close()
    return result['column_type'] if result else None

def get_column_id_from_option_db(option_id):
    """Get the column_id associated with an option."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT column_id FROM custom_column_options WHERE id = ?", (option_id,))
    result = cursor.fetchone()
    conn.close()
    return result['column_id'] if result else None

def batch_update_doors_db(door_ids, base_fields_to_update, columns_to_update):
    """
    Update multiple doors in batch.
    Returns (successful_updates, failed_updates, success_messages, error_messages)
    """
    conn = None
    successful_updates = 0
    failed_updates = 0
    success_messages = []
    error_messages = []
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for door_id in door_ids:
            try:
                door_id = int(door_id)
                door_updated = False
                
                # Get current door info for reporting
                cursor.execute("SELECT location FROM doors WHERE id = ?", (door_id,))
                door_info = cursor.fetchone()
                door_location = door_info['location'] if door_info else f"ID: {door_id}"
                
                # Update base fields
                if base_fields_to_update:
                    update_parts = []
                    params = []
                    field_updates = []
                    
                    for field, value in base_fields_to_update.items():
                        if field in ["width", "height", "quantity"]:
                            try:
                                value = float(value) if field != "quantity" else int(value)
                                update_parts.append(f"{field} = ?")
                                params.append(value)
                                field_updates.append(f"{field} = {value}")
                            except (ValueError, TypeError):
                                error_msg = f"Invalid value for {field}: '{value}' on door {door_location}"
                                error_messages.append(error_msg)
                                continue
                        else:
                            update_parts.append(f"{field} = ?")
                            params.append(value)
                            field_updates.append(f"{field} = '{value}'")
                    
                    if update_parts:
                        query = f"UPDATE doors SET {', '.join(update_parts)} WHERE id = ?"
                        params.append(door_id)
                        
                        try:
                            cursor.execute(query, params)
                            if cursor.rowcount > 0:
                                door_updated = True
                                msg = f"Door {door_location}: Updated {', '.join(field_updates)}"
                                success_messages.append(msg)
                        except sqlite3.Error as e:
                            error_msg = f"Error updating base fields for door {door_location}: {str(e)}"
                            error_messages.append(error_msg)

                # Update custom fields
                for column_key, new_value in columns_to_update.items():
                    try:
                        column_id = get_column_id_by_key(column_key)
                        if not column_id:
                            error_msg = f"Column '{column_key}' not found for door {door_location}"
                            error_messages.append(error_msg)
                            continue
                            
                        # Get display name
                        cursor.execute("SELECT display_name FROM custom_columns WHERE id = ?", (column_id,))
                        display_result = cursor.fetchone()
                        column_display = display_result['display_name'] if display_result else column_key
                        
                        # Get current value for reporting
                        cursor.execute("SELECT value FROM door_custom_values WHERE door_id = ? AND column_id = ?", (door_id, column_id))
                        current_result = cursor.fetchone()
                        current_value = current_result['value'] if current_result else None
                        
                        # Update value
                        update_door_custom_value(cursor, door_id, column_id, new_value)
                        door_updated = True
                        
                        if current_value:
                            msg = f"Column '{column_display}' changed from '{current_value}' to '{new_value}'"
                        else:
                            msg = f"Column '{column_display}' set to '{new_value}'"
                        
                        success_messages.append(f"Door {door_location}: {msg}")
                    
                    except Exception as e:
                        error_msg = f"Error updating column '{column_key}' for door {door_location}: {str(e)}"
                        error_messages.append(error_msg)
                
                if door_updated:
                    successful_updates += 1
                else:
                    failed_updates += 1
                    if not error_messages or not any(f"Door {door_location}" in m for m in error_messages):
                        error_messages.append(f"No fields updated for door {door_location}")

            except Exception as e:
                failed_updates += 1
                error_msg = f"Error updating door {door_id}: {str(e)}"
                error_messages.append(error_msg)
                traceback.print_exc()

        conn.commit()
        
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        failed_updates += len(door_ids)
        error_msg = f"Database error: {str(e)}"
        error_messages.append(error_msg)
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
            
    return successful_updates, failed_updates, success_messages, error_messages

# -------------------------------------------------------------------
# بخش مدیریت انبار (Inventory Management)
# -------------------------------------------------------------------

def initialize_inventory_tables():
    """ایجاد جداول مورد نیاز برای سیستم انبار"""
    print("DEBUG: Creating inventory tables...")
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # جدول انواع پروفیل
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS profile_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            default_length REAL DEFAULT 600,
            weight_per_meter REAL DEFAULT 1.9,
            color TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # جدول موجودی شاخه‌های کامل
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_type_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE
        )
        ''')
        
        # جدول شاخه‌های برش‌خورده
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_pieces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_type_id INTEGER NOT NULL,
            length REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE
        )
        ''')
        
        # جدول سوابق تغییرات انبار
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_type_id INTEGER NOT NULL,
            change_type TEXT NOT NULL,
            quantity INTEGER,
            length REAL,
            piece_id INTEGER,
            project_id INTEGER,
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (profile_type_id) REFERENCES profile_types (id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL
        )
        ''')
        
        # جدول تنظیمات محاسبه برش
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS cutting_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            value TEXT,
            description TEXT
        )
        ''')
        
        # داده‌های پیش‌فرض برای تنظیمات
        cursor.execute('''
        INSERT OR IGNORE INTO cutting_settings (name, value, description) 
        VALUES 
            ('waste_threshold', '70', 'آستانه اندازه ضایعات کوچک (سانتی‌متر)'),
            ('use_inventory', 'true', 'استفاده از سیستم انبار در محاسبات'),
            ('prefer_pieces', 'true', 'اولویت استفاده از شاخه‌های نیمه بر کامل'),
            ('inventory_optimization_strategy', 'minimize_waste', 'استراتژی بهینه‌سازی'),
            ('show_inventory_warnings', 'true', 'نمایش هشدارهای موجودی'),
            ('low_inventory_threshold', '5', 'آستانه هشدار موجودی کم')
        ''')
        
        # بررسی و افزودن ستون min_waste در صورت عدم وجود (Migration)
        try:
            cursor.execute("SELECT min_waste FROM profile_types LIMIT 1")
        except sqlite3.OperationalError:
            print("DEBUG: Adding min_waste column to profile_types table...")
            cursor.execute("ALTER TABLE profile_types ADD COLUMN min_waste REAL DEFAULT 20")
            
        conn.commit()
    except sqlite3.Error as e:
        print(f"!!!!!! Error in initialize_inventory_tables: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

def get_all_profile_types():
    """دریافت تمام انواع پروفیل"""
    conn = None
    profiles = []
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # دریافت اطلاعات پروفیل به همراه آمار موجودی
        query = """
        SELECT 
            pt.*,
            COALESCE(SUM(ii.quantity), 0) as complete_count,
            (SELECT COUNT(*) FROM inventory_pieces ip WHERE ip.profile_type_id = pt.id) as cut_count,
            (COALESCE(SUM(ii.quantity), 0) * pt.default_length) + 
            COALESCE((SELECT SUM(length) FROM inventory_pieces ip WHERE ip.profile_type_id = pt.id), 0) as total_length
        FROM profile_types pt
        LEFT JOIN inventory_items ii ON pt.id = ii.profile_type_id
        GROUP BY pt.id
        ORDER BY pt.name
        """
        
        cursor.execute(query)
        profiles = [dict(row) for row in cursor.fetchall()]
        
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_all_profile_types: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return profiles

def add_profile_type(name, description, default_length=600, weight_per_meter=1.9, color='#cccccc', min_waste=20):
    """افزودن نوع پروفیل جدید"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO profile_types (name, description, default_length, weight_per_meter, color, min_waste) VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, default_length, weight_per_meter, color, min_waste)
        )
        profile_id = cursor.lastrowid
        
        # ایجاد رکورد موجودی صفر برای این پروفیل
        cursor.execute(
            "INSERT INTO inventory_items (profile_type_id, quantity) VALUES (?, 0)",
            (profile_id,)
        )
        
        conn.commit()
        return True, profile_id
    except sqlite3.Error as e:
        print(f"!!!!!! Error in add_profile_type: {e}")
        return False, str(e)
    finally:
        if conn:
            conn.close()

def update_profile_type(profile_id, name, description, default_length, weight_per_meter, color, min_waste):
    """ویرایش نوع پروفیل"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE profile_types 
            SET name=?, description=?, default_length=?, weight_per_meter=?, color=?, min_waste=?
            WHERE id=?
            """,
            (name, description, default_length, weight_per_meter, color, min_waste, profile_id)
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"!!!!!! Error in update_profile_type: {e}")
        return False
    finally:
        if conn:
            conn.close()

def delete_profile_type(profile_id):
    """حذف نوع پروفیل"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM profile_types WHERE id = ?", (profile_id,))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"!!!!!! Error in delete_profile_type: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_profile_details(profile_id):
    """دریافت جزئیات یک پروفیل خاص"""
    conn = None
    profile = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM profile_types WHERE id = ?", (profile_id,))
        row = cursor.fetchone()
        if row:
            profile = dict(row)
            
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_profile_details: {e}")
    finally:
        if conn:
            conn.close()
    return profile

def get_inventory_settings():
    """دریافت تنظیمات انبار"""
    conn = None
    settings = {}
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT name, value FROM cutting_settings")
        for name, value in cursor.fetchall():
            # تبدیل مقادیر رشته‌ای به نوع مناسب
            if value.lower() == 'true':
                settings[name] = True
            elif value.lower() == 'false':
                settings[name] = False
            elif value.isdigit():
                settings[name] = int(value)
            else:
                settings[name] = value
                
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_inventory_settings: {e}")
    finally:
        if conn:
            conn.close()
    return settings

def update_inventory_settings(new_settings):
    """به‌روزرسانی تنظیمات انبار"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        for name, value in new_settings.items():
            cursor.execute(
                "INSERT OR REPLACE INTO cutting_settings (name, value) VALUES (?, ?)",
                (name, str(value))
            )
            
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"!!!!!! Error in update_inventory_settings: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_inventory_stats():
    """دریافت آمار کلی انبار"""
    conn = None
    stats = {
        "total_profiles": 0,
        "total_complete_pieces": 0,
        "total_cut_pieces": 0,
        "total_weight": 0,
        "total_complete_length": 0,
        "total_cut_length": 0,
        "total_length": 0,
        "average_piece_length": 0
    }
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # تعداد کل انواع پروفیل
        cursor.execute("SELECT COUNT(*) FROM profile_types")
        stats["total_profiles"] = cursor.fetchone()[0]
        
        # آمار شاخه‌های کامل
        cursor.execute("""
            SELECT 
                SUM(ii.quantity), 
                SUM(ii.quantity * pt.default_length),
                SUM(ii.quantity * pt.default_length * pt.weight_per_meter / 100)
            FROM inventory_items ii
            JOIN profile_types pt ON ii.profile_type_id = pt.id
        """)
        row = cursor.fetchone()
        if row and row[0] is not None:
            stats["total_complete_pieces"] = row[0]
            stats["total_complete_length"] = row[1] or 0
            stats["total_weight"] += row[2] or 0
            
        # آمار شاخه‌های برش‌خورده
        cursor.execute("""
            SELECT 
                COUNT(*), 
                SUM(ip.length),
                SUM(ip.length * pt.weight_per_meter / 100)
            FROM inventory_pieces ip
            JOIN profile_types pt ON ip.profile_type_id = pt.id
        """)
        row = cursor.fetchone()
        if row and row[0] is not None:
            stats["total_cut_pieces"] = row[0]
            stats["total_cut_length"] = row[1] or 0
            stats["total_weight"] += row[2] or 0
            
        # محاسبات نهایی
        stats["total_length"] = stats["total_complete_length"] + stats["total_cut_length"]
        total_pieces = stats["total_complete_pieces"] + stats["total_cut_pieces"]
        if total_pieces > 0:
            stats["average_piece_length"] = stats["total_length"] / total_pieces
            
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_inventory_stats: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return stats

def add_inventory_stock(profile_id, quantity, description=""):
    """افزودن موجودی شاخه کامل"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # به‌روزرسانی موجودی
        cursor.execute(
            "UPDATE inventory_items SET quantity = quantity + ?, last_updated = CURRENT_TIMESTAMP WHERE profile_type_id = ?",
            (quantity, profile_id)
        )
        
        # ثبت در لاگ
        cursor.execute(
            """
            INSERT INTO inventory_logs (profile_type_id, change_type, quantity, description)
            VALUES (?, 'add_stock', ?, ?)
            """,
            (profile_id, quantity, description)
        )
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"!!!!!! Error in add_inventory_stock: {e}")
        return False
    finally:
        if conn:
            conn.close()

def remove_inventory_stock(profile_id, quantity, description="", project_id=None):
    """کسر موجودی شاخه کامل"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # بررسی موجودی فعلی
        cursor.execute("SELECT quantity FROM inventory_items WHERE profile_type_id = ?", (profile_id,))
        row = cursor.fetchone()
        current_qty = row[0] if row else 0
        
        if current_qty < quantity:
            return False, "موجودی کافی نیست."
            
        # به‌روزرسانی موجودی
        cursor.execute(
            "UPDATE inventory_items SET quantity = quantity - ?, last_updated = CURRENT_TIMESTAMP WHERE profile_type_id = ?",
            (quantity, profile_id)
        )
        
        # ثبت در لاگ
        cursor.execute(
            """
            INSERT INTO inventory_logs (profile_type_id, change_type, quantity, project_id, description)
            VALUES (?, 'remove_stock', ?, ?, ?)
            """,
            (profile_id, quantity, project_id, description)
        )
        
        conn.commit()
        return True, ""
    except sqlite3.Error as e:
        print(f"!!!!!! Error in remove_inventory_stock: {e}")
        return False, str(e)
    finally:
        if conn:
            conn.close()

def add_inventory_piece(profile_id, length, description=""):
    """افزودن تکه شاخه (برش خورده/ضایعات مفید)"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO inventory_pieces (profile_type_id, length) VALUES (?, ?)",
            (profile_id, length)
        )
        piece_id = cursor.lastrowid
        
        # ثبت در لاگ
        cursor.execute(
            """
            INSERT INTO inventory_logs (profile_type_id, change_type, length, piece_id, description)
            VALUES (?, 'add_piece', ?, ?, ?)
            """,
            (profile_id, length, piece_id, description)
        )
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"!!!!!! Error in add_inventory_piece: {e}")
        return False
    finally:
        if conn:
            conn.close()

def remove_inventory_piece(piece_id, description="", project_id=None):
    """حذف تکه شاخه (استفاده شده)"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # دریافت اطلاعات قطعه قبل از حذف
        cursor.execute("SELECT profile_type_id, length FROM inventory_pieces WHERE id = ?", (piece_id,))
        row = cursor.fetchone()
        if not row:
            return False, "قطعه یافت نشد."
            
        profile_id, length = row
        
        cursor.execute("DELETE FROM inventory_pieces WHERE id = ?", (piece_id,))
        
        # ثبت در لاگ
        cursor.execute(
            """
            INSERT INTO inventory_logs (profile_type_id, change_type, length, piece_id, project_id, description)
            VALUES (?, 'remove_piece', ?, ?, ?, ?)
            """,
            (profile_id, length, piece_id, project_id, description)
        )
        
        conn.commit()
        return True, ""
    except sqlite3.Error as e:
        print(f"!!!!!! Error in remove_inventory_piece: {e}")
        return False, str(e)
    finally:
        if conn:
            conn.close()

def get_inventory_logs(limit=100, profile_id=None):
    """دریافت تاریخچه انبار"""
    conn = None
    logs = []
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = """
            SELECT il.*, pt.name as profile_name, p.customer_name as project_customer
            FROM inventory_logs il
            JOIN profile_types pt ON il.profile_type_id = pt.id
            LEFT JOIN projects p ON il.project_id = p.id
        """
        params = []
        
        if profile_id:
            query += " WHERE il.profile_type_id = ?"
            params.append(profile_id)
            
        query += " ORDER BY il.timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        logs = [dict(row) for row in cursor.fetchall()]
        
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_inventory_logs: {e}")
    finally:
        if conn:
            conn.close()
    return logs

def get_profile_stock_details(profile_id):
    """دریافت جزئیات موجودی یک پروفیل (شاخه‌های کامل و تکه‌ها)"""
    conn = None
    details = {
        "complete_pieces": 0,
        "pieces": [],
        "logs": []
    }
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # موجودی کامل
        cursor.execute("SELECT quantity FROM inventory_items WHERE profile_type_id = ?", (profile_id,))
        row = cursor.fetchone()
        if row:
            details["complete_pieces"] = row[0]
            
        # تکه‌ها
        cursor.execute("SELECT * FROM inventory_pieces WHERE profile_type_id = ? ORDER BY length DESC", (profile_id,))
        details["pieces"] = [dict(row) for row in cursor.fetchall()]
        
        # آخرین لاگ‌ها
        details["logs"] = get_inventory_logs(limit=10, profile_id=profile_id)
        
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_profile_stock_details: {e}")
    finally:
        if conn:
            conn.close()
    return details
