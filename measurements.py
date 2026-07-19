CENTIMETER = "cm"
MILLIMETER = "mm"
SUPPORTED_MEASUREMENT_UNITS = {CENTIMETER, MILLIMETER}


def normalize_measurement_unit(value):
    """Validate a user-selected dimension unit; old forms default to cm."""
    unit = str(value or CENTIMETER).strip().lower()
    if unit not in SUPPORTED_MEASUREMENT_UNITS:
        raise ValueError("واحد اندازه‌گیری باید سانتی‌متر یا میلی‌متر باشد")
    return unit


def dimension_to_centimeters(value, unit=CENTIMETER):
    """Convert a numeric form value to the application's canonical cm unit."""
    number = float(value)
    normalized_unit = normalize_measurement_unit(unit)
    return number / 10.0 if normalized_unit == MILLIMETER else number


def centimeters_to_measurement_unit(value, unit=CENTIMETER):
    """Convert a canonical database length to a project's display/export unit."""
    number = float(value)
    normalized_unit = normalize_measurement_unit(unit)
    return number * 10.0 if normalized_unit == MILLIMETER else number


def format_measurement_value(value):
    """Show whole measurements without a redundant trailing decimal."""
    return f"{float(value):g}"


def measurement_unit_labels(unit=CENTIMETER):
    normalized_unit = normalize_measurement_unit(unit)
    if normalized_unit == MILLIMETER:
        return {"short": "mm", "fa": "میلی‌متر"}
    return {"short": "cm", "fa": "سانتی‌متر"}
