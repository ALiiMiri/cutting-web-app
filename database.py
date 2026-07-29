import sqlite3
import traceback
import os
import random
import math
import secrets
import json
from config import Config
from db_migrations import apply_migrations
from datetime import datetime
from date_utils import get_shamsi_datetime_str, get_shamsi_datetime_iso
from profile_names import normalize_profile_name

DB_NAME = Config.DB_NAME

def get_db_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DB_NAME, timeout=30)
    # Ensure consistent behavior across all connections (SQLite defaults can be surprising)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA synchronous = FULL")
    except sqlite3.Error:
        # Non-fatal; keep going with best-effort defaults
        pass
    conn.row_factory = sqlite3.Row
    # apply_migrations(conn)  <-- Removed for performance
    return conn

def init_db(allow_migrations=False):
    """Validate schema at startup; mutations are reserved for the safe upgrader."""
    print("DEBUG: Initializing database system...")

    # 1. Run Core Migrations (projects, doors, pricing, etc.)
    conn = get_db_connection()
    try:
        apply_migrations(conn, allow_changes=allow_migrations)
        print("DEBUG: Core schema migrations applied successfully.")
    finally:
        conn.close()

    # 2. Initialize Inventory Tables (managed separately)
    initialize_inventory_tables()
    print("DEBUG: Inventory tables initialized.")

    print("DEBUG: Database initialization process completed.")

def check_table_exists(table_name):
    conn_check = None
    exists = False
    print(f"DEBUG: Starting check for table '{table_name}'...")
    try:
        conn_check = get_db_connection()
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
            conn = get_db_connection()
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
        conn = get_db_connection()
        cursor = conn.cursor()
        archive_filter = (
            "WHERE p.archived_at IS NULL"
            if "archived_at"
            in {row[1] for row in cursor.execute("PRAGMA table_info(projects)")}
            else ""
        )
        cursor.execute(
            f"""
            SELECT p.id, p.customer_name, p.order_ref, p.date_shamsi, p.project_code,
                   p.assigned_to_user_id, assignee.username, creator.username
            FROM projects AS p
            LEFT JOIN users AS assignee ON assignee.id=p.assigned_to_user_id
            LEFT JOIN users AS creator ON creator.id=p.created_by_user_id
            {archive_filter}
            ORDER BY p.id DESC
            """
        )
        projects = [
            {
                "id": row[0], "cust_name": row[1], "order_ref": row[2],
                "date_shamsi": row[3], "project_code": row[4],
                "assigned_to_user_id": row[5], "assigned_to_username": row[6],
                "created_by_username": row[7],
            }
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
                           date_from="", date_to="", customer_filter="", scope="all",
                           current_user_id=None):
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
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build WHERE clause
        project_columns = {
            row[1] for row in cursor.execute("PRAGMA table_info(projects)")
        }
        where_conditions = (
            ["archived_at IS NULL"] if "archived_at" in project_columns else []
        )
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

        if scope == "mine" and current_user_id:
            where_conditions.append("assigned_to_user_id = ?")
            params.append(current_user_id)
        elif scope == "unassigned":
            where_conditions.append("assigned_to_user_id IS NULL")

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
            SELECT p.id, p.customer_name, p.order_ref, p.date_shamsi, p.project_code,
                   p.assigned_to_user_id, assignee.username, creator.username
            FROM projects AS p
            LEFT JOIN users AS assignee ON assignee.id=p.assigned_to_user_id
            LEFT JOIN users AS creator ON creator.id=p.created_by_user_id
            {where_clause}
            ORDER BY p.{sort_by} {sort_order}
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
                "project_code": row[4],
                "assigned_to_user_id": row[5],
                "assigned_to_username": row[6],
                "created_by_username": row[7],
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


def get_project_dashboard_counts(user_id):
    """Return the three stable counts shown above the orders dashboard."""
    conn = None
    try:
        conn = get_db_connection()
        has_archived = "archived_at" in {
            column[1] for column in conn.execute("PRAGMA table_info(projects)")
        }
        row = conn.execute(
            f"""
            SELECT COUNT(*),
                   SUM(CASE WHEN assigned_to_user_id = ? THEN 1 ELSE 0 END),
                   SUM(CASE WHEN assigned_to_user_id IS NULL THEN 1 ELSE 0 END)
            FROM projects
            {"WHERE archived_at IS NULL" if has_archived else ""}
            """,
            (user_id,),
        ).fetchone()
        return {
            "total": int(row[0] or 0),
            "mine": int(row[1] or 0),
            "unassigned": int(row[2] or 0),
        }
    except sqlite3.Error as exc:
        print(f"Error loading project dashboard counts: {exc}")
        return {"total": 0, "mine": 0, "unassigned": 0}
    finally:
        if conn:
            conn.close()

def get_recent_customers(limit=100, scan_limit=500):
    """Return bounded recent customer suggestions for the dashboard filter."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT customer_name
            FROM (
                SELECT id, customer_name
                FROM projects
                WHERE archived_at IS NULL
                  AND customer_name IS NOT NULL
                  AND customer_name != ''
                ORDER BY id DESC
                LIMIT ?
            )
            GROUP BY customer_name
            ORDER BY MAX(id) DESC
            LIMIT ?
            """,
            (
                max(1, min(int(scan_limit), 2000)),
                max(1, min(int(limit), 200)),
            ),
        )
        customers = [row[0] for row in cursor.fetchall()]
        return customers
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_recent_customers: {e}")
        traceback.print_exc()
        return []
    finally:
        if conn:
            conn.close()

def add_project_db(
    customer_name,
    order_ref,
    date_shamsi="",
    project_code=None,
    measurement_unit="cm",
    created_by_user_id=None,
):
    """Add a new project."""
    print(f"DEBUG: Entering add_project_db, customer_name: {customer_name}, order_ref: {order_ref}, project_code: {project_code}")
    conn = None
    try:
        if not project_code:
            project_code = generate_unique_project_code()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO projects
                (customer_name, order_ref, date_shamsi, project_code, measurement_unit,
                 created_by_user_id, assigned_to_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_name, order_ref, date_shamsi, project_code, measurement_unit,
                created_by_user_id, created_by_user_id,
            ),
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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.id, p.customer_name, p.order_ref, p.date_shamsi, p.project_code,
                   COALESCE(p.measurement_unit, 'cm'), p.created_by_user_id,
                   p.assigned_to_user_id, creator.username, assignee.username
            FROM projects AS p
            LEFT JOIN users AS creator ON creator.id=p.created_by_user_id
            LEFT JOIN users AS assignee ON assignee.id=p.assigned_to_user_id
            WHERE p.id = ?
            """,
            (project_id,),
        )
        row = cursor.fetchone()
        if row:
            project_details = {
                "id": row[0],
                "customer_name": row[1],
                "order_ref": row[2],
                "date_shamsi": row[3],
                "project_code": row[4] if len(row) > 4 else None,
                "measurement_unit": row[5] if len(row) > 5 else "cm",
                "created_by_user_id": row[6],
                "assigned_to_user_id": row[7],
                "created_by_username": row[8],
                "assigned_to_username": row[9],
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


def user_can_edit_project_assignment(user_id, role, assigned_to_user_id):
    """Check edit access from project data already loaded by the caller."""
    if role in ("admin", "manager"):
        return True
    return bool(
        role == "staff"
        and user_id
        and assigned_to_user_id is not None
        and int(assigned_to_user_id) == int(user_id)
    )


def user_can_edit_project(user_id, role, project_id):
    """Managers edit every project; staff edit only their assigned projects."""
    if role in ("admin", "manager"):
        return True
    if role != "staff" or not user_id:
        return False
    conn = None
    try:
        conn = get_db_connection()
        row = conn.execute(
            "SELECT assigned_to_user_id FROM projects WHERE id=?",
            (project_id,),
        ).fetchone()
        return row is not None and user_can_edit_project_assignment(
            user_id, role, row[0]
        )
    except sqlite3.Error as exc:
        print(f"Error checking project ownership: {exc}")
        return False
    finally:
        if conn:
            conn.close()


def get_assignable_project_users():
    """Return active staff/managers who can be responsible for a project."""
    conn = None
    try:
        conn = get_db_connection()
        rows = conn.execute(
            """
            SELECT id, username, role FROM users
            WHERE is_active=1 AND role IN ('manager','staff')
            ORDER BY CASE role WHEN 'manager' THEN 0 ELSE 1 END, username
            """
        ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        print(f"Error loading assignable project users: {exc}")
        return []
    finally:
        if conn:
            conn.close()


def assign_project_user(project_id, new_user_id, actor_user_id):
    """Assign or unassign a project and record the complete assignment history."""
    conn = None
    try:
        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        project = conn.execute(
            "SELECT assigned_to_user_id FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if not project:
            conn.rollback()
            return False, "سفارش پیدا نشد."

        if new_user_id is not None:
            target = conn.execute(
                """
                SELECT id FROM users
                WHERE id=? AND is_active=1 AND role IN ('manager','staff')
                """,
                (new_user_id,),
            ).fetchone()
            if not target:
                conn.rollback()
                return False, "کاربر انتخاب‌شده نمی‌تواند مسئول سفارش باشد."

        previous_user_id = project[0]
        if previous_user_id == new_user_id:
            conn.rollback()
            return True, "مسئول سفارش تغییری نکرد."

        conn.execute(
            "UPDATE projects SET assigned_to_user_id=? WHERE id=?",
            (new_user_id, project_id),
        )
        conn.execute(
            """
            INSERT INTO project_assignment_logs(
                project_id, actor_user_id, previous_assignee_user_id,
                new_assignee_user_id, action, created_at
            ) VALUES (?, ?, ?, ?, 'assign', ?)
            """,
            (
                project_id, actor_user_id, previous_user_id, new_user_id,
                get_shamsi_datetime_iso(),
            ),
        )
        conn.commit()
        return True, "مسئول سفارش با موفقیت تغییر کرد."
    except sqlite3.Error as exc:
        if conn:
            conn.rollback()
        print(f"Error assigning project: {exc}")
        return False, "تغییر مسئول سفارش انجام نشد."
    finally:
        if conn:
            conn.close()


def get_project_assignment_logs(project_id, limit=20):
    conn = None
    try:
        conn = get_db_connection()
        rows = conn.execute(
            """
            SELECT l.created_at, l.action,
                   actor.username AS actor_username,
                   previous_user.username AS previous_username,
                   new_user.username AS new_username
            FROM project_assignment_logs AS l
            LEFT JOIN users AS actor ON actor.id=l.actor_user_id
            LEFT JOIN users AS previous_user ON previous_user.id=l.previous_assignee_user_id
            LEFT JOIN users AS new_user ON new_user.id=l.new_assignee_user_id
            WHERE l.project_id=? ORDER BY l.id DESC LIMIT ?
            """,
            (project_id, max(1, min(int(limit), 100))),
        ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        print(f"Error loading project assignment logs: {exc}")
        return []
    finally:
        if conn:
            conn.close()

def get_doors_for_project_db(project_id):
    """Get all doors for a project with custom values."""
    conn = None
    doors_dict = {}
    print(f"DEBUG: Entering get_doors_for_project_db for project ID: {project_id}")
    try:
        conn = get_db_connection()
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
        conn = get_db_connection()
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
        conn = get_db_connection()
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
        conn = get_db_connection()
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

def add_custom_column(column_name=None, display_name=None, column_type='text'):
    """Add a custom column, generating a stable internal key when omitted."""
    conn = None
    new_id = None
    try:
        display_name = " ".join(str(display_name or "").split())
        if not display_name or column_type not in ("text", "dropdown"):
            return None

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        # The temporary key and final key are written in one transaction. If any
        # step fails, no half-created column can remain in the database.
        generated_key = not column_name
        internal_key = column_name or f"__pending_{secrets.token_hex(12)}"
        cursor.execute(
            "INSERT INTO custom_columns (column_name, display_name, is_active, column_type) VALUES (?, ?, 1, ?)",
            (internal_key, display_name, column_type),
        )
        new_id = cursor.lastrowid
        if generated_key:
            cursor.execute(
                "UPDATE custom_columns SET column_name = ? WHERE id = ?",
                (f"custom_{new_id}", new_id),
            )
        conn.commit()
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
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
        conn = get_db_connection()
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


# These are the built-in order fields that existing projects already expect to
# see. User-created fields remain reusable, but start in the library for every
# other project until someone explicitly adds them there.
DEFAULT_PROJECT_CUSTOM_COLUMN_KEYS = {
    "rang",
    "noe_profile",
    "vaziat",
    "lola",
    "ghofl",
    "accessory",
    "kolaft",
    "dastgire",
    "tozihat",
}


def ensure_project_column_preferences(project_id):
    """Create durable per-project visibility rows without overwriting choices."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        cursor.execute(
            "SELECT column_key FROM project_visible_columns WHERE project_id = ?",
            (project_id,),
        )
        existing_keys = {row[0] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT DISTINCT cc.column_name
            FROM door_custom_values dcv
            JOIN doors d ON d.id = dcv.door_id
            JOIN custom_columns cc ON cc.id = dcv.column_id
            WHERE d.project_id = ?
              AND dcv.value IS NOT NULL
              AND TRIM(dcv.value) != ''
            """,
            (project_id,),
        )
        keys_with_data = {row[0] for row in cursor.fetchall()}

        cursor.execute(
            "SELECT column_name, is_active FROM custom_columns ORDER BY id"
        )
        for column_key, is_active in cursor.fetchall():
            if column_key in existing_keys:
                continue
            should_select = bool(
                column_key in keys_with_data
                or (column_key in DEFAULT_PROJECT_CUSTOM_COLUMN_KEYS and is_active)
            )
            # No row means the reusable field is still in the library. A row
            # with 0 means it belongs to this project but is temporarily hidden.
            if not should_select:
                continue
            cursor.execute(
                """
                INSERT INTO project_visible_columns(project_id, column_key, is_visible)
                VALUES (?, ?, ?)
                """,
                (project_id, column_key, 1),
            )

        conn.commit()
        return True
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in ensure_project_column_preferences: {e}")
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()


def get_project_custom_columns(project_id):
    """Return the shared field library with this project's selected state."""
    ensure_project_column_preferences(project_id)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                cc.id,
                cc.column_name,
                cc.display_name,
                cc.column_type,
                pvc.is_visible AS preference_state,
                COUNT(DISTINCT CASE
                    WHEN dcv.value IS NOT NULL AND TRIM(dcv.value) != ''
                    THEN d.project_id
                END) AS project_usage_count
            FROM custom_columns cc
            LEFT JOIN project_visible_columns pvc
                ON pvc.column_key = cc.column_name AND pvc.project_id = ?
            LEFT JOIN door_custom_values dcv ON dcv.column_id = cc.id
            LEFT JOIN doors d ON d.id = dcv.door_id
            GROUP BY cc.id, cc.column_name, cc.display_name, cc.column_type, pvc.is_visible
            ORDER BY cc.id
            """,
            (project_id,),
        )
        return [
            {
                "id": row[0],
                "key": row[1],
                "display": row[2],
                "type": row[3],
                "is_selected": row[4] is not None and int(row[4]) >= 0,
                "is_visible": row[4] is not None and int(row[4]) == 1,
                "project_usage_count": int(row[5] or 0),
            }
            for row in cursor.fetchall()
        ]
    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_project_custom_columns: {e}")
        traceback.print_exc()
        return []
    finally:
        if conn:
            conn.close()


def get_project_visible_custom_columns(project_id):
    """Return only fields selected for one project."""
    return [
        {
            "id": column["id"],
            "key": column["key"],
            "display": column["display"],
            "type": column["type"],
        }
        for column in get_project_custom_columns(project_id)
        if column["is_selected"] and column["is_visible"]
    ]


def set_project_column_visibility(project_id, column_id, is_visible):
    """Select or remove a shared field for one project only."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT column_name FROM custom_columns WHERE id = ?", (column_id,)
        )
        row = cursor.fetchone()
        if not row:
            return False
        column_key = row[0]
        cursor.execute(
            """
            INSERT INTO project_visible_columns(project_id, column_key, is_visible)
            VALUES (?, ?, ?)
            ON CONFLICT(project_id, column_key)
            DO UPDATE SET is_visible = excluded.is_visible
            """,
            (project_id, column_key, 1 if is_visible else 0),
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in set_project_column_visibility: {e}")
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()


def remove_project_column(project_id, column_id):
    """Move a field back to the library without touching any door values."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT column_name FROM custom_columns WHERE id = ?", (column_id,)
        )
        row = cursor.fetchone()
        if not row:
            return False
        # -1 is a durable 'not selected' marker. It prevents legacy data in the
        # field from automatically selecting it again during initialization.
        cursor.execute(
            """
            INSERT INTO project_visible_columns(project_id, column_key, is_visible)
            VALUES (?, ?, -1)
            ON CONFLICT(project_id, column_key)
            DO UPDATE SET is_visible = -1
            """,
            (project_id, row[0]),
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in remove_project_column: {e}")
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()

def get_column_id_by_key(column_key):
    """Find column ID by key."""
    conn = None
    column_id = None
    try:
        conn = get_db_connection()
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
        conn = get_db_connection()
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
        conn = get_db_connection()
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
        conn = get_db_connection()
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
        conn = get_db_connection()
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
        conn = get_db_connection()
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
        conn = get_db_connection()
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
                SELECT d.profile_type_id, d.color_id, d.color_name_snapshot,
                       d.quantity_deducted, pt.name as profile_name
                FROM inventory_deductions d
                JOIN profile_types pt ON d.profile_type_id = pt.id
                WHERE d.project_id = ?
            """, (project_id,))

            deductions = cursor.fetchall()

            if deductions:
                print(f"DEBUG: Found {len(deductions)} deduction(s) to return to inventory")

                for ded in deductions:
                    profile_id = ded['profile_type_id']
                    color_id = ded['color_id']
                    color_name = ded['color_name_snapshot']
                    quantity = ded['quantity_deducted']
                    profile_name = ded['profile_name']

                    # Ensure inventory row exists (older DBs may miss inventory_items for a profile)
                    cursor.execute(
                        "INSERT OR IGNORE INTO inventory_items (profile_type_id, color_id, quantity) VALUES (?, ?, 0)",
                        (profile_id, color_id),
                    )

                    # Return stock to inventory
                    cursor.execute("""
                        UPDATE inventory_items
                        SET quantity = quantity + ?, last_updated = CURRENT_TIMESTAMP
                        WHERE profile_type_id = ? AND color_id = ?
                    """, (quantity, profile_id, color_id))

                    # Log the return in inventory_logs
                    cursor.execute("""
                        INSERT INTO inventory_logs
                        (profile_type_id, color_id, color_name_snapshot, change_type,
                         quantity, description, timestamp)
                        VALUES (?, ?, ?, 'return_on_delete', ?, ?, ?)
                    """, (
                        profile_id,
                        color_id,
                        color_name,
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
        conn = get_db_connection()
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
        conn = get_db_connection()
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

def batch_update_doors_db(
    door_ids, base_fields_to_update, columns_to_update, project_id=None
):
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
                if project_id is None:
                    cursor.execute(
                        "SELECT location FROM doors WHERE id = ?", (door_id,)
                    )
                else:
                    cursor.execute(
                        "SELECT location FROM doors WHERE id = ? AND project_id = ?",
                        (door_id, project_id),
                    )
                door_info = cursor.fetchone()
                if not door_info:
                    failed_updates += 1
                    error_messages.append(
                        f"Door ID {door_id} does not belong to the selected project"
                    )
                    continue
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
                        if project_id is None:
                            query = f"UPDATE doors SET {', '.join(update_parts)} WHERE id = ?"
                            params.append(door_id)
                        else:
                            query = (
                                f"UPDATE doors SET {', '.join(update_parts)} "
                                "WHERE id = ? AND project_id = ?"
                            )
                            params.extend([door_id, project_id])

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

def get_all_profile_types(include_inactive=False):
    """دریافت تمام انواع پروفیل"""
    conn = None
    profiles = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        has_reservations = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_reservations'"
        ).fetchone()
        reserved_stock_expr = (
            "(SELECT COUNT(*) FROM inventory_reservations r "
            "WHERE r.profile_type_id=pt.id AND r.resource_type='stock' "
            "AND r.status='active')"
            if has_reservations
            else "0"
        )
        reserved_piece_expr = (
            "(SELECT COUNT(*) FROM inventory_reservations r "
            "WHERE r.profile_type_id=pt.id AND r.resource_type='piece' "
            "AND r.status='active')"
            if has_reservations
            else "0"
        )

        # دریافت اطلاعات پروفیل به همراه آمار موجودی
        query = f"""
        SELECT
            pt.*,
            COALESCE(SUM(ii.quantity), 0) as complete_count,
            (SELECT COUNT(*) FROM inventory_pieces ip WHERE ip.profile_type_id = pt.id) as cut_count,
            {reserved_stock_expr} AS reserved_complete_count,
            MAX(0,COALESCE(SUM(ii.quantity),0)-{reserved_stock_expr}) AS available_complete_count,
            {reserved_piece_expr} AS reserved_cut_count,
            MAX(0,(SELECT COUNT(*) FROM inventory_pieces ip WHERE ip.profile_type_id=pt.id)-{reserved_piece_expr}) AS available_cut_count,
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
        WHERE (? = 1 OR COALESCE(pt.is_active, 1) = 1)
        GROUP BY pt.id
        ORDER BY COALESCE(pt.is_active, 1) DESC, pt.name
        """

        cursor.execute(query, (1 if include_inactive else 0,))
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
        name = normalize_profile_name(name)
        if not name:
            return False, "نام پروفیل نمی‌تواند خالی باشد."
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM profile_types")
        if any(normalize_profile_name(row[0]) == name for row in cursor.fetchall()):
            return False, f"پروفیل با نام '{name}' قبلاً در سیستم وجود دارد. لطفاً نام دیگری انتخاب کنید."
        cursor.execute(
            "INSERT INTO profile_types (name, description, default_length, weight_per_meter, color, min_waste) VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, default_length, weight_per_meter, color, min_waste)
        )
        profile_id = cursor.lastrowid

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
        name = normalize_profile_name(name)
        if not name:
            return False
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM profile_types WHERE id != ?", (profile_id,))
        if any(normalize_profile_name(row[1]) == name for row in cursor.fetchall()):
            return False

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

def delete_profile_type(profile_id, actor_user_id=None, reason=""):
    """Delete an unused profile or archive a profile that has historical references."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT name, is_active FROM profile_types WHERE id = ?", (profile_id,))
        result = cursor.fetchone()
        if not result:
            return {"status": "not_found", "message": "پروفیل موردنظر پیدا نشد."}
        profile_name = result["name"]

        references = 0
        reference_queries = (
            ("inventory_items", "profile_type_id = ? AND quantity != 0"),
            ("inventory_pieces", "profile_type_id = ?"),
            ("inventory_logs", "profile_type_id = ?"),
            ("inventory_deductions", "profile_type_id = ?"),
            ("inventory_operation_items", "profile_type_id = ?"),
            ("inventory_waste_items", "profile_type_id = ?"),
        )
        for table, condition in reference_queries:
            cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            if cursor.fetchone():
                references += cursor.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {condition}", (profile_id,)
                ).fetchone()[0]
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM door_custom_values dcv
            JOIN custom_columns cc ON cc.id = dcv.column_id
            WHERE cc.column_name = 'noe_profile' AND TRIM(dcv.value) = TRIM(?)
            """,
            (profile_name,),
        )
        references += cursor.fetchone()[0]

        if references:
            reason = str(reason or "").strip()
            if len(reason) < 3:
                return {
                    "status": "validation_error",
                    "message": "این پروفیل استفاده شده است؛ برای بایگانی، ثبت دلیل الزامی است.",
                }
            cursor.execute(
                """
                UPDATE profile_types
                SET is_active=0, archived_at=?, archived_by_user_id=?, archive_reason=?
                WHERE id=?
                """,
                (get_shamsi_datetime_iso(), actor_user_id, reason, profile_id),
            )
            _remove_profile_from_dropdown(cursor, profile_name)
            status = "archived"
            message = "پروفیل به‌دلیل داشتن سابقه، با موفقیت بایگانی شد."
        else:
            cursor.execute("DELETE FROM inventory_items WHERE profile_type_id = ?", (profile_id,))
            cursor.execute("DELETE FROM profile_types WHERE id = ?", (profile_id,))
            _remove_profile_from_dropdown(cursor, profile_name)
            status = "deleted"
            message = "پروفیل بلااستفاده با موفقیت حذف شد."

        conn.commit()
        return {"status": status, "message": message, "references": references}
    except sqlite3.Error as e:
        print(f"!!!!!! Error in delete_profile_type: {e}")
        traceback.print_exc()
        return {"status": "database_error", "message": "حذف یا بایگانی پروفیل انجام نشد."}
    finally:
        if conn:
            conn.close()


def reactivate_profile_type(profile_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM profile_types WHERE id=?", (profile_id,))
        row = cursor.fetchone()
        if not row:
            return False
        cursor.execute(
            """
            UPDATE profile_types
            SET is_active=1, archived_at=NULL, archived_by_user_id=NULL, archive_reason=NULL
            WHERE id=?
            """,
            (profile_id,),
        )
        _sync_profile_to_dropdown(cursor, row["name"])
        conn.commit()
        return True
    except sqlite3.Error:
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_profile_details(profile_id):
    """دریافت جزئیات یک پروفیل خاص"""
    conn = None
    profile = None
    try:
        conn = get_db_connection()
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

INVENTORY_SETTING_DEFAULTS = {
    "default_wastage": 20,
    "min_remaining_length": 20,
    "use_inventory_for_cutting": True,
    "prefer_inventory_pieces": True,
    "inventory_optimization_strategy": "minimize_waste",
    "show_inventory_warnings": True,
    "low_inventory_threshold": 5,
}

INVENTORY_SETTING_ALIASES = {
    "use_inventory_for_cutting": "use_inventory",
    "prefer_inventory_pieces": "prefer_pieces",
}


def get_inventory_settings():
    """Return canonical inventory settings while accepting legacy setting names."""
    conn = None
    settings = {}
    try:
        conn = get_db_connection()
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

        for canonical_name, legacy_name in INVENTORY_SETTING_ALIASES.items():
            if canonical_name not in settings and legacy_name in settings:
                settings[canonical_name] = settings[legacy_name]
        for name, value in INVENTORY_SETTING_DEFAULTS.items():
            settings.setdefault(name, value)

    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_inventory_settings: {e}")
    finally:
        if conn:
            conn.close()
    return settings

def update_inventory_settings(new_settings):
    """Store canonical settings and keep legacy aliases synchronized."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        for name, value in new_settings.items():
            cursor.execute(
                "INSERT OR REPLACE INTO cutting_settings (name, value) VALUES (?, ?)",
                (name, str(value))
            )
            legacy_name = INVENTORY_SETTING_ALIASES.get(name)
            if legacy_name:
                cursor.execute(
                    "INSERT OR REPLACE INTO cutting_settings (name, value) VALUES (?, ?)",
                    (legacy_name, str(value)),
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
        "average_piece_length": 0,
        "reserved_complete_pieces": 0,
        "reserved_cut_pieces": 0,
        "available_complete_pieces": 0,
        "available_cut_pieces": 0,
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
        cursor.execute("SELECT COUNT(*) FROM profile_types WHERE COALESCE(is_active,1)=1")
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

        if cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_reservations'"
        ).fetchone():
            stats["reserved_complete_pieces"] = int(
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM inventory_reservations
                    WHERE resource_type='stock' AND status='active'
                    """
                ).fetchone()[0]
            )
            stats["reserved_cut_pieces"] = int(
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM inventory_reservations
                    WHERE resource_type='piece' AND status='active'
                    """
                ).fetchone()[0]
            )
        stats["available_complete_pieces"] = max(
            0,
            int(stats["total_complete_pieces"] or 0)
            - stats["reserved_complete_pieces"],
        )
        stats["available_cut_pieces"] = max(
            0,
            int(stats["total_cut_pieces"] or 0) - stats["reserved_cut_pieces"],
        )

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

def _get_profile_name_for_operation(cursor, profile_id):
    cursor.execute("SELECT name FROM profile_types WHERE id = ?", (profile_id,))
    row = cursor.fetchone()
    if not row:
        raise sqlite3.IntegrityError(f"Profile {profile_id} not found")
    return row["name"]


def _active_stock_reservations(cursor, profile_id, color_id):
    if not cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_reservations'"
    ).fetchone():
        return 0
    return int(
        cursor.execute(
            """
            SELECT COUNT(*) FROM inventory_reservations
            WHERE profile_type_id=? AND color_id=?
              AND resource_type='stock' AND status='active'
            """,
            (profile_id, color_id),
        ).fetchone()[0]
    )


def _inventory_piece_is_reserved(cursor, piece_id):
    if not cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_reservations'"
    ).fetchone():
        return False
    return (
        cursor.execute(
            """
            SELECT 1 FROM inventory_reservations
            WHERE inventory_piece_id=? AND resource_type='piece' AND status='active'
            """,
            (piece_id,),
        ).fetchone()
        is not None
    )


def _get_color_for_operation(cursor, color_id=None, color_name=None):
    if color_id is not None:
        cursor.execute(
            "SELECT id, name, hex_code FROM profile_colors WHERE id = ? AND is_active = 1",
            (int(color_id),),
        )
    elif str(color_name or "").strip():
        cursor.execute(
            "SELECT id, name, hex_code FROM profile_colors WHERE name = ? AND is_active = 1",
            (str(color_name).strip(),),
        )
    else:
        cursor.execute(
            "SELECT id, name, hex_code FROM profile_colors WHERE name = 'تعیین‌نشده'"
        )
    row = cursor.fetchone()
    if not row:
        raise sqlite3.IntegrityError("رنگ پروفیل معتبر نیست.")
    return dict(row)


def get_profile_colors(active_only=True):
    """Return the user-manageable physical profile colors."""
    conn = None
    try:
        conn = get_db_connection()
        query = "SELECT * FROM profile_colors"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY CASE WHEN name = 'تعیین‌نشده' THEN 1 ELSE 0 END, name"
        return [dict(row) for row in conn.execute(query).fetchall()]
    except sqlite3.Error as exc:
        print(f"!!!!!! Error in get_profile_colors: {exc}")
        return []
    finally:
        if conn:
            conn.close()


def add_profile_color(name, hex_code="#9ca3af"):
    """Create a physical stock color and expose it in the door-color dropdown."""
    name = " ".join(str(name or "").split())
    hex_code = str(hex_code or "#9ca3af").strip()
    if not name:
        return False, "نام رنگ الزامی است."
    if len(hex_code) != 7 or not hex_code.startswith("#"):
        return False, "کد رنگ باید به شکل #RRGGBB باشد."
    try:
        int(hex_code[1:], 16)
    except ValueError:
        return False, "کد رنگ معتبر نیست."
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO profile_colors (name, hex_code) VALUES (?, ?)",
            (name, hex_code.lower()),
        )
        color_id = cursor.lastrowid
        cursor.execute("SELECT id FROM custom_columns WHERE column_name = 'rang'")
        column = cursor.fetchone()
        if column:
            cursor.execute(
                "INSERT OR IGNORE INTO custom_column_options (column_id, option_value) VALUES (?, ?)",
                (column["id"], name),
            )
        conn.commit()
        return True, color_id
    except sqlite3.IntegrityError:
        return False, f"رنگ «{name}» قبلاً تعریف شده است."
    except sqlite3.Error as exc:
        if conn:
            conn.rollback()
        return False, str(exc)
    finally:
        if conn:
            conn.close()


def _create_inventory_operation(
    cursor,
    operation_type,
    description="",
    project_id=None,
    actor_user_id=None,
    is_reversible=True,
    reverses_operation_id=None,
):
    cursor.execute(
        """
        INSERT INTO inventory_operations
            (operation_type, project_id, actor_user_id, description, status,
             is_reversible, created_at, reverses_operation_id)
        VALUES (?, ?, ?, ?, 'applied', ?, ?, ?)
        """,
        (
            operation_type,
            project_id,
            actor_user_id,
            description,
            1 if is_reversible else 0,
            get_shamsi_datetime_iso(),
            reverses_operation_id,
        ),
    )
    return cursor.lastrowid


def _record_inventory_operation_item(
    cursor,
    operation_id,
    sequence_no,
    action_type,
    profile_id,
    profile_name,
    quantity_delta=None,
    before_quantity=None,
    after_quantity=None,
    piece_id=None,
    length=None,
    color_id=None,
    color_name=None,
):
    cursor.execute(
        """
        INSERT INTO inventory_operation_items
            (operation_id, sequence_no, action_type, profile_type_id, profile_name,
             quantity_delta, before_quantity, after_quantity, piece_id, length,
             color_id, color_name_snapshot)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            operation_id,
            sequence_no,
            action_type,
            profile_id,
            profile_name,
            quantity_delta,
            before_quantity,
            after_quantity,
            piece_id,
            length,
            color_id,
            color_name,
        ),
    )


def add_inventory_stock(profile_id, quantity, description="", actor_user_id=None, color_id=None):
    """افزودن موجودی شاخه کامل"""
    conn = None
    try:
        quantity = int(quantity)
        if quantity <= 0:
            return False
        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        profile_name = _get_profile_name_for_operation(cursor, profile_id)
        color = _get_color_for_operation(cursor, color_id=color_id)

        # Ensure inventory row exists
        cursor.execute(
            "INSERT OR IGNORE INTO inventory_items (profile_type_id, color_id, quantity) VALUES (?, ?, 0)",
            (profile_id, color["id"]),
        )
        cursor.execute(
            "SELECT quantity FROM inventory_items WHERE profile_type_id = ? AND color_id = ?",
            (profile_id, color["id"]),
        )
        before_quantity = int(cursor.fetchone()["quantity"])
        after_quantity = before_quantity + quantity
        operation_id = _create_inventory_operation(
            cursor,
            "manual_add_stock",
            description=description,
            actor_user_id=actor_user_id,
        )

        # به‌روزرسانی موجودی
        cursor.execute(
            "UPDATE inventory_items SET quantity = ?, last_updated = CURRENT_TIMESTAMP WHERE profile_type_id = ? AND color_id = ?",
            (after_quantity, profile_id, color["id"]),
        )
        _record_inventory_operation_item(
            cursor,
            operation_id,
            1,
            "stock_delta",
            profile_id,
            profile_name,
            quantity_delta=quantity,
            before_quantity=before_quantity,
            after_quantity=after_quantity,
            color_id=color["id"],
            color_name=color["name"],
        )

        # ثبت در لاگ
        cursor.execute(
            """
            INSERT INTO inventory_logs
                (profile_type_id, color_id, color_name_snapshot, change_type, quantity,
                 description, timestamp, operation_id)
            VALUES (?, ?, ?, 'add_stock', ?, ?, ?, ?)
            """,
            (profile_id, color["id"], color["name"], quantity, description,
             get_shamsi_datetime_iso(), operation_id),
        )

        conn.commit()
        return True
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in add_inventory_stock: {e}")
        return False
    finally:
        if conn:
            conn.close()

def remove_inventory_stock(
    profile_id,
    quantity,
    description="",
    project_id=None,
    actor_user_id=None,
    color_id=None,
):
    """کسر موجودی شاخه کامل"""
    conn = None
    try:
        quantity = int(quantity)
        if quantity <= 0:
            return False, "تعداد باید بزرگتر از صفر باشد."
        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        profile_name = _get_profile_name_for_operation(cursor, profile_id)
        color = _get_color_for_operation(cursor, color_id=color_id)

        # بررسی آیا این پروفیل قبلاً برای این پروژه کسر شده؟
        if project_id:
            cursor.execute(
                "SELECT quantity_deducted FROM inventory_deductions WHERE project_id = ? AND profile_type_id = ? AND color_id = ?",
                (project_id, profile_id, color["id"])
            )
            existing_deduction = cursor.fetchone()
            if existing_deduction:
                return False, f"این پروفیل قبلاً برای این پروژه کسر شده است ({existing_deduction[0]} شاخه)."

        # بررسی موجودی فعلی
        cursor.execute(
            "SELECT quantity FROM inventory_items WHERE profile_type_id = ? AND color_id = ?",
            (profile_id, color["id"]),
        )
        row = cursor.fetchone()
        current_qty = row[0] if row else 0
        reserved_qty = _active_stock_reservations(cursor, profile_id, color["id"])

        if current_qty - reserved_qty < quantity:
            conn.rollback()
            return False, (
                f"موجودی آزاد کافی نیست؛ {reserved_qty} شاخه برای سفارش برش رزرو شده است."
            )
        after_quantity = current_qty - quantity
        operation_id = _create_inventory_operation(
            cursor,
            "manual_remove_stock" if project_id is None else "project_stock_deduction",
            description=description,
            project_id=project_id,
            actor_user_id=actor_user_id,
        )

        # به‌روزرسانی موجودی
        cursor.execute(
            "UPDATE inventory_items SET quantity = ?, last_updated = CURRENT_TIMESTAMP WHERE profile_type_id = ? AND color_id = ?",
            (after_quantity, profile_id, color["id"]),
        )
        _record_inventory_operation_item(
            cursor,
            operation_id,
            1,
            "stock_delta",
            profile_id,
            profile_name,
            quantity_delta=-quantity,
            before_quantity=current_qty,
            after_quantity=after_quantity,
            color_id=color["id"],
            color_name=color["name"],
        )

        # ثبت در لاگ
        cursor.execute(
            """
            INSERT INTO inventory_logs
                (profile_type_id, color_id, color_name_snapshot, change_type, quantity,
                 project_id, description, timestamp, operation_id)
            VALUES (?, ?, ?, 'remove_stock', ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                color["id"],
                color["name"],
                quantity,
                project_id,
                description,
                get_shamsi_datetime_iso(),
                operation_id,
            ),
        )

        # ثبت در جدول کسرهای انبار برای جلوگیری از کسر دوباره
        if project_id:
            cursor.execute(
                """
                INSERT INTO inventory_deductions
                    (project_id, profile_type_id, color_id, color_name_snapshot, quantity_deducted)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, profile_id, color["id"], color["name"], quantity)
            )

        conn.commit()
        return True, ""
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in remove_inventory_stock: {e}")
        return False, str(e)
    finally:
        if conn:
            conn.close()

def add_inventory_piece(
    profile_id,
    length,
    description="",
    project_id=None,
    actor_user_id=None,
    color_id=None,
):
    """افزودن تکه شاخه (برش خورده/ضایعات مفید)"""
    conn = None
    try:
        length = float(length)
        if not math.isfinite(length) or length <= 0:
            return False
        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        profile_name = _get_profile_name_for_operation(cursor, profile_id)
        color = _get_color_for_operation(cursor, color_id=color_id)
        operation_id = _create_inventory_operation(
            cursor,
            "manual_add_piece",
            description=description,
            project_id=project_id,
            actor_user_id=actor_user_id,
        )

        cursor.execute(
            "INSERT INTO inventory_pieces (profile_type_id, color_id, length) VALUES (?, ?, ?)",
            (profile_id, color["id"], length)
        )
        piece_id = cursor.lastrowid
        _record_inventory_operation_item(
            cursor,
            operation_id,
            1,
            "piece_add",
            profile_id,
            profile_name,
            piece_id=piece_id,
            length=length,
            color_id=color["id"],
            color_name=color["name"],
        )

        # ثبت در لاگ (با project_id اگر ارائه شده باشد)
        cursor.execute(
            """
            INSERT INTO inventory_logs
                (profile_type_id, color_id, color_name_snapshot, change_type, length,
                 piece_id, project_id, description, timestamp, operation_id)
            VALUES (?, ?, ?, 'add_piece', ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                color["id"],
                color["name"],
                length,
                piece_id,
                project_id,
                description,
                get_shamsi_datetime_iso(),
                operation_id,
            ),
        )

        conn.commit()
        return True
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in add_inventory_piece: {e}")
        return False
    finally:
        if conn:
            conn.close()

def remove_inventory_piece(
    piece_id,
    description="",
    project_id=None,
    actor_user_id=None,
):
    """حذف تکه شاخه (استفاده شده)"""
    conn = None
    try:
        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()

        # دریافت اطلاعات قطعه قبل از حذف
        cursor.execute(
            "SELECT profile_type_id, color_id, length FROM inventory_pieces WHERE id = ?",
            (piece_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False, "قطعه یافت نشد."
        if _inventory_piece_is_reserved(cursor, piece_id):
            conn.rollback()
            return False, "این قطعه برای یک سفارش برش رزرو شده و قابل حذف نیست."

        profile_id, color_id, length = row
        profile_name = _get_profile_name_for_operation(cursor, profile_id)
        color = _get_color_for_operation(cursor, color_id=color_id)
        operation_id = _create_inventory_operation(
            cursor,
            "manual_remove_piece",
            description=description,
            project_id=project_id,
            actor_user_id=actor_user_id,
        )

        cursor.execute("DELETE FROM inventory_pieces WHERE id = ?", (piece_id,))
        _record_inventory_operation_item(
            cursor,
            operation_id,
            1,
            "piece_remove",
            profile_id,
            profile_name,
            piece_id=piece_id,
            length=length,
            color_id=color["id"],
            color_name=color["name"],
        )

        # ثبت در لاگ
        cursor.execute(
            """
            INSERT INTO inventory_logs
                (profile_type_id, color_id, color_name_snapshot, change_type, length,
                 piece_id, project_id, description, timestamp, operation_id)
            VALUES (?, ?, ?, 'remove_piece', ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                color["id"],
                color["name"],
                length,
                piece_id,
                project_id,
                description,
                get_shamsi_datetime_iso(),
                operation_id,
            ),
        )

        conn.commit()
        return True, ""
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in remove_inventory_piece: {e}")
        return False, str(e)
    finally:
        if conn:
            conn.close()


def transfer_inventory_stock_color(
    profile_id, source_color_id, target_color_id, quantity, actor_user_id=None, reason=""
):
    """Reclassify existing full stock from one physical color to another."""
    conn = None
    try:
        quantity = int(quantity)
        if quantity <= 0 or int(source_color_id) == int(target_color_id):
            return False, "مبدأ، مقصد یا تعداد انتقال معتبر نیست."
        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        profile_name = _get_profile_name_for_operation(cursor, profile_id)
        source = _get_color_for_operation(cursor, color_id=source_color_id)
        target = _get_color_for_operation(cursor, color_id=target_color_id)
        cursor.execute(
            "SELECT quantity FROM inventory_items WHERE profile_type_id=? AND color_id=?",
            (profile_id, source["id"]),
        )
        row = cursor.fetchone()
        source_before = int(row["quantity"]) if row else 0
        source_reserved = _active_stock_reservations(
            cursor, profile_id, source["id"]
        )
        if source_before - source_reserved < quantity:
            conn.rollback()
            return False, "موجودی آزاد رنگ مبدأ برای انتقال کافی نیست."
        cursor.execute(
            "INSERT OR IGNORE INTO inventory_items (profile_type_id,color_id,quantity) VALUES (?,?,0)",
            (profile_id, target["id"]),
        )
        target_before = int(
            cursor.execute(
                "SELECT quantity FROM inventory_items WHERE profile_type_id=? AND color_id=?",
                (profile_id, target["id"]),
            ).fetchone()["quantity"]
        )
        operation_id = _create_inventory_operation(
            cursor,
            "stock_color_transfer",
            description=(
                f"انتقال {quantity} شاخه از {source['name']} به {target['name']}"
                + (f" — دلیل: {str(reason).strip()}" if str(reason).strip() else "")
            ),
            actor_user_id=actor_user_id,
        )
        for sequence, color, delta, before in (
            (1, source, -quantity, source_before),
            (2, target, quantity, target_before),
        ):
            after = before + delta
            cursor.execute(
                "UPDATE inventory_items SET quantity=?,last_updated=CURRENT_TIMESTAMP WHERE profile_type_id=? AND color_id=?",
                (after, profile_id, color["id"]),
            )
            _record_inventory_operation_item(
                cursor, operation_id, sequence, "stock_delta", profile_id, profile_name,
                quantity_delta=delta, before_quantity=before, after_quantity=after,
                color_id=color["id"], color_name=color["name"],
            )
            cursor.execute(
                """
                INSERT INTO inventory_logs
                    (profile_type_id,color_id,color_name_snapshot,change_type,quantity,
                     description,timestamp,operation_id)
                VALUES (?,?,?,'transfer_color',?,?,?,?)
                """,
                (profile_id, color["id"], color["name"], abs(delta),
                 f"انتقال رنگ: {source['name']} ← {target['name']}؛ {str(reason).strip()}",
                 get_shamsi_datetime_iso(), operation_id),
            )
        conn.commit()
        return True, ""
    except (TypeError, ValueError, sqlite3.Error) as exc:
        if conn:
            conn.rollback()
        return False, str(exc)
    finally:
        if conn:
            conn.close()


def correct_inventory_stock(profile_id, color_id, quantity_delta, reason, actor_user_id=None):
    """Apply an explicit, auditable admin correction to full-stock quantity."""
    reason = str(reason or "").strip()
    try:
        quantity_delta = int(quantity_delta)
    except (TypeError, ValueError):
        return {"status": "validation_error", "message": "مقدار اصلاح معتبر نیست."}
    if quantity_delta == 0:
        return {"status": "validation_error", "message": "مقدار اصلاح نمی‌تواند صفر باشد."}
    if len(reason) < 3:
        return {"status": "validation_error", "message": "ثبت دلیل اصلاح الزامی است."}

    conn = None
    try:
        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        profile_name = _get_profile_name_for_operation(cursor, profile_id)
        color = _get_color_for_operation(cursor, color_id=color_id)
        cursor.execute(
            "INSERT OR IGNORE INTO inventory_items (profile_type_id,color_id,quantity) VALUES (?,?,0)",
            (profile_id, color["id"]),
        )
        before = int(
            cursor.execute(
                "SELECT quantity FROM inventory_items WHERE profile_type_id=? AND color_id=?",
                (profile_id, color["id"]),
            ).fetchone()["quantity"]
        )
        after = before + quantity_delta
        reserved_qty = _active_stock_reservations(cursor, profile_id, color["id"])
        if after < reserved_qty:
            conn.rollback()
            return {
                "status": "validation_error",
                "message": (
                    f"این اصلاح موجودی را از تعداد رزروشده کمتر می‌کند؛ "
                    f"موجودی فیزیکی {before} و رزرو فعال {reserved_qty} شاخه است."
                ),
            }
        operation_id = _create_inventory_operation(
            cursor,
            "admin_stock_correction",
            description=f"اصلاح موجودی {profile_name} — {color['name']}: {before} ← {after}؛ دلیل: {reason}",
            actor_user_id=actor_user_id,
        )
        cursor.execute(
            "UPDATE inventory_items SET quantity=?,last_updated=CURRENT_TIMESTAMP WHERE profile_type_id=? AND color_id=?",
            (after, profile_id, color["id"]),
        )
        _record_inventory_operation_item(
            cursor, operation_id, 1, "stock_delta", profile_id, profile_name,
            quantity_delta=quantity_delta, before_quantity=before, after_quantity=after,
            color_id=color["id"], color_name=color["name"],
        )
        cursor.execute(
            """
            INSERT INTO inventory_logs
                (profile_type_id,color_id,color_name_snapshot,change_type,quantity,
                 description,timestamp,operation_id)
            VALUES (?,?,?,'stock_correction',?,?,?,?)
            """,
            (profile_id, color["id"], color["name"], abs(quantity_delta),
             f"اصلاح ادمین: {before} ← {after}؛ دلیل: {reason}",
             get_shamsi_datetime_iso(), operation_id),
        )
        conn.commit()
        return {
            "status": "success",
            "message": f"موجودی از {before} به {after} شاخه اصلاح شد.",
            "operation_id": operation_id,
        }
    except (TypeError, ValueError, sqlite3.Error) as exc:
        if conn:
            conn.rollback()
        return {"status": "database_error", "message": f"اصلاح موجودی انجام نشد: {exc}"}
    finally:
        if conn:
            conn.close()


def get_inventory_correction_center_data(operation_limit=50):
    """Return stock variants, reusable pieces and recent audit operations for admins."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        profiles = [
            dict(row) for row in cursor.execute(
                "SELECT id,name FROM profile_types WHERE COALESCE(is_active,1)=1 ORDER BY name"
            ).fetchall()
        ]
        colors = [
            dict(row) for row in cursor.execute(
                "SELECT id,name,hex_code FROM profile_colors WHERE is_active=1 ORDER BY name"
            ).fetchall()
        ]
        stock = [
            dict(row) for row in cursor.execute(
                """
                SELECT ii.profile_type_id,pt.name AS profile_name,ii.color_id,
                       pc.name AS color_name,ii.quantity
                FROM inventory_items ii
                JOIN profile_types pt ON pt.id=ii.profile_type_id
                JOIN profile_colors pc ON pc.id=ii.color_id
                WHERE ii.quantity != 0 ORDER BY pt.name,pc.name
                """
            ).fetchall()
        ]
        pieces = [
            dict(row) for row in cursor.execute(
                """
                SELECT ip.id,ip.profile_type_id,pt.name AS profile_name,ip.color_id,
                       pc.name AS color_name,ip.length,ip.created_at
                FROM inventory_pieces ip
                JOIN profile_types pt ON pt.id=ip.profile_type_id
                JOIN profile_colors pc ON pc.id=ip.color_id
                ORDER BY ip.id DESC LIMIT 300
                """
            ).fetchall()
        ]
        operations = [
            dict(row) for row in cursor.execute(
                """
                SELECT o.*,u.username AS actor_username
                FROM inventory_operations o
                LEFT JOIN users u ON u.id=o.actor_user_id
                ORDER BY o.id DESC LIMIT ?
                """,
                (int(operation_limit),),
            ).fetchall()
        ]
        return {"profiles": profiles, "colors": colors, "stock": stock,
                "pieces": pieces, "operations": operations}
    except sqlite3.Error as exc:
        print(f"!!!!!! Error in get_inventory_correction_center_data: {exc}")
        return {"profiles": [], "colors": [], "stock": [], "pieces": [], "operations": []}
    finally:
        if conn:
            conn.close()


def get_inventory_cutting_application_status(project_id):
    """Return the reliable application state for a project's cutting plan."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'inventory_cutting_applications'"
        )
        if cursor.fetchone():
            cursor.execute(
                "SELECT * FROM inventory_cutting_applications WHERE project_id = ?",
                (project_id,),
            )
            application = cursor.fetchone()
            if application:
                return {"status": "completed", "application": dict(application), "deductions": []}

        cursor.execute(
            """
            SELECT d.profile_type_id, d.quantity_deducted, d.deduction_date,
                   pt.name AS profile_name, d.color_name_snapshot AS color_name
            FROM inventory_deductions d
            JOIN profile_types pt ON pt.id = d.profile_type_id
            WHERE d.project_id = ?
            ORDER BY d.deduction_date
            """,
            (project_id,),
        )
        deductions = [dict(row) for row in cursor.fetchall()]
        if deductions:
            # Records created before the transactional application marker cannot prove
            # that every profile and every inventory piece was handled successfully.
            return {"status": "legacy_unverified", "application": None, "deductions": deductions}

        return {"status": "not_applied", "application": None, "deductions": []}
    except sqlite3.Error as exc:
        print(f"!!!!!! Error in get_inventory_cutting_application_status: {exc}")
        return {"status": "error", "application": None, "deductions": [], "error": str(exc)}
    finally:
        if conn:
            conn.close()


def apply_cutting_plan_inventory_transaction(
    project_id,
    project_info,
    profile_requirements,
    used_inventory_pieces=None,
    actor_user_id=None,
    plan_snapshot=None,
):
    """
    Apply a complete cutting plan to inventory in one SQLite transaction.

    Validation is performed for every profile and inventory piece before the first
    mutation. Any later failure rolls back stock, pieces, logs, deductions and the
    completion marker together.
    """
    used_inventory_pieces = used_inventory_pieces or {}
    try:
        plan_snapshot_json = (
            json.dumps(plan_snapshot, ensure_ascii=False, separators=(",", ":"))
            if plan_snapshot is not None
            else None
        )
    except (TypeError, ValueError) as exc:
        return {
            "status": "validation_error",
            "errors": [f"نسخه ذخیره‌شده طرح برش معتبر نیست: {exc}"],
        }
    conn = None
    try:
        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM inventory_cutting_applications WHERE project_id = ?",
            (project_id,),
        )
        completed = cursor.fetchone()
        if completed:
            conn.rollback()
            return {"status": "already_applied", "application": dict(completed)}

        cursor.execute(
            """
            SELECT d.profile_type_id, d.quantity_deducted, d.deduction_date,
                   pt.name AS profile_name, d.color_name_snapshot AS color_name
            FROM inventory_deductions d
            JOIN profile_types pt ON pt.id = d.profile_type_id
            WHERE d.project_id = ?
            ORDER BY d.deduction_date
            """,
            (project_id,),
        )
        legacy_deductions = [dict(row) for row in cursor.fetchall()]
        if legacy_deductions:
            conn.rollback()
            return {
                "status": "legacy_unverified",
                "deductions": legacy_deductions,
                "errors": [
                    "برای این پروژه سابقه کسر قدیمی یا نیمه‌کاره وجود دارد و ادامه خودکار آن امن نیست."
                ],
            }

        cursor.execute(
            "SELECT id, name, default_length, min_waste, weight_per_meter FROM profile_types"
        )
        profiles_by_name = {}
        ambiguous_profile_names = set()
        for row in cursor.fetchall():
            normalized_name = normalize_profile_name(row["name"])
            if normalized_name in profiles_by_name:
                ambiguous_profile_names.add(normalized_name)
                profiles_by_name.pop(normalized_name, None)
            elif normalized_name not in ambiguous_profile_names:
                profiles_by_name[normalized_name] = dict(row)

        errors = []
        prepared_profiles = []
        all_piece_ids = set()

        normalized_used_inventory_pieces = {
            str(name): piece_ids for name, piece_ids in used_inventory_pieces.items()
        }
        normalized_requirement_names = {str(name) for name in profile_requirements}
        extra_piece_profiles = set(normalized_used_inventory_pieces) - normalized_requirement_names
        if extra_piece_profiles:
            errors.append(
                "اطلاعات قطعات مصرفی با طرح برش هماهنگ نیست؛ لطفاً گزارش برش را دوباره محاسبه کنید."
            )

        for variant_key, profile_data in profile_requirements.items():
            variant_key = str(variant_key)
            profile_name = normalize_profile_name(
                profile_data.get("profile_name", variant_key)
                if isinstance(profile_data, dict) else variant_key
            )
            color_name = (
                profile_data.get("color_name", "تعیین‌نشده")
                if isinstance(profile_data, dict) else "تعیین‌نشده"
            )
            try:
                color = _get_color_for_operation(cursor, color_name=color_name)
            except sqlite3.IntegrityError:
                errors.append(
                    f"رنگ «{color_name}» برای پروفیل «{profile_name}» در انبار تعریف نشده است."
                )
                continue
            if profile_name in ambiguous_profile_names:
                errors.append(
                    f"بیش از یک پروفیل با نام «{profile_name}» در انبار وجود دارد؛ "
                    "ابتدا نام‌های تکراری را اصلاح کنید."
                )
                continue
            profile = profiles_by_name.get(profile_name)
            if not profile:
                errors.append(
                    f"پروفیل «{profile_name}» در انبار تعریف نشده است."
                )
                continue

            bins = profile_data.get("bins", []) if isinstance(profile_data, dict) else []
            if not isinstance(bins, list):
                errors.append(f"اطلاعات طرح برش پروفیل «{profile_name}» معتبر نیست.")
                continue
            if any(not isinstance(bin_data, dict) for bin_data in bins):
                errors.append(f"اطلاعات شاخه‌های پروفیل «{profile_name}» معتبر نیست.")
                continue

            new_bins_count = sum(
                1 for bin_data in bins
                if isinstance(bin_data, dict) and not bin_data.get("from_inventory_piece", False)
            )
            inventory_bins = [
                bin_data for bin_data in bins
                if isinstance(bin_data, dict) and bin_data.get("from_inventory_piece", False)
            ]

            declared_piece_ids = normalized_used_inventory_pieces.get(variant_key, [])
            if not isinstance(declared_piece_ids, list):
                errors.append(f"فهرست قطعات مصرفی پروفیل «{profile_name}» معتبر نیست.")
                continue

            try:
                declared_piece_ids = [int(piece_id) for piece_id in declared_piece_ids]
            except (TypeError, ValueError):
                errors.append(f"شناسه قطعات مصرفی پروفیل «{profile_name}» معتبر نیست.")
                continue

            if len(declared_piece_ids) != len(inventory_bins):
                errors.append(
                    f"تعداد قطعات مصرفی پروفیل «{profile_name}» با طرح برش هماهنگ نیست؛ "
                    "لطفاً گزارش برش را دوباره محاسبه کنید."
                )
                continue

            embedded_piece_ids = [bin_data.get("inventory_piece_id") for bin_data in inventory_bins]
            if all(piece_id is not None for piece_id in embedded_piece_ids):
                try:
                    embedded_piece_ids = [int(piece_id) for piece_id in embedded_piece_ids]
                except (TypeError, ValueError):
                    errors.append(f"شناسه قطعات طرح برش پروفیل «{profile_name}» معتبر نیست.")
                    continue
                if embedded_piece_ids != declared_piece_ids:
                    errors.append(
                        f"قطعات مصرفی پروفیل «{profile_name}» تغییر کرده‌اند؛ "
                        "لطفاً گزارش برش را دوباره محاسبه کنید."
                    )
                    continue

            prepared_pieces = []
            for piece_id, bin_data in zip(declared_piece_ids, inventory_bins):
                if piece_id in all_piece_ids:
                    errors.append(f"قطعه انبار با شناسه {piece_id} بیش از یک‌بار در طرح استفاده شده است.")
                    continue
                all_piece_ids.add(piece_id)

                cursor.execute(
                    "SELECT id, profile_type_id, color_id, length FROM inventory_pieces WHERE id = ?",
                    (piece_id,),
                )
                piece = cursor.fetchone()
                if not piece:
                    errors.append(
                        f"قطعه انتخاب‌شده برای پروفیل «{profile_name}» دیگر در انبار موجود نیست؛ "
                        "لطفاً گزارش برش را دوباره محاسبه کنید."
                    )
                    continue
                if piece["profile_type_id"] != profile["id"]:
                    errors.append(f"قطعه {piece_id} متعلق به پروفیل «{profile_name}» نیست.")
                    continue
                if piece["color_id"] != color["id"]:
                    errors.append(
                        f"رنگ قطعه {piece_id} با رنگ «{color['name']}» پروژه هماهنگ نیست."
                    )
                    continue
                try:
                    planned_initial_length = float(
                        bin_data.get("initial_length", piece["length"])
                    )
                    planned_remaining = float(bin_data.get("remaining", 0))
                except (TypeError, ValueError):
                    errors.append(f"طول قطعه مصرفی پروفیل «{profile_name}» معتبر نیست.")
                    continue
                if (
                    not math.isfinite(planned_initial_length)
                    or not math.isfinite(planned_remaining)
                    or abs(planned_initial_length - float(piece["length"])) > 0.001
                    or planned_remaining > float(piece["length"])
                ):
                    errors.append(
                        f"طول قطعه {piece_id} با طرح برش هماهنگ نیست؛ "
                        "لطفاً گزارش برش را دوباره محاسبه کنید."
                    )
                    continue
                prepared_pieces.append(dict(piece))

            cursor.execute(
                "SELECT quantity FROM inventory_items WHERE profile_type_id = ? AND color_id = ?",
                (profile["id"], color["id"]),
            )
            stock_row = cursor.fetchone()
            current_stock = int(stock_row["quantity"]) if stock_row else 0
            reservations_table = cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_reservations'"
            ).fetchone()
            reserved_stock = 0
            if reservations_table:
                reserved_stock = int(
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM inventory_reservations
                        WHERE profile_type_id=? AND color_id=?
                          AND resource_type='stock' AND status='active'
                        """,
                        (profile["id"], color["id"]),
                    ).fetchone()[0]
                )
            available_stock = current_stock - reserved_stock
            if available_stock < new_bins_count:
                errors.append(
                    f"موجودی «{profile_name}» با رنگ «{color['name']}» کافی نیست؛ نیاز: {new_bins_count} شاخه، "
                    f"موجودی آزاد: {available_stock} شاخه."
                )

            try:
                min_waste = float(profile["min_waste"] if profile["min_waste"] is not None else 70)
            except (TypeError, ValueError):
                min_waste = 70.0
            if not math.isfinite(min_waste) or min_waste < 0:
                errors.append(f"حداقل ضایعات پروفیل «{profile_name}» معتبر نیست.")
                continue
            try:
                weight_per_meter = float(profile["weight_per_meter"])
            except (TypeError, ValueError):
                errors.append(f"وزن هر متر پروفیل «{profile_name}» معتبر نیست.")
                continue
            if not math.isfinite(weight_per_meter) or weight_per_meter <= 0:
                errors.append(f"وزن هر متر پروفیل «{profile_name}» معتبر نیست.")
                continue

            try:
                default_length = float(profile["default_length"])
                planned_default_length = float(profile_data.get("default_length"))
            except (TypeError, ValueError):
                errors.append(f"طول استاندارد پروفیل «{profile_name}» معتبر نیست.")
                continue
            if not math.isfinite(default_length) or default_length <= 0:
                errors.append(f"طول استاندارد پروفیل «{profile_name}» معتبر نیست.")
                continue
            if (
                not math.isfinite(planned_default_length)
                or abs(planned_default_length - default_length) > 0.001
            ):
                errors.append(
                    f"طول استاندارد پروفیل «{profile_name}» پس از محاسبه تغییر کرده است؛ "
                    "لطفاً گزارش برش را دوباره محاسبه کنید."
                )
                continue

            planned_min_waste = profile_data.get("min_waste")
            if planned_min_waste is not None:
                try:
                    planned_min_waste = float(planned_min_waste)
                except (TypeError, ValueError):
                    errors.append(f"حداقل ضایعات طرح برش پروفیل «{profile_name}» معتبر نیست.")
                    continue
                if not math.isfinite(planned_min_waste) or abs(planned_min_waste - min_waste) > 0.001:
                    errors.append(
                        f"تنظیم حداقل ضایعات پروفیل «{profile_name}» پس از محاسبه تغییر کرده است؛ "
                        "لطفاً گزارش برش را دوباره محاسبه کنید."
                    )
                    continue

            normalized_bins = []
            for bin_data in bins:
                try:
                    remaining = float(bin_data.get("remaining", 0))
                    initial_length = float(bin_data.get("initial_length", 600))
                except (TypeError, ValueError):
                    errors.append(f"مقدار باقی‌مانده پروفیل «{profile_name}» معتبر نیست.")
                    continue
                if (
                    not math.isfinite(remaining)
                    or not math.isfinite(initial_length)
                    or remaining < 0
                    or initial_length <= 0
                    or remaining > initial_length
                ):
                    errors.append(f"مقدار باقی‌مانده پروفیل «{profile_name}» معتبر نیست.")
                    continue
                if (
                    not bin_data.get("from_inventory_piece", False)
                    and abs(initial_length - default_length) > 0.001
                ):
                    errors.append(
                        f"طول شاخه جدید پروفیل «{profile_name}» با طول استاندارد انبار هماهنگ نیست."
                    )
                    continue
                normalized_bins.append(
                    {
                        "remaining": remaining,
                        "from_inventory_piece": bool(bin_data.get("from_inventory_piece", False)),
                        "source_piece_id": bin_data.get("inventory_piece_id"),
                    }
                )

            prepared_profiles.append(
                {
                    "id": profile["id"],
                    "name": profile_name,
                    "color_id": color["id"],
                    "color_name": color["name"],
                    "min_waste": min_waste,
                    "weight_per_meter": weight_per_meter,
                    "default_length": default_length,
                    "new_bins_count": new_bins_count,
                    "current_stock": current_stock,
                    "pieces": prepared_pieces,
                    "bins": normalized_bins,
                }
            )

        if errors:
            conn.rollback()
            return {"status": "validation_error", "errors": errors}

        project_name = project_info.get("customer_name") or f"پروژه {project_id}"
        project_code = project_info.get("project_code")
        project_display = f"{project_name} ({project_code})" if project_code else project_name
        timestamp = get_shamsi_datetime_iso()
        profile_results = []
        total_stock_deducted = 0
        total_pieces_consumed = 0
        total_pieces_returned = 0
        total_waste_registered = 0
        total_waste_weight = 0.0
        operation_id = _create_inventory_operation(
            cursor,
            "cutting_plan",
            description=f"اعمال طرح برش پروژه «{project_display}»",
            project_id=project_id,
            actor_user_id=actor_user_id,
        )
        operation_sequence = 0

        for prepared in prepared_profiles:
            profile_id = prepared["id"]
            profile_name = prepared["name"]
            color_id = prepared["color_id"]
            color_name = prepared["color_name"]
            new_bins_count = prepared["new_bins_count"]

            for piece in prepared["pieces"]:
                cursor.execute(
                    "DELETE FROM inventory_pieces WHERE id = ? AND profile_type_id = ? AND color_id = ?",
                    (piece["id"], profile_id, color_id),
                )
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError(f"Inventory piece {piece['id']} changed during application")
                operation_sequence += 1
                _record_inventory_operation_item(
                    cursor,
                    operation_id,
                    operation_sequence,
                    "piece_remove",
                    profile_id,
                    profile_name,
                    piece_id=piece["id"],
                    length=piece["length"],
                    color_id=color_id,
                    color_name=color_name,
                )
                cursor.execute(
                    """
                    INSERT INTO inventory_logs
                        (profile_type_id, color_id, color_name_snapshot, change_type,
                         length, piece_id, project_id, description, timestamp, operation_id)
                    VALUES (?, ?, ?, 'remove_piece', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        color_id,
                        color_name,
                        piece["length"],
                        piece["id"],
                        project_id,
                        f"استفاده شده در پروژه «{project_display}»",
                        timestamp,
                        operation_id,
                    ),
                )

            if new_bins_count:
                cursor.execute(
                    """
                    UPDATE inventory_items
                    SET quantity = quantity - ?, last_updated = CURRENT_TIMESTAMP
                    WHERE profile_type_id = ? AND color_id = ? AND quantity >= ?
                    """,
                    (new_bins_count, profile_id, color_id, new_bins_count),
                )
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError(f"Stock changed for profile {profile_id} during application")
                operation_sequence += 1
                _record_inventory_operation_item(
                    cursor,
                    operation_id,
                    operation_sequence,
                    "stock_delta",
                    profile_id,
                    profile_name,
                    quantity_delta=-new_bins_count,
                    before_quantity=prepared["current_stock"],
                    after_quantity=prepared["current_stock"] - new_bins_count,
                    color_id=color_id,
                    color_name=color_name,
                )
                cursor.execute(
                    """
                    INSERT INTO inventory_logs
                        (profile_type_id, color_id, color_name_snapshot, change_type,
                         quantity, project_id, description, timestamp, operation_id)
                    VALUES (?, ?, ?, 'remove_stock', ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        color_id,
                        color_name,
                        new_bins_count,
                        project_id,
                        f"کسر بابت پروژه: {project_display} - محاسبه برش",
                        timestamp,
                        operation_id,
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO inventory_deductions
                        (project_id, profile_type_id, color_id, color_name_snapshot, quantity_deducted)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (project_id, profile_id, color_id, color_name, new_bins_count),
                )

            returned_pieces = 0
            discarded_pieces = 0
            discarded_weight = 0.0
            for bin_data in prepared["bins"]:
                remaining = bin_data["remaining"]
                if remaining >= prepared["min_waste"] and remaining > 0:
                    cursor.execute(
                        "INSERT INTO inventory_pieces (profile_type_id, color_id, length) VALUES (?, ?, ?)",
                        (profile_id, color_id, remaining),
                    )
                    returned_piece_id = cursor.lastrowid
                    operation_sequence += 1
                    _record_inventory_operation_item(
                        cursor,
                        operation_id,
                        operation_sequence,
                        "piece_add",
                        profile_id,
                        profile_name,
                        piece_id=returned_piece_id,
                        length=remaining,
                        color_id=color_id,
                        color_name=color_name,
                    )
                    source_label = "قطعه موجود" if bin_data["from_inventory_piece"] else "شاخه جدید"
                    cursor.execute(
                        """
                        INSERT INTO inventory_logs
                            (profile_type_id, color_id, color_name_snapshot, change_type,
                             length, piece_id, project_id, description, timestamp, operation_id)
                        VALUES (?, ?, ?, 'add_piece', ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            profile_id,
                            color_id,
                            color_name,
                            remaining,
                            returned_piece_id,
                            project_id,
                            f"باقی‌مانده {source_label} از پروژه «{project_display}»",
                            timestamp,
                            operation_id,
                        ),
                    )
                    returned_pieces += 1
                elif remaining > 0:
                    waste_weight = remaining / 100.0 * prepared["weight_per_meter"]
                    cursor.execute(
                        """
                        INSERT INTO inventory_waste_items
                            (cutting_operation_id, project_id, profile_type_id, color_id,
                             profile_name_snapshot, color_name_snapshot, length_cm, weight_per_meter_snapshot,
                             calculated_weight_kg, source_type, source_piece_id, status,
                             created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?)
                        """,
                        (
                            operation_id,
                            project_id,
                            profile_id,
                            color_id,
                            profile_name,
                            color_name,
                            remaining,
                            prepared["weight_per_meter"],
                            waste_weight,
                            "inventory_piece"
                            if bin_data["from_inventory_piece"]
                            else "new_stock",
                            bin_data.get("source_piece_id"),
                            timestamp,
                            timestamp,
                        ),
                    )
                    discarded_pieces += 1
                    discarded_weight += waste_weight

            pieces_consumed = len(prepared["pieces"])
            total_stock_deducted += new_bins_count
            total_pieces_consumed += pieces_consumed
            total_pieces_returned += returned_pieces
            total_waste_registered += discarded_pieces
            total_waste_weight += discarded_weight
            profile_results.append(
                {
                    "profile_name": profile_name,
                    "color_name": color_name,
                    "stock_deducted": new_bins_count,
                    "pieces_consumed": pieces_consumed,
                    "pieces_returned": returned_pieces,
                    "pieces_discarded": discarded_pieces,
                    "waste_registered": discarded_pieces,
                    "waste_weight": discarded_weight,
                    "min_waste": prepared["min_waste"],
                }
            )

        cursor.execute(
            """
            INSERT INTO inventory_cutting_applications
                (project_id, applied_at, profile_count, total_stock_deducted,
                 pieces_consumed, pieces_returned, operation_id, plan_snapshot_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                timestamp,
                len(prepared_profiles),
                total_stock_deducted,
                total_pieces_consumed,
                total_pieces_returned,
                operation_id,
                plan_snapshot_json,
            ),
        )
        conn.commit()
        return {
            "status": "success",
            "profile_results": profile_results,
            "application": {
                "project_id": project_id,
                "applied_at": timestamp,
                "profile_count": len(prepared_profiles),
                "total_stock_deducted": total_stock_deducted,
                "pieces_consumed": total_pieces_consumed,
                "pieces_returned": total_pieces_returned,
                "operation_id": operation_id,
                "waste_registered": total_waste_registered,
                "waste_weight": total_waste_weight,
            },
        }
    except sqlite3.Error as exc:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in apply_cutting_plan_inventory_transaction: {exc}")
        traceback.print_exc()
        return {"status": "database_error", "errors": [str(exc)]}
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"!!!!!! Unexpected error in apply_cutting_plan_inventory_transaction: {exc}")
        traceback.print_exc()
        return {"status": "error", "errors": [str(exc)]}
    finally:
        if conn:
            conn.close()


def _load_inventory_operation_items(cursor, operation_id, descending=False):
    order = "DESC" if descending else "ASC"
    cursor.execute(
        f"""
        SELECT *
        FROM inventory_operation_items
        WHERE operation_id = ?
        ORDER BY sequence_no {order}, id {order}
        """,
        (operation_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def _inventory_undo_validation_errors(cursor, operation, items):
    errors = []
    for item in items:
        profile_id = item["profile_type_id"]
        color_id = item.get("color_id")
        if profile_id is None:
            errors.append(f"پروفیل «{item['profile_name']}» دیگر وجود ندارد.")
            continue

        cursor.execute("SELECT name FROM profile_types WHERE id = ?", (profile_id,))
        if not cursor.fetchone():
            errors.append(f"پروفیل «{item['profile_name']}» دیگر وجود ندارد.")
            continue

        if item["action_type"] == "stock_delta":
            cursor.execute(
                "SELECT quantity FROM inventory_items WHERE profile_type_id = ? AND color_id = ?",
                (profile_id, color_id),
            )
            stock_row = cursor.fetchone()
            current_quantity = int(stock_row["quantity"]) if stock_row else 0
            if current_quantity != item["after_quantity"]:
                errors.append(
                    f"موجودی «{item['profile_name']}» پس از این عملیات تغییر کرده است "
                    f"(مقدار مورد انتظار: {item['after_quantity']}، مقدار فعلی: {current_quantity})."
                )
        elif item["action_type"] == "piece_add":
            cursor.execute(
                "SELECT profile_type_id, color_id, length FROM inventory_pieces WHERE id = ?",
                (item["piece_id"],),
            )
            piece = cursor.fetchone()
            if (
                not piece
                or piece["profile_type_id"] != profile_id
                or piece["color_id"] != color_id
                or abs(float(piece["length"]) - float(item["length"])) > 0.001
            ):
                errors.append(
                    f"قطعه {item['piece_id']} مربوط به «{item['profile_name']}» دیگر به حالت ثبت‌شده موجود نیست."
                )
        elif item["action_type"] == "piece_remove":
            cursor.execute("SELECT 1 FROM inventory_pieces WHERE id = ?", (item["piece_id"],))
            if cursor.fetchone():
                errors.append(
                    f"شناسه قطعه {item['piece_id']} دوباره استفاده شده و بازیابی خودکار امن نیست."
                )
        else:
            errors.append(f"نوع تغییر «{item['action_type']}» قابل بازگردانی نیست.")

    if operation["operation_type"] == "cutting_plan":
        cursor.execute(
            "SELECT operation_id FROM inventory_cutting_applications WHERE project_id = ?",
            (operation["project_id"],),
        )
        application = cursor.fetchone()
        if not application or application["operation_id"] != operation["id"]:
            errors.append("سابقه تکمیل کسر پروژه با این عملیات هماهنگ نیست.")
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM inventory_waste_items
            WHERE cutting_operation_id = ? AND status != 'available'
            """,
            (operation["id"],),
        )
        changed_waste_count = cursor.fetchone()[0]
        if changed_waste_count:
            errors.append(
                f"وضعیت {changed_waste_count} ضایعات این عملیات تغییر کرده است؛ "
                "ابتدا وضعیت ضایعات را بررسی کنید."
            )

    return errors


def get_latest_reversible_inventory_operation():
    """Return the latest applied inventory operation plus an undo safety preview."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                o.*,
                u.username AS actor_username,
                p.customer_name AS project_customer,
                p.project_code AS project_code
            FROM inventory_operations o
            LEFT JOIN users u ON u.id = o.actor_user_id
            LEFT JOIN projects p ON p.id = o.project_id
            WHERE o.status = 'applied' AND o.is_reversible = 1
            ORDER BY o.id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            return None

        operation = dict(row)
        operation["items"] = _load_inventory_operation_items(cursor, operation["id"])
        operation["validation_errors"] = _inventory_undo_validation_errors(
            cursor, operation, operation["items"]
        )
        operation["can_undo"] = not operation["validation_errors"]
        return operation
    except sqlite3.Error as exc:
        print(f"!!!!!! Error in get_latest_reversible_inventory_operation: {exc}")
        traceback.print_exc()
        return None
    finally:
        if conn:
            conn.close()


def undo_latest_inventory_operation(operation_id, admin_user_id, reason):
    """Reverse the latest reversible inventory operation without deleting its audit trail."""
    reason = str(reason or "").strip()
    if len(reason) < 3:
        return {"status": "validation_error", "message": "ثبت دلیل بازگردانی الزامی است."}

    conn = None
    try:
        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM inventory_operations
            WHERE status = 'applied' AND is_reversible = 1
            ORDER BY id DESC LIMIT 1
            """
        )
        latest = cursor.fetchone()
        if not latest:
            conn.rollback()
            return {"status": "not_found", "message": "عملیات قابل‌بازگشتی وجود ندارد."}
        operation = dict(latest)
        if operation["id"] != int(operation_id):
            conn.rollback()
            return {
                "status": "not_latest",
                "message": "عملیات جدیدتری ثبت شده است؛ صفحه تاریخچه را دوباره بارگذاری کنید.",
            }

        items = _load_inventory_operation_items(cursor, operation["id"], descending=True)
        errors = _inventory_undo_validation_errors(cursor, operation, items)
        if errors:
            conn.rollback()
            return {"status": "blocked", "message": "\n".join(errors), "errors": errors}

        timestamp = get_shamsi_datetime_iso()
        reversal_operation_id = _create_inventory_operation(
            cursor,
            "undo",
            description=f"بازگردانی عملیات شماره {operation['id']}: {reason}",
            project_id=operation["project_id"],
            actor_user_id=admin_user_id,
            is_reversible=False,
            reverses_operation_id=operation["id"],
        )
        reverse_sequence = 0
        summary = []

        for item in items:
            reverse_sequence += 1
            profile_id = item["profile_type_id"]
            profile_name = item["profile_name"]
            color_id = item.get("color_id")
            color_name = item.get("color_name_snapshot") or "تعیین‌نشده"

            if item["action_type"] == "stock_delta":
                cursor.execute(
                    """
                    UPDATE inventory_items
                    SET quantity = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE profile_type_id = ? AND color_id = ? AND quantity = ?
                    """,
                    (item["before_quantity"], profile_id, color_id, item["after_quantity"]),
                )
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError("Stock changed during undo")
                reverse_delta = -int(item["quantity_delta"])
                _record_inventory_operation_item(
                    cursor,
                    reversal_operation_id,
                    reverse_sequence,
                    "stock_delta",
                    profile_id,
                    profile_name,
                    quantity_delta=reverse_delta,
                    before_quantity=item["after_quantity"],
                    after_quantity=item["before_quantity"],
                    color_id=color_id,
                    color_name=color_name,
                )
                cursor.execute(
                    """
                    INSERT INTO inventory_logs
                        (profile_type_id, color_id, color_name_snapshot, change_type,
                         quantity, project_id, description, timestamp, operation_id)
                    VALUES (?, ?, ?, 'undo_stock', ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        color_id,
                        color_name,
                        abs(reverse_delta),
                        operation["project_id"],
                        f"بازگردانی عملیات {operation['id']}: {reason}",
                        timestamp,
                        reversal_operation_id,
                    ),
                )
                direction = "افزایش" if reverse_delta > 0 else "کاهش"
                summary.append(
                    f"{profile_name} — {color_name}: {direction} {abs(reverse_delta)} شاخه"
                )

            elif item["action_type"] == "piece_add":
                cursor.execute(
                    """
                    DELETE FROM inventory_pieces
                    WHERE id = ? AND profile_type_id = ? AND color_id = ? AND ABS(length - ?) < 0.001
                    """,
                    (item["piece_id"], profile_id, color_id, item["length"]),
                )
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError("Added piece changed during undo")
                _record_inventory_operation_item(
                    cursor,
                    reversal_operation_id,
                    reverse_sequence,
                    "piece_remove",
                    profile_id,
                    profile_name,
                    piece_id=item["piece_id"],
                    length=item["length"],
                    color_id=color_id,
                    color_name=color_name,
                )
                cursor.execute(
                    """
                    INSERT INTO inventory_logs
                        (profile_type_id, color_id, color_name_snapshot, change_type,
                         length, piece_id, project_id, description, timestamp, operation_id)
                    VALUES (?, ?, ?, 'undo_add_piece', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        color_id,
                        color_name,
                        item["length"],
                        item["piece_id"],
                        operation["project_id"],
                        f"حذف قطعه حاصل از عملیات {operation['id']}: {reason}",
                        timestamp,
                        reversal_operation_id,
                    ),
                )
                summary.append(f"{profile_name} — {color_name}: حذف قطعه {item['length']:g} سانتی‌متری")

            elif item["action_type"] == "piece_remove":
                cursor.execute(
                    "INSERT INTO inventory_pieces (id, profile_type_id, color_id, length) VALUES (?, ?, ?, ?)",
                    (item["piece_id"], profile_id, color_id, item["length"]),
                )
                _record_inventory_operation_item(
                    cursor,
                    reversal_operation_id,
                    reverse_sequence,
                    "piece_add",
                    profile_id,
                    profile_name,
                    piece_id=item["piece_id"],
                    length=item["length"],
                    color_id=color_id,
                    color_name=color_name,
                )
                cursor.execute(
                    """
                    INSERT INTO inventory_logs
                        (profile_type_id, color_id, color_name_snapshot, change_type,
                         length, piece_id, project_id, description, timestamp, operation_id)
                    VALUES (?, ?, ?, 'undo_remove_piece', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile_id,
                        color_id,
                        color_name,
                        item["length"],
                        item["piece_id"],
                        operation["project_id"],
                        f"بازیابی قطعه حذف‌شده در عملیات {operation['id']}: {reason}",
                        timestamp,
                        reversal_operation_id,
                    ),
                )
                summary.append(f"{profile_name} — {color_name}: بازیابی قطعه {item['length']:g} سانتی‌متری")

        if operation["operation_type"] == "cutting_plan":
            cursor.execute(
                """
                SELECT id, status, actual_weight_kg
                FROM inventory_waste_items
                WHERE cutting_operation_id = ?
                """,
                (operation["id"],),
            )
            waste_items = cursor.fetchall()
            for waste_item in waste_items:
                cursor.execute(
                    """
                    UPDATE inventory_waste_items
                    SET status = 'reversed', updated_at = ?
                    WHERE id = ? AND status = 'available'
                    """,
                    (timestamp, waste_item["id"]),
                )
                if cursor.rowcount != 1:
                    raise sqlite3.IntegrityError("Waste item changed during undo")
                cursor.execute(
                    """
                    INSERT INTO inventory_waste_movements
                        (waste_item_id, action_type, previous_status, new_status,
                         actual_weight_kg, note, actor_user_id, created_at)
                    VALUES (?, 'undo_cutting', 'available', 'reversed', ?, ?, ?, ?)
                    """,
                    (
                        waste_item["id"],
                        waste_item["actual_weight_kg"],
                        f"بازگردانی عملیات {operation['id']}: {reason}",
                        admin_user_id,
                        timestamp,
                    ),
                )
            cursor.execute(
                "DELETE FROM inventory_cutting_applications WHERE project_id = ? AND operation_id = ?",
                (operation["project_id"], operation["id"]),
            )
            if cursor.rowcount != 1:
                raise sqlite3.IntegrityError("Cutting application changed during undo")
            cursor.execute(
                "DELETE FROM inventory_deductions WHERE project_id = ?",
                (operation["project_id"],),
            )
        elif operation["operation_type"] == "project_stock_deduction":
            affected_profiles = {
                item["profile_type_id"]
                for item in items
                if item["action_type"] == "stock_delta"
            }
            for profile_id in affected_profiles:
                cursor.execute(
                    "DELETE FROM inventory_deductions WHERE project_id = ? AND profile_type_id = ?",
                    (operation["project_id"], profile_id),
                )

        cursor.execute(
            """
            UPDATE inventory_operations
            SET status = 'reversed', reversed_at = ?, reversed_by_user_id = ?,
                reversal_reason = ?, reversal_operation_id = ?
            WHERE id = ? AND status = 'applied'
            """,
            (
                timestamp,
                admin_user_id,
                reason,
                reversal_operation_id,
                operation["id"],
            ),
        )
        if cursor.rowcount != 1:
            raise sqlite3.IntegrityError("Operation changed during undo")

        conn.commit()
        return {
            "status": "success",
            "message": "عملیات با موفقیت به حالت قبل بازگردانده شد.",
            "operation_id": operation["id"],
            "reversal_operation_id": reversal_operation_id,
            "summary": summary,
            "project_id": operation["project_id"],
        }
    except (sqlite3.Error, ValueError, TypeError) as exc:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in undo_latest_inventory_operation: {exc}")
        traceback.print_exc()
        return {
            "status": "database_error",
            "message": "بازگردانی انجام نشد و هیچ تغییری در انبار ثبت نشد.",
        }
    finally:
        if conn:
            conn.close()


WASTE_STATUSES = {
    "available",
    "sold",
    "recycled",
    "discarded",
    "consumed",
    "reversed",
}


def get_waste_warehouse_data(profile_id=None, project_id=None, status="available"):
    """Return waste warehouse totals, profile/project summaries and traceable items."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                COUNT(*) AS piece_count,
                COALESCE(SUM(length_cm), 0) AS total_length_cm,
                COALESCE(SUM(COALESCE(actual_weight_kg, calculated_weight_kg)), 0) AS total_weight_kg,
                COALESCE(SUM(calculated_weight_kg), 0) AS calculated_weight_kg,
                SUM(CASE WHEN actual_weight_kg IS NOT NULL THEN 1 ELSE 0 END) AS confirmed_count
            FROM inventory_waste_items
            WHERE status = 'available'
            """
        )
        totals = dict(cursor.fetchone())

        cursor.execute(
            """
            SELECT
                profile_type_id,
                profile_name_snapshot AS profile_name,
                color_id,
                color_name_snapshot AS color_name,
                COUNT(*) AS piece_count,
                SUM(length_cm) AS total_length_cm,
                SUM(COALESCE(actual_weight_kg, calculated_weight_kg)) AS total_weight_kg,
                COUNT(DISTINCT project_id) AS project_count
            FROM inventory_waste_items
            WHERE status = 'available'
            GROUP BY profile_type_id, profile_name_snapshot, color_id, color_name_snapshot
            ORDER BY total_weight_kg DESC, profile_name_snapshot
            """
        )
        profile_summaries = [dict(row) for row in cursor.fetchall()]

        project_params = []
        project_where = "WHERE w.status = 'available'"
        if profile_id is not None:
            project_where += " AND w.profile_type_id = ?"
            project_params.append(profile_id)
        cursor.execute(
            f"""
            SELECT
                w.project_id,
                COALESCE(p.customer_name, 'پروژه حذف‌شده') AS project_name,
                p.project_code,
                COUNT(*) AS piece_count,
                SUM(w.length_cm) AS total_length_cm,
                SUM(COALESCE(w.actual_weight_kg, w.calculated_weight_kg)) AS total_weight_kg,
                COUNT(DISTINCT w.profile_type_id) AS profile_count
            FROM inventory_waste_items w
            LEFT JOIN projects p ON p.id = w.project_id
            {project_where}
            GROUP BY w.project_id, p.customer_name, p.project_code
            ORDER BY total_weight_kg DESC, w.project_id DESC
            """,
            project_params,
        )
        project_summaries = [dict(row) for row in cursor.fetchall()]

        item_where = []
        item_params = []
        if status != "all":
            normalized_status = status if status in WASTE_STATUSES else "available"
            item_where.append("w.status = ?")
            item_params.append(normalized_status)
        if profile_id is not None:
            item_where.append("w.profile_type_id = ?")
            item_params.append(profile_id)
        if project_id is not None:
            item_where.append("w.project_id = ?")
            item_params.append(project_id)
        where_sql = "WHERE " + " AND ".join(item_where) if item_where else ""

        cursor.execute(
            f"""
            SELECT
                w.*,
                COALESCE(p.customer_name, 'پروژه حذف‌شده') AS project_name,
                p.project_code,
                COALESCE(w.actual_weight_kg, w.calculated_weight_kg) AS effective_weight_kg,
                (
                    SELECT m.action_type
                    FROM inventory_waste_movements m
                    WHERE m.waste_item_id = w.id
                    ORDER BY m.id DESC LIMIT 1
                ) AS last_action,
                (
                    SELECT m.note
                    FROM inventory_waste_movements m
                    WHERE m.waste_item_id = w.id
                    ORDER BY m.id DESC LIMIT 1
                ) AS last_note,
                (
                    SELECT m.counterparty
                    FROM inventory_waste_movements m
                    WHERE m.waste_item_id = w.id
                    ORDER BY m.id DESC LIMIT 1
                ) AS last_counterparty,
                (
                    SELECT m.total_amount
                    FROM inventory_waste_movements m
                    WHERE m.waste_item_id = w.id
                    ORDER BY m.id DESC LIMIT 1
                ) AS last_total_amount
            FROM inventory_waste_items w
            LEFT JOIN projects p ON p.id = w.project_id
            {where_sql}
            ORDER BY w.id DESC
            LIMIT 300
            """,
            item_params,
        )
        items = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT COALESCE(SUM(total_amount), 0)
            FROM inventory_waste_movements
            WHERE action_type = 'sold'
            """
        )
        sold_total_amount = cursor.fetchone()[0]

        cursor.execute("SELECT id, name FROM profile_types ORDER BY name")
        profiles = [dict(row) for row in cursor.fetchall()]
        cursor.execute("SELECT id, customer_name, project_code FROM projects ORDER BY id DESC")
        projects = [dict(row) for row in cursor.fetchall()]

        return {
            "totals": totals,
            "profile_summaries": profile_summaries,
            "project_summaries": project_summaries,
            "items": items,
            "profiles": profiles,
            "projects": projects,
            "sold_total_amount": sold_total_amount,
        }
    except sqlite3.Error as exc:
        print(f"!!!!!! Error in get_waste_warehouse_data: {exc}")
        traceback.print_exc()
        return {
            "totals": {},
            "profile_summaries": [],
            "project_summaries": [],
            "items": [],
            "profiles": [],
            "projects": [],
            "sold_total_amount": 0,
        }
    finally:
        if conn:
            conn.close()


def update_waste_item(item_id, action_type, actor_user_id, actual_weight=None,
                      price_per_kg=None, counterparty="", note=""):
    """Confirm or move one waste item while preserving an append-only movement trail."""
    action_to_status = {
        "confirm": None,
        "sold": "sold",
        "recycled": "recycled",
        "discarded": "discarded",
        "consumed": "consumed",
        "return_available": "available",
    }
    if action_type not in action_to_status:
        return {"status": "validation_error", "message": "نوع عملیات ضایعات معتبر نیست."}

    def optional_nonnegative(value, field_label):
        if value in (None, ""):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_label} معتبر نیست.") from exc
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"{field_label} معتبر نیست.")
        return number

    conn = None
    try:
        actual_weight_value = optional_nonnegative(actual_weight, "وزن واقعی")
        price_value = optional_nonnegative(price_per_kg, "قیمت هر کیلو")
        if action_type == "confirm" and (actual_weight_value is None or actual_weight_value <= 0):
            return {"status": "validation_error", "message": "برای تأیید، وزن واقعی باید بزرگ‌تر از صفر باشد."}

        conn = get_db_connection()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory_waste_items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return {"status": "not_found", "message": "رکورد ضایعات یافت نشد."}
        item = dict(row)
        if item["status"] == "reversed":
            conn.rollback()
            return {"status": "blocked", "message": "ضایعات مربوط به عملیات بازگردانی‌شده قابل تغییر نیست."}

        if action_type == "return_available":
            if item["status"] == "available":
                conn.rollback()
                return {"status": "validation_error", "message": "این ضایعات هم‌اکنون در انبار موجود است."}
        elif action_type != "confirm" and item["status"] != "available":
            conn.rollback()
            return {"status": "blocked", "message": "این ضایعات قبلاً از موجودی خارج شده است."}
        elif action_type == "confirm" and item["status"] != "available":
            conn.rollback()
            return {"status": "blocked", "message": "فقط ضایعات موجود قابل تأیید وزن است."}

        new_status = action_to_status[action_type] or item["status"]
        effective_actual_weight = (
            actual_weight_value
            if actual_weight_value is not None
            else item["actual_weight_kg"]
        )
        effective_weight = (
            effective_actual_weight
            if effective_actual_weight is not None
            else item["calculated_weight_kg"]
        )
        total_amount = effective_weight * price_value if action_type == "sold" and price_value is not None else None
        timestamp = get_shamsi_datetime_iso()

        cursor.execute(
            """
            UPDATE inventory_waste_items
            SET status = ?, actual_weight_kg = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (new_status, effective_actual_weight, timestamp, item_id, item["status"]),
        )
        if cursor.rowcount != 1:
            raise sqlite3.IntegrityError("Waste item changed during update")
        cursor.execute(
            """
            INSERT INTO inventory_waste_movements
                (waste_item_id, action_type, previous_status, new_status,
                 actual_weight_kg, price_per_kg, total_amount, counterparty,
                 note, actor_user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                action_type,
                item["status"],
                new_status,
                effective_actual_weight,
                price_value,
                total_amount,
                str(counterparty or "").strip(),
                str(note or "").strip(),
                actor_user_id,
                timestamp,
            ),
        )
        conn.commit()
        return {"status": "success", "message": "وضعیت ضایعات با موفقیت ثبت شد."}
    except ValueError as exc:
        if conn:
            conn.rollback()
        return {"status": "validation_error", "message": str(exc)}
    except sqlite3.Error as exc:
        if conn:
            conn.rollback()
        print(f"!!!!!! Error in update_waste_item: {exc}")
        traceback.print_exc()
        return {"status": "database_error", "message": "تغییر وضعیت ضایعات ثبت نشد."}
    finally:
        if conn:
            conn.close()


def get_inventory_logs(limit=100, profile_id=None):
    """دریافت تاریخچه انبار"""
    conn = None
    logs = []
    try:
        conn = get_db_connection()
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
        "logs": [],
        "stock_by_color": [],
        "colors": [],
    }
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # موجودی کامل
        has_reservations = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_reservations'"
        ).fetchone()
        if has_reservations:
            cursor.execute(
                """
                SELECT pc.id AS color_id,pc.name AS color_name,pc.hex_code,
                       COALESCE(ii.quantity,0) AS quantity,
                       (
                           SELECT COUNT(*) FROM inventory_reservations r
                           WHERE r.profile_type_id=? AND r.color_id=pc.id
                             AND r.resource_type='stock' AND r.status='active'
                       ) AS reserved_quantity,
                       MAX(0,COALESCE(ii.quantity,0)-(
                           SELECT COUNT(*) FROM inventory_reservations r
                           WHERE r.profile_type_id=? AND r.color_id=pc.id
                             AND r.resource_type='stock' AND r.status='active'
                       )) AS available_quantity
                FROM profile_colors pc
                LEFT JOIN inventory_items ii
                  ON ii.color_id=pc.id AND ii.profile_type_id=?
                WHERE pc.is_active=1
                ORDER BY CASE WHEN pc.name='تعیین‌نشده' THEN 1 ELSE 0 END,pc.name
                """,
                (profile_id, profile_id, profile_id),
            )
        else:
            cursor.execute(
                """
                SELECT pc.id AS color_id,pc.name AS color_name,pc.hex_code,
                       COALESCE(ii.quantity,0) AS quantity,0 AS reserved_quantity,
                       COALESCE(ii.quantity,0) AS available_quantity
                FROM profile_colors pc
                LEFT JOIN inventory_items ii
                  ON ii.color_id=pc.id AND ii.profile_type_id=?
                WHERE pc.is_active=1
                ORDER BY CASE WHEN pc.name='تعیین‌نشده' THEN 1 ELSE 0 END,pc.name
                """,
                (profile_id,),
            )
        details["stock_by_color"] = [dict(row) for row in cursor.fetchall()]
        details["colors"] = [dict(row) for row in details["stock_by_color"]]
        details["complete_pieces"] = sum(
            row["available_quantity"] for row in details["stock_by_color"]
        )

        # تکه‌ها
        if has_reservations:
            cursor.execute(
                """
                SELECT ip.*,pc.name AS color_name,pc.hex_code,
                       EXISTS(
                           SELECT 1 FROM inventory_reservations r
                           WHERE r.inventory_piece_id=ip.id
                             AND r.resource_type='piece' AND r.status='active'
                       ) AS is_reserved
                FROM inventory_pieces ip
                JOIN profile_colors pc ON pc.id=ip.color_id
                WHERE ip.profile_type_id=? ORDER BY ip.length DESC
                """,
                (profile_id,),
            )
        else:
            cursor.execute(
                """
                SELECT ip.*,pc.name AS color_name,pc.hex_code,0 AS is_reserved
                FROM inventory_pieces ip
                JOIN profile_colors pc ON pc.id=ip.color_id
                WHERE ip.profile_type_id=? ORDER BY ip.length DESC
                """,
                (profile_id,),
            )
        details["pieces"] = [dict(row) for row in cursor.fetchall()]

        # آخرین لاگ‌ها
        details["logs"] = get_inventory_logs(limit=10, profile_id=profile_id)

    except sqlite3.Error as e:
        print(f"!!!!!! Error in get_profile_stock_details: {e}")
    finally:
        if conn:
            conn.close()
    return details

def get_available_inventory_pieces(profile_name, color_name=None):
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
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        normalized_name = normalize_profile_name(profile_name)
        cursor.execute("SELECT id, name FROM profile_types")
        matches = [
            row for row in cursor.fetchall()
            if normalize_profile_name(row["name"]) == normalized_name
        ]

        if len(matches) != 1:
            # پروفیل یافت نشد
            return pieces

        profile_id = matches[0]['id']

        # دریافت قطعات برش‌خورده مرتب‌شده به صورت نزولی
        color = _get_color_for_operation(cursor, color_name=color_name)
        reservations_table = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_reservations'"
        ).fetchone()
        if reservations_table:
            cursor.execute(
                """
                SELECT ip.id,ip.length,ip.color_id FROM inventory_pieces ip
                WHERE ip.profile_type_id=? AND ip.color_id=?
                  AND NOT EXISTS (
                    SELECT 1 FROM inventory_reservations r
                    WHERE r.resource_type='piece' AND r.inventory_piece_id=ip.id
                      AND r.status='active'
                  )
                ORDER BY ip.length DESC
                """,
                (profile_id, color["id"]),
            )
        else:
            cursor.execute(
                """
                SELECT id, length, color_id FROM inventory_pieces
                WHERE profile_type_id = ? AND color_id = ? ORDER BY length DESC
                """,
                (profile_id, color["id"]),
            )
        pieces = [dict(row) for row in cursor.fetchall()]

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
        conn = get_db_connection()
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
                d.color_id,
                d.color_name_snapshot AS color_name,
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
