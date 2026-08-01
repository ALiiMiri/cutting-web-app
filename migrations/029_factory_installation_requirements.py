"""Add per-door bracket mode and per-profile factory bracket labels."""


def _columns(cursor, table_name):
    return {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})")}


def apply(conn):
    cursor = conn.cursor()
    if "installation_bracket_mode" not in _columns(cursor, "doors"):
        cursor.execute(
            """
            ALTER TABLE doors ADD COLUMN installation_bracket_mode TEXT NOT NULL
            DEFAULT 'profile'
            CHECK(installation_bracket_mode IN ('profile','meaty'))
            """
        )
    if "installation_bracket_name" not in _columns(cursor, "profile_types"):
        cursor.execute(
            """
            ALTER TABLE profile_types ADD COLUMN installation_bracket_name TEXT
            CHECK(
                installation_bracket_name IS NULL OR
                length(trim(installation_bracket_name)) BETWEEN 1 AND 160
            )
            """
        )
