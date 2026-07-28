from profile_names import normalize_profile_name


def apply(conn):
    """Trim and normalize profile names without merging distinct inventory records."""
    cursor = conn.cursor()

    profiles = cursor.execute("SELECT id, name FROM profile_types ORDER BY id").fetchall()
    normalized_to_id = {}
    normalized_profiles = []
    for profile_id, raw_name in profiles:
        normalized_name = normalize_profile_name(raw_name)
        if not normalized_name:
            raise ValueError(f"Profile {profile_id} has an empty name")
        if normalized_name in normalized_to_id and normalized_to_id[normalized_name] != profile_id:
            raise ValueError(
                f"Profiles {normalized_to_id[normalized_name]} and {profile_id} normalize to the same name"
            )
        normalized_to_id[normalized_name] = profile_id
        normalized_profiles.append((normalized_name, profile_id))

    for normalized_name, profile_id in normalized_profiles:
        cursor.execute(
            "UPDATE profile_types SET name = ? WHERE id = ?",
            (normalized_name, profile_id),
        )
    column_row = cursor.execute(
        "SELECT id FROM custom_columns WHERE column_name = 'noe_profile'"
    ).fetchone()
    if not column_row:
        return

    column_id = column_row[0]
    options = cursor.execute(
        "SELECT id, option_value FROM custom_column_options WHERE column_id = ? ORDER BY id",
        (column_id,),
    ).fetchall()
    kept_options = {}
    for option_id, raw_value in options:
        normalized_value = normalize_profile_name(raw_value)
        if not normalized_value:
            cursor.execute("DELETE FROM custom_column_options WHERE id = ?", (option_id,))
        elif normalized_value in kept_options:
            cursor.execute("DELETE FROM custom_column_options WHERE id = ?", (option_id,))
        else:
            kept_options[normalized_value] = option_id
            cursor.execute(
                "UPDATE custom_column_options SET option_value = ? WHERE id = ?",
                (normalized_value, option_id),
            )

    door_values = cursor.execute(
        "SELECT door_id, value FROM door_custom_values WHERE column_id = ?",
        (column_id,),
    ).fetchall()
    for door_id, raw_value in door_values:
        cursor.execute(
            "UPDATE door_custom_values SET value = ? WHERE door_id = ? AND column_id = ?",
            (normalize_profile_name(raw_value), door_id, column_id),
        )
