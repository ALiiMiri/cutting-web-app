import sqlite3
import traceback
import os
import random
from config import Config
from db_migrations import apply_migrations
from datetime import datetime
from date_utils import get_shamsi_datetime_str, get_shamsi_datetime_iso

DB_NAME = Config.DB_NAME

def get_db_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DB_NAME)
    # Ensure consistent behavior across all connections (SQLite defaults can be surprising)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
    except sqlite3.Error:
        # Non-fatal; keep going with best-effort defaults
        pass
    conn.row_factory = sqlite3.Row
    # apply_migrations(conn)  <-- Removed for performance
    return conn

def init_db():
    """Initialize the database with schema migrations and inventory tables."""
    print("DEBUG: Initializing database system...")
    
    # 1. Run Core Migrations (projects, doors, pricing, etc.)
    conn = get_db_connection()
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

def generate_unique_project_code():
    """Generate a unique 4-digit project code."""
    conn = None
    max_attempts = 100
    for _ in range(max_attempts):
        code = f"{random.randint(1000, 9999)}"
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE project_code = ?", (code,))
            if not cursor.fetchone():
                return code
        except sqlite3.Error:
            pass
        finally:
            if conn:
                conn.close()
    # Fallback: if all attempts fail, use timestamp-based code
    return f"{random.randint(1000, 9999)}"

def get_all_projects():
    """Return all projects."""
    conn = None
    projects = []
    print("DEBUG: Entering get_all_projects")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, customer_name, order_ref, date_shamsi, project_code FROM projects ORDER BY id DESC"
        )
        projects = [
            {"id": row[0], "cust_name": row[1], "order_ref": row[2], "date_shamsi": row[3], "project_code": row[4] if len(row) > 4 else None}
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

def get_projects_paginated(page=1, per_page=15, search="", sort_by="id", sort_order="DESC", 
                           date_from="", date_to="", customer_filter=""):
    """
    Get projects with pagination, search, filtering and sorting.
    
    Args:
        page: Page number (1-indexed)
        per_page: Number of items per page
        search: Search term (searches in customer_name, order_ref)
        sort_by: Column to sort by (id, customer_name, order_ref, date_shamsi)
        sort_order: ASC or DESC
        date_from: Filter by date from (Shamsi format: YYYY/MM/DD)
        date_to: Filter by date to (Shamsi format: YYYY/MM/DD)
        customer_filter: Filter by specific customer name
    
    Returns:
        dict with keys: projects (list), total (int), page (int), per_page (int), pages (int)
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Build WHERE clause
        where_conditions = []
        params = []
        
        # Search filter
        if search:
            where_conditions.append("(customer_name LIKE ? OR order_ref LIKE ?)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param])
        
        # Customer filter
        if customer_filter:
            where_conditions.append("customer_name = ?")
            params.append(customer_filter)
        
        # Date filters (simple string comparison for Shamsi dates)
        if date_from:
            where_conditions.append("date_shamsi >= ?")
            params.append(date_from)
        
        if date_to:
            where_conditions.append("date_shamsi <= ?")
            params.append(date_to)
        
        where_clause = " WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Validate sort_by
        valid_sort_columns = ["id", "customer_name", "order_ref", "date_shamsi"]
        if sort_by not in valid_sort_columns:
            sort_by = "id"
        
        # Validate sort_order
        if sort_order.upper() not in ["ASC", "DESC"]:
            sort_order = "DESC"
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM projects{where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        
        # Calculate pagination
        offset = (page - 1) * per_page
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        
        # Get paginated results
        query = f"""
            SELECT id, customer_name, order_ref, date_shamsi, project_code 
            FROM projects
            {where_clause}
            ORDER BY {sort_by} {sort_order}
            LIMIT ? OFFSET ?
        """
        params.extend([per_page, offset])
        cursor.execute(query, params)
        
        projects = [
            {
                "id": row[0],
                "cust_name": row[1],
                "order_ref": row[2],
                "date_shamsi": row[3],
                "project_code": row[4] if len(row) > 4 else None
            }
            for row in cursor.fetchall()
        ]
        
        return {
            "projects": projects,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": total_pages
        }
        
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_projects_paginated: {e}")
        traceback.print_exc()
        return {
            "projects": [],
            "total": 0,
            "page": 1,
            "per_page": per_page,
            "pages": 1
        }
    finally:
        if conn:
            conn.close()

def get_unique_customers():
    """Get list of unique customer names for filter dropdown."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT customer_name FROM projects WHERE customer_name IS NOT NULL AND customer_name != '' ORDER BY customer_name")
        customers = [row[0] for row in cursor.fetchall()]
        return customers
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_unique_customers: {e}")
        traceback.print_exc()
        return []
    finally:
        if conn:
            conn.close()

def add_project_db(customer_name, order_ref, date_shamsi="", project_code=None):
    """Add a new project."""
    print(f"DEBUG: Entering add_project_db, customer_name: {customer_name}, order_ref: {order_ref}, project_code: {project_code}")
    conn = None
    try:
        if not project_code:
            project_code = generate_unique_project_code()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO projects (customer_name, order_ref, date_shamsi, project_code) VALUES (?, ?, ?, ?)",
            (customer_name, order_ref, date_shamsi, project_code),
        )
        project_id = cursor.lastrowid
        conn.commit()
        print(f"DEBUG: New project added with ID {project_id}, code: {project_code}, name: '{customer_name}', date: {date_shamsi}.")
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
            "SELECT id, customer_name, order_ref, date_shamsi, project_code FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        if row:
            project_details = {
                "id": row[0],
                "customer_name": row[1],
                "order_ref": row[2],
                "date_shamsi": row[3],
                "project_code": row[4] if len(row) > 4 else None
            }
            project_code = project_details.get("project_code", "N/A")
            customer_name = project_details.get("customer_name", "N/A")
            print(f"DEBUG: Project details found for ID {project_id}, code: {project_code}, name: '{customer_name}'.")
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
        # Get project code for logging
        cursor.execute("SELECT project_code FROM projects WHERE id = ?", (project_id,))
        project_code_row = cursor.fetchone()
        project_code = project_code_row[0] if project_code_row and project_code_row[0] else None
        
        cursor.execute(
            "UPDATE projects SET customer_name = ?, order_ref = ?, date_shamsi = ? WHERE id = ?",
            (customer_name, order_ref, date_shamsi, project_id),
        )
        conn.commit()
        success = cursor.rowcount > 0
        project_display = f"{customer_name} ({project_code})" if project_code else customer_name
        print(f"DEBUG: Update project ID {project_id} ({project_display}) {'successful' if success else 'failed'}.")
    except sqlite3.Error as e:
        print(f"!!!!!! Error in update_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success

def delete_project_db(project_id):
    """
    Delete a project and its dependent data.

    Notes:
    - The schema does not consistently use ON DELETE CASCADE, and SQLite foreign keys
      are often disabled unless explicitly enabled. So we manually delete dependent
      rows to avoid orphaned data and to work regardless of FK settings.
    - Inventory logs are preserved, but their project_id reference is cleared.
    - Deducted profiles are automatically returned to inventory when project is deleted.
    """
    conn = None
    success = False
    project_name = f"Project #{project_id}"
    project_code = None
    print(f"DEBUG: Entering delete_project_db for ID: {project_id}")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 0) Before deleting, return any deducted profiles to inventory
        try:
            # Get project name and code for logging
            cursor.execute("SELECT customer_name, project_code FROM projects WHERE id = ?", (project_id,))
            project_row = cursor.fetchone()
            if project_row:
                project_name = project_row['customer_name'] if project_row['customer_name'] else f"Project #{project_id}"
                try:
                    project_code = project_row['project_code'] if project_row['project_code'] else None
                except (KeyError, IndexError):
                    project_code = None
            project_display = f"{project_name} ({project_code})" if project_code else project_name
            
            # Get all deductions for this project
            cursor.execute("""
                SELECT d.profile_type_id, d.quantity_deducted, pt.name as profile_name
                FROM inventory_deductions d
                JOIN profile_types pt ON d.profile_type_id = pt.id
                WHERE d.project_id = ?
            """, (project_id,))
            
            deductions = cursor.fetchall()
            
            if deductions:
                print(f"DEBUG: Found {len(deductions)} deduction(s) to return to inventory")
                
                for ded in deductions:
                    profile_id = ded['profile_type_id']
                    quantity = ded['quantity_deducted']
                    profile_name = ded['profile_name']
                    
                    # Ensure inventory row exists (older DBs may miss inventory_items for a profile)
                    cursor.execute(
                        "INSERT OR IGNORE INTO inventory_items (profile_type_id, quantity) VALUES (?, 0)",
                        (profile_id,),
                    )

                    # Return stock to inventory
                    cursor.execute("""
                        UPDATE inventory_items 
                        SET quantity = quantity + ?, last_updated = CURRENT_TIMESTAMP 
                        WHERE profile_type_id = ?
                    """, (quantity, profile_id))
                    
                    # Log the return in inventory_logs
                    cursor.execute("""
                        INSERT INTO inventory_logs
                        (profile_type_id, change_type, quantity, description, timestamp)
                        VALUES (?, 'return_on_delete', ?, ?, ?)
                    """, (
                        profile_id,
                        quantity,
                        f"بازگشت {quantity} شاخه به خاطر حذف پروژه: {project_display}",
                        get_shamsi_datetime_iso()  # تاریخ شمسی
                    ))
                    
                    print(f"DEBUG: Returned {quantity} units (profile_id={profile_id}) to inventory")
                
                # Delete deduction records (will happen via CASCADE anyway, but being explicit)
                cursor.execute("DELETE FROM inventory_deductions WHERE project_id = ?", (project_id,))
            else:
                print(f"DEBUG: No inventory deductions found for project {project_id}")
                
        except sqlite3.Error as e:
            print(f"WARNING: Error returning inventory (might not exist in older DBs): {e}")
            # Continue with deletion even if inventory return fails

        # Reset row_factory for the rest of the operations
        conn.row_factory = None
        cursor = conn.cursor()

        # 1) Gather door ids for this project (for door_custom_values cleanup)
        cursor.execute("SELECT id FROM doors WHERE project_id = ?", (project_id,))
        door_ids = [row[0] for row in cursor.fetchall()]

        # 2) Delete door_custom_values for those doors (if any)
        if door_ids:
            placeholders = ",".join(["?"] * len(door_ids))
            cursor.execute(
                f"DELETE FROM door_custom_values WHERE door_id IN ({placeholders})",
                door_ids,
            )

        # 3) Delete doors
        cursor.execute("DELETE FROM doors WHERE project_id = ?", (project_id,))

        # 4) Delete per-project UI/settings tables
        cursor.execute(
            "DELETE FROM project_visible_columns WHERE project_id = ?", (project_id,)
        )
        cursor.execute(
            "DELETE FROM batch_edit_checkbox_state WHERE project_id = ?", (project_id,)
        )

        # 5) Keep inventory logs, but detach them from this project
        try:
            cursor.execute(
                "UPDATE inventory_logs SET project_id = NULL WHERE project_id = ?",
                (project_id,),
            )
        except sqlite3.Error:
            # inventory_logs table might not exist in older DBs
            pass

        # 6) Finally, delete the project row
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        deleted_projects = cursor.rowcount
        conn.commit()
        success = deleted_projects > 0
        project_display_final = f"{project_name} ({project_code})" if project_code else project_name
        print(f"DEBUG: Delete project ID {project_id} ({project_display_final}) {'successful' if success else 'failed'}.")
    except sqlite3.Error as e:
        print(f"!!!!!! Error in delete_project_db: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return success

# تابع ensure_default_custom_columns() حذف شد.
# این تابع قدیمی با مایگریشن 002 تداخل داشت و ستون‌ها را بدون column_type اضافه می‌کرد.
# مایگریشن 002_seed_base_custom_columns این کار را به درستی انجام می‌دهد.

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
            data.get('selections_details'), data.get('final_price'), get_shamsi_datetime_iso(),  # تاریخ شمسی
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
    """
    بررسی وجود جداول انبار (برای سازگاری با کدهای قدیمی)
    
    NOTE: جداول انبار اکنون از طریق سیستم مایگریشن ایجاد می‌شوند:
    - Migration 010_create_inventory_tables: ایجاد جداول اصلی
    - Migration 011_add_min_waste_to_profile_types: افزودن ستون min_waste
    
    این تابع فقط برای سازگاری با کدهای قدیمی نگه داشته شده است
    و در واقع کاری انجام نمی‌دهد چون مایگریشن‌ها قبلاً اجرا شده‌اند.
    """
    print("DEBUG: Inventory tables are managed by migrations (010, 011).")
    # جداول انبار توسط مایگریشن‌های 010 و 011 ایجاد می‌شوند
    # این تابع فقط برای سازگاری با کدهای قدیمی نگه داشته شده است

def get_all_profile_types():
    """دریافت تمام انواع پروفیل"""
    conn = None
    profiles = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # دریافت اطلاعات پروفیل به همراه آمار موجودی
        query = """
        SELECT 
            pt.*,
            COALESCE(SUM(ii.quantity), 0) as complete_count,
            (SELECT COUNT(*) FROM inventory_pieces ip WHERE ip.profile_type_id = pt.id) as cut_count,
            -- total_length is returned in meters (default_length/length are stored in centimeters)
            ((COALESCE(SUM(ii.quantity), 0) * pt.default_length) / 100.0) +
            (COALESCE((SELECT SUM(length) FROM inventory_pieces ip WHERE ip.profile_type_id = pt.id), 0) / 100.0) as total_length,
            -- total_weight is returned in kg (weight_per_meter is kg/m, lengths are centimeters)
            ((COALESCE(SUM(ii.quantity), 0) * pt.default_length * pt.weight_per_meter) / 100.0) +
            COALESCE((
                SELECT SUM(ip.length * pt.weight_per_meter / 100.0)
                FROM inventory_pieces ip
                WHERE ip.profile_type_id = pt.id
            ), 0) as total_weight
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

def _sync_profile_to_dropdown(cursor, profile_name, old_name=None):
    """
    همگام‌سازی نام پروفیل با dropdown نوع پروفیل
    اگر old_name داده شود، گزینه قبلی را آپدیت می‌کند
    اگر old_name نباشد، گزینه جدید اضافه می‌کند
    """
    try:
        # پیدا کردن column_id برای "نوع پروفیل"
        cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", ("noe_profile",))
        result = cursor.fetchone()
        
        if not result:
            print("WARNING: Column 'noe_profile' not found. Skipping sync.")
            return
            
        column_id = result[0]
        
        if old_name:
            # آپدیت گزینه موجود
            cursor.execute(
                "UPDATE custom_column_options SET option_value = ? WHERE column_id = ? AND option_value = ?",
                (profile_name, column_id, old_name)
            )
            print(f"DEBUG: Updated dropdown option from '{old_name}' to '{profile_name}'")
        else:
            # بررسی وجود گزینه (جلوگیری از تکراری)
            cursor.execute(
                "SELECT id FROM custom_column_options WHERE column_id = ? AND option_value = ?",
                (column_id, profile_name)
            )
            if cursor.fetchone():
                print(f"DEBUG: Option '{profile_name}' already exists in dropdown")
                return
            
            # اضافه کردن گزینه جدید
            cursor.execute(
                "INSERT INTO custom_column_options (column_id, option_value) VALUES (?, ?)",
                (column_id, profile_name)
            )
            print(f"DEBUG: Added '{profile_name}' to dropdown")
            
    except sqlite3.Error as e:
        print(f"ERROR: Failed to sync profile to dropdown: {e}")

def _remove_profile_from_dropdown(cursor, profile_name):
    """حذف نام پروفیل از dropdown نوع پروفیل"""
    try:
        # پیدا کردن column_id برای "نوع پروفیل"
        cursor.execute("SELECT id FROM custom_columns WHERE column_name = ?", ("noe_profile",))
        result = cursor.fetchone()
        
        if not result:
            print("WARNING: Column 'noe_profile' not found. Skipping removal.")
            return
            
        column_id = result[0]
        
        # حذف گزینه
        cursor.execute(
            "DELETE FROM custom_column_options WHERE column_id = ? AND option_value = ?",
            (column_id, profile_name)
        )
        print(f"DEBUG: Removed '{profile_name}' from dropdown")
        
    except sqlite3.Error as e:
        print(f"ERROR: Failed to remove profile from dropdown: {e}")

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
        
        # همگام‌سازی با dropdown نوع پروفیل
        _sync_profile_to_dropdown(cursor, name)
        
        conn.commit()
        return True, profile_id
    except sqlite3.IntegrityError as e:
        error_msg = str(e)
        print(f"!!!!!! Integrity error in add_profile_type: {e}")
        if "UNIQUE constraint failed: profile_types.name" in error_msg or "UNIQUE constraint failed" in error_msg:
            return False, f"پروفیل با نام '{name}' قبلاً در سیستم وجود دارد. لطفاً نام دیگری انتخاب کنید."
        return False, f"خطای محدودیت دیتابیس: {error_msg}"
    except sqlite3.Error as e:
        print(f"!!!!!! Error in add_profile_type: {e}")
        return False, f"خطا در افزودن پروفیل: {str(e)}"
    finally:
        if conn:
            conn.close()

def update_profile_type(profile_id, name, description, default_length, weight_per_meter, color, min_waste):
    """ویرایش نوع پروفیل"""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # دریافت نام قبلی برای همگام‌سازی
        cursor.execute("SELECT name FROM profile_types WHERE id = ?", (profile_id,))
        result = cursor.fetchone()
        old_name = result[0] if result else None
        
        cursor.execute(
            """
            UPDATE profile_types 
            SET name=?, description=?, default_length=?, weight_per_meter=?, color=?, min_waste=?
            WHERE id=?
            """,
            (name, description, default_length, weight_per_meter, color, min_waste, profile_id)
        )
        
        # همگام‌سازی با dropdown نوع پروفیل (فقط اگر نام تغییر کرده)
        if old_name and old_name != name:
            _sync_profile_to_dropdown(cursor, name, old_name)
        
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # دریافت نام پروفیل برای حذف از dropdown
        cursor.execute("SELECT name FROM profile_types WHERE id = ?", (profile_id,))
        result = cursor.fetchone()
        profile_name = result[0] if result else None
        
        # با فعال بودن foreign keys و ON DELETE CASCADE، 
        # رکوردهای inventory_items و inventory_pieces به صورت خودکار حذف می‌شوند
        cursor.execute("DELETE FROM profile_types WHERE id = ?", (profile_id,))
        
        # حذف از dropdown نوع پروفیل
        if profile_name:
            _remove_profile_from_dropdown(cursor, profile_name)
        
        # پاک کردن رکوردهای orphaned (اگر وجود داشته باشند)
        # این برای اطمینان از پاک شدن رکوردهای قدیمی است
        cursor.execute("""
            DELETE FROM inventory_items 
            WHERE profile_type_id NOT IN (SELECT id FROM profile_types)
        """)
        cursor.execute("""
            DELETE FROM inventory_pieces 
            WHERE profile_type_id NOT IN (SELECT id FROM profile_types)
        """)
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"!!!!!! Error in delete_profile_type: {e}")
        traceback.print_exc()
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # پاک کردن رکوردهای orphaned قبل از محاسبه آمار
        # این برای اطمینان از صحت آمار است
        cursor.execute("""
            DELETE FROM inventory_items 
            WHERE profile_type_id NOT IN (SELECT id FROM profile_types)
        """)
        cursor.execute("""
            DELETE FROM inventory_pieces 
            WHERE profile_type_id NOT IN (SELECT id FROM profile_types)
        """)
        conn.commit()
        
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Ensure inventory row exists
        cursor.execute(
            "INSERT OR IGNORE INTO inventory_items (profile_type_id, quantity) VALUES (?, 0)",
            (profile_id,),
        )
        
        # به‌روزرسانی موجودی
        cursor.execute(
            "UPDATE inventory_items SET quantity = quantity + ?, last_updated = CURRENT_TIMESTAMP WHERE profile_type_id = ?",
            (quantity, profile_id)
        )
        
        # ثبت در لاگ
        cursor.execute(
            """
            INSERT INTO inventory_logs (profile_type_id, change_type, quantity, description, timestamp)
            VALUES (?, 'add_stock', ?, ?, ?)
            """,
            (profile_id, quantity, description, get_shamsi_datetime_iso())  # تاریخ شمسی
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # بررسی آیا این پروفیل قبلاً برای این پروژه کسر شده؟
        if project_id:
            cursor.execute(
                "SELECT quantity_deducted FROM inventory_deductions WHERE project_id = ? AND profile_type_id = ?",
                (project_id, profile_id)
            )
            existing_deduction = cursor.fetchone()
            if existing_deduction:
                return False, f"این پروفیل قبلاً برای این پروژه کسر شده است ({existing_deduction[0]} شاخه)."
        
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
            INSERT INTO inventory_logs (profile_type_id, change_type, quantity, project_id, description, timestamp)
            VALUES (?, 'remove_stock', ?, ?, ?, ?)
            """,
            (profile_id, quantity, project_id, description, get_shamsi_datetime_iso())  # تاریخ شمسی
        )
        
        # ثبت در جدول کسرهای انبار برای جلوگیری از کسر دوباره
        if project_id:
            cursor.execute(
                """
                INSERT INTO inventory_deductions (project_id, profile_type_id, quantity_deducted)
                VALUES (?, ?, ?)
                """,
                (project_id, profile_id, quantity)
            )
        
        conn.commit()
        return True, ""
    except sqlite3.Error as e:
        print(f"!!!!!! Error in remove_inventory_stock: {e}")
        return False, str(e)
    finally:
        if conn:
            conn.close()

def add_inventory_piece(profile_id, length, description="", project_id=None):
    """افزودن تکه شاخه (برش خورده/ضایعات مفید)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO inventory_pieces (profile_type_id, length) VALUES (?, ?)",
            (profile_id, length)
        )
        piece_id = cursor.lastrowid
        
        # ثبت در لاگ (با project_id اگر ارائه شده باشد)
        cursor.execute(
            """
            INSERT INTO inventory_logs (profile_type_id, change_type, length, piece_id, project_id, description, timestamp)
            VALUES (?, 'add_piece', ?, ?, ?, ?, ?)
            """,
            (profile_id, length, piece_id, project_id, description, get_shamsi_datetime_iso())  # تاریخ شمسی
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
        conn = get_db_connection()
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
            INSERT INTO inventory_logs (profile_type_id, change_type, length, piece_id, project_id, description, timestamp)
            VALUES (?, 'remove_piece', ?, ?, ?, ?, ?)
            """,
            (profile_id, length, piece_id, project_id, description, get_shamsi_datetime_iso())  # تاریخ شمسی
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
            SELECT
                il.*,
                pt.name as profile_name,
                pt.color as profile_color,
                p.customer_name as project_customer
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

def get_available_inventory_pieces(profile_name):
    """
    دریافت لیست قطعات برش‌خورده موجود برای یک پروفیل
    
    Args:
        profile_name (str): نام پروفیل
        
    Returns:
        list: لیست دیکشنری‌های حاوی id و length قطعات برش‌خورده، مرتب‌شده به صورت نزولی بر اساس length
              در صورت عدم یافتن پروفیل یا خطا، لیست خالی برمی‌گرداند
    """
    conn = None
    pieces = []
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # یافتن profile_id بر اساس نام
        cursor.execute("SELECT id FROM profile_types WHERE name = ?", (profile_name,))
        row = cursor.fetchone()
        
        if not row:
            # پروفیل یافت نشد
            return pieces
        
        profile_id = row['id']
        
        # دریافت قطعات برش‌خورده مرتب‌شده به صورت نزولی
        cursor.execute(
            "SELECT id, length FROM inventory_pieces WHERE profile_type_id = ? ORDER BY length DESC",
            (profile_id,)
        )
        pieces = [{"id": row['id'], "length": row['length']} for row in cursor.fetchall()]
        
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_available_inventory_pieces: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    return pieces

def get_mapped_profile_id(order_profile_name):
    """
    Map order profile name to inventory profile_type_id.
    
    This function bridges the Price Calculator (Order System) and the Inventory System.
    The Order System uses specific Persian names for profiles, while the Inventory System
    uses IDs and might have slightly different names.
    
    Args:
        order_profile_name (str): Profile name from the order/price calculator
        
    Returns:
        int or None: The profile_type_id if found, None otherwise
    """
    print(f"DEBUG: get_mapped_profile_id called with order_profile_name='{order_profile_name}'")
    
    if not order_profile_name:
        print("DEBUG: Empty profile name provided, returning None")
        return None
    
    # Hardcoded mapping dictionary for variations and alternative names
    profile_name_mapping = {
        "فریم لس قدیمی": ["فریم لس قدیمی", "Frameless Old", "frameless old"],
        "فریم لس قالب جدید": ["فریم لس قالب جدید", "Frameless New", "frameless new"],
        "توچوب دار": ["توچوب دار"],
        "دور آلومینیوم": ["دور آلومینیوم"]
    }
    
    conn = None
    profile_id = None
    
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Step 1: Try exact match first
        print(f"DEBUG: Attempting exact match for '{order_profile_name}'...")
        cursor.execute("SELECT id, name FROM profile_types WHERE name = ?", (order_profile_name,))
        row = cursor.fetchone()
        
        if row:
            profile_id = row['id']
            print(f"DEBUG: ✓ Exact match found! profile_type_id={profile_id} (name='{row['name']}')")
            return profile_id
        
        print(f"DEBUG: No exact match found for '{order_profile_name}'")
        
        # Step 2: Try variations from mapping dictionary
        variations = profile_name_mapping.get(order_profile_name, [])
        
        if variations:
            print(f"DEBUG: Checking {len(variations)} variation(s) from mapping dictionary...")
            
            for variant in variations:
                print(f"DEBUG: Trying variant '{variant}'...")
                cursor.execute("SELECT id, name FROM profile_types WHERE name = ?", (variant,))
                row = cursor.fetchone()
                
                if row:
                    profile_id = row['id']
                    print(f"DEBUG: ✓ Match found via variant '{variant}'! profile_type_id={profile_id} (name='{row['name']}')")
                    return profile_id
            
            print(f"DEBUG: No match found for any variations of '{order_profile_name}'")
        else:
            print(f"DEBUG: No variations defined in mapping dictionary for '{order_profile_name}'")
        
        # Step 3: No match found
        print(f"DEBUG: ✗ Profile '{order_profile_name}' NOT found in inventory system")
        return None
        
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_mapped_profile_id: {e}")
        traceback.print_exc()
        return None
    finally:
        if conn:
            conn.close()

def get_project_deductions(project_id):
    """
    دریافت لیست کسرهای انبار برای یک پروژه
    
    Args:
        project_id: شماره پروژه
        
    Returns:
        list: لیست دیکشنری‌های حاوی اطلاعات کسرها
    """
    conn = None
    deductions = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                d.id,
                d.project_id,
                d.profile_type_id,
                d.quantity_deducted,
                d.deduction_date,
                pt.name as profile_name
            FROM inventory_deductions d
            JOIN profile_types pt ON d.profile_type_id = pt.id
            WHERE d.project_id = ?
            ORDER BY d.deduction_date DESC
        """, (project_id,))
        
        deductions = [dict(row) for row in cursor.fetchall()]
        
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_project_deductions: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
    
    return deductions

def check_if_already_deducted(project_id, profile_id=None):
    """
    بررسی اینکه آیا پروژه قبلاً کسر شده یا نه
    
    Args:
        project_id: شماره پروژه
        profile_id: شماره پروفیل (اختیاری) - اگر داده نشه کلی پروژه رو چک می‌کنه
        
    Returns:
        bool: True اگه قبلاً کسر شده باشه
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if profile_id:
            cursor.execute(
                "SELECT COUNT(*) FROM inventory_deductions WHERE project_id = ? AND profile_type_id = ?",
                (project_id, profile_id)
            )
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM inventory_deductions WHERE project_id = ?",
                (project_id,)
            )
        
        count = cursor.fetchone()[0]
        return count > 0
        
    except sqlite3.Error as e:
        print(f"!!!!!! Error in check_if_already_deducted: {e}")
        return False
    finally:
        if conn:
            conn.close()

