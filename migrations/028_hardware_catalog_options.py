"""Create user-managed dropdown catalogs for structured hardware fields."""


CATEGORIES = (
    "hinge_brand",
    "hinge_color",
    "handle_brand",
    "handle_model",
    "handle_color",
    "lock_brand",
    "lock_model",
    "cylinder_brand",
    "cylinder_model",
)


def apply(conn):
    cursor = conn.cursor()
    category_sql = ",".join(f"'{category}'" for category in CATEGORIES)
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS hardware_catalog_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL CHECK(category IN ({category_sql})),
            value TEXT NOT NULL CHECK(length(trim(value)) BETWEEN 1 AND 120),
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category, value)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hardware_catalog_active_order
        ON hardware_catalog_options(category, is_active, sort_order, id)
        """
    )

    # Existing structured values become available choices automatically. This
    # preserves real business data without inventing brands or models.
    for category in CATEGORIES:
        cursor.execute(
            f"""
            INSERT OR IGNORE INTO hardware_catalog_options(category,value,sort_order)
            SELECT ?, TRIM({category}), 0
            FROM door_hardware
            WHERE {category} IS NOT NULL AND TRIM({category}) != ''
            GROUP BY TRIM({category})
            """,
            (category,),
        )
