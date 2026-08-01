"""Store validated hardware choices for each door."""


def apply(conn):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS door_hardware (
            door_id INTEGER PRIMARY KEY,
            hinge_brand TEXT NOT NULL CHECK(length(trim(hinge_brand)) > 0),
            hinge_color TEXT NOT NULL CHECK(length(trim(hinge_color)) > 0),
            hinge_count INTEGER NOT NULL CHECK(hinge_count BETWEEN 1 AND 20),
            has_handle INTEGER NOT NULL CHECK(has_handle IN (0, 1)),
            handle_type TEXT CHECK(handle_type IN ('two_piece', 'single_rosette')),
            handle_brand TEXT,
            handle_model TEXT,
            handle_color TEXT,
            lock_source TEXT CHECK(lock_source IN ('separate', 'own_brand')),
            lock_brand TEXT,
            lock_model TEXT,
            cylinder_brand TEXT,
            cylinder_model TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(door_id) REFERENCES doors(id) ON DELETE CASCADE,
            CHECK(
                (has_handle = 0
                    AND handle_type IS NULL
                    AND handle_brand IS NULL
                    AND handle_model IS NULL
                    AND handle_color IS NULL
                    AND lock_source IS NULL
                    AND lock_brand IS NULL
                    AND lock_model IS NULL
                    AND cylinder_brand IS NULL
                    AND cylinder_model IS NULL)
                OR
                (has_handle = 1
                    AND handle_type = 'two_piece'
                    AND length(trim(COALESCE(handle_brand, ''))) > 0
                    AND length(trim(COALESCE(handle_model, ''))) > 0
                    AND length(trim(COALESCE(handle_color, ''))) > 0
                    AND lock_source = 'separate'
                    AND length(trim(COALESCE(lock_brand, ''))) > 0
                    AND length(trim(COALESCE(lock_model, ''))) > 0
                    AND length(trim(COALESCE(cylinder_brand, ''))) > 0
                    AND length(trim(COALESCE(cylinder_model, ''))) > 0)
                OR
                (has_handle = 1
                    AND handle_type = 'single_rosette'
                    AND length(trim(COALESCE(handle_brand, ''))) > 0
                    AND length(trim(COALESCE(handle_model, ''))) > 0
                    AND length(trim(COALESCE(handle_color, ''))) > 0
                    AND lock_source = 'own_brand'
                    AND lock_brand IS NULL
                    AND lock_model IS NULL
                    AND cylinder_brand IS NULL
                    AND cylinder_model IS NULL)
                OR
                (has_handle = 1
                    AND handle_type = 'single_rosette'
                    AND length(trim(COALESCE(handle_brand, ''))) > 0
                    AND length(trim(COALESCE(handle_model, ''))) > 0
                    AND length(trim(COALESCE(handle_color, ''))) > 0
                    AND lock_source = 'separate'
                    AND length(trim(COALESCE(lock_brand, ''))) > 0
                    AND length(trim(COALESCE(lock_model, ''))) > 0
                    AND cylinder_brand IS NULL
                    AND cylinder_model IS NULL)
            )
        )
        """
    )
