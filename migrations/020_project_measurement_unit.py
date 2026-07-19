def apply(conn):
    """Store the input/drawing unit once per project; existing projects use cm."""
    cursor = conn.cursor()
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(projects)")}
    if "measurement_unit" not in columns:
        cursor.execute(
            """
            ALTER TABLE projects ADD COLUMN measurement_unit TEXT NOT NULL
            DEFAULT 'cm' CHECK (measurement_unit IN ('cm', 'mm'))
            """
        )
    cursor.execute(
        """
        UPDATE projects SET measurement_unit='cm'
        WHERE measurement_unit IS NULL OR measurement_unit NOT IN ('cm','mm')
        """
    )
