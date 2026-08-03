"""Group technically identical doors under a code with installation locations."""

import re


def _next_available_code(used, number):
    while True:
        candidate = f"D-{number:02d}"
        number += 1
        if candidate.casefold() not in used:
            used.add(candidate.casefold())
            return candidate, number


def apply(conn):
    cursor = conn.cursor()
    door_columns = {row[1] for row in cursor.execute("PRAGMA table_info(doors)")}
    if "door_code" not in door_columns:
        cursor.execute("ALTER TABLE doors ADD COLUMN door_code TEXT")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS door_installation_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            door_id INTEGER NOT NULL,
            location TEXT NOT NULL CHECK(length(trim(location)) > 0),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (door_id) REFERENCES doors(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_door_installation_locations_door "
        "ON door_installation_locations(door_id, sort_order, id)"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_doors_project_door_code "
        "ON doors(project_id, door_code COLLATE NOCASE) WHERE door_code IS NOT NULL"
    )

    project_ids = [
        row[0]
        for row in cursor.execute(
            "SELECT DISTINCT project_id FROM doors WHERE project_id IS NOT NULL"
        )
    ]
    for project_id in project_ids:
        rows = cursor.execute(
            "SELECT id,door_code,location,quantity FROM doors WHERE project_id=? ORDER BY id",
            (project_id,),
        ).fetchall()
        used = {
            str(row[1]).strip().casefold()
            for row in rows
            if row[1] and str(row[1]).strip()
        }
        next_number = 1
        for door_id, door_code, location, quantity in rows:
            clean_code = " ".join(str(door_code or "").split())
            if not clean_code:
                clean_code, next_number = _next_available_code(used, next_number)
                cursor.execute(
                    "UPDATE doors SET door_code=? WHERE id=?", (clean_code, door_id)
                )
            else:
                match = re.fullmatch(r"D-(\d+)", clean_code, re.IGNORECASE)
                if match:
                    next_number = max(next_number, int(match.group(1)) + 1)

            exists = cursor.execute(
                "SELECT 1 FROM door_installation_locations WHERE door_id=? LIMIT 1",
                (door_id,),
            ).fetchone()
            if not exists:
                clean_location = " ".join(str(location or "").split()) or "مکان ثبت‌نشده"
                clean_quantity = int(quantity or 1)
                if clean_quantity <= 0:
                    clean_quantity = 1
                cursor.execute(
                    """
                    INSERT INTO door_installation_locations(door_id,location,quantity,sort_order)
                    VALUES(?,?,?,0)
                    """,
                    (door_id, clean_location, clean_quantity),
                )
