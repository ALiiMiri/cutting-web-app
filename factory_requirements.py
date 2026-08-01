"""Factory-facing rubber and installation-bracket calculations."""

from collections import defaultdict
from math import ceil

from cutting_calculator import TWO_SIDED_FRAME, normalize_frame_type
from profile_names import normalize_profile_name


BRACKET_MODES = {"profile", "meaty"}
MEATY_BRACKET_LABEL = "براکت گوشتی"


class FactoryRequirementError(ValueError):
    """Raised when a factory-installation choice is invalid."""


def normalize_bracket_mode(value):
    mode = str(value or "profile").strip()
    if mode not in BRACKET_MODES:
        raise FactoryRequirementError("نوع براکت نصب معتبر نیست.")
    return mode


def default_profile_bracket_label(profile_name):
    """Create a useful default label while allowing an explicit settings override."""
    profile = normalize_profile_name(profile_name)
    compact = (
        profile.replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace("‌", "")
    )
    if "توچوب" in compact:
        return "براکت نصب پروفیل توچوب‌دار"
    if "فریملس" in compact and ("جدید" in compact or "قالبجدید" in compact):
        return "براکت نصب پروفیل جدید فریم‌لس"
    if "فریملس" in compact:
        return "براکت نصب پروفیل فریم‌لس"
    if compact.startswith("پروفیل"):
        return f"براکت نصب {profile}"
    return f"براکت نصب پروفیل {profile}" if profile else ""


def bracket_count_for_height(height_cm):
    """One bracket per 60 cm on each of the two installation sides."""
    height = float(height_cm)
    return ceil(height / 60.0) * 2 if height > 0 else 0


def rubber_meters_per_door(width_cm, height_cm, frame_type):
    """Round packing length up to full meters, matching the established pricing rule."""
    width = float(width_cm)
    height = float(height_cm)
    if width <= 0 or height <= 0:
        return 0
    top_length = 0 if normalize_frame_type(frame_type) == TWO_SIDED_FRAME else width
    return ceil((top_length + (2 * height)) / 100.0)


def calculate_factory_requirements(doors, profile_bracket_labels=None):
    """Return separate factory totals and per-door details for rubber and brackets."""
    labels = {
        normalize_profile_name(name): str(label or "").strip()
        for name, label in (profile_bracket_labels or {}).items()
    }
    bracket_totals = defaultdict(int)
    details = []
    warnings = []
    total_rubber_meters = 0
    total_bracket_count = 0
    included_door_count = 0
    excluded_row_count = 0

    for row_number, door in enumerate(doors, start=1):
        if "".join(str(door.get("vaziat") or "").split()) == "بدوندرب":
            excluded_row_count += 1
            continue
        door_id = door.get("id")
        location = " ".join(str(door.get("location") or "").split()) or f"ردیف {row_number}"
        try:
            width = float(door.get("width"))
            height = float(door.get("height"))
            quantity = int(door.get("quantity"))
            if width <= 0 or height <= 0 or quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            warnings.append(
                {
                    "door_id": door_id,
                    "location": location,
                    "message": "عرض، ارتفاع یا تعداد معتبر نیست؛ اقلام کارخانه محاسبه نشد.",
                }
            )
            continue

        profile_name = normalize_profile_name(door.get("noe_profile"))
        mode = normalize_bracket_mode(door.get("installation_bracket_mode"))
        if mode == "meaty":
            bracket_label = MEATY_BRACKET_LABEL
        elif profile_name:
            bracket_label = labels.get(profile_name) or default_profile_bracket_label(profile_name)
        else:
            bracket_label = ""
            warnings.append(
                {
                    "door_id": door_id,
                    "location": location,
                    "message": "نوع پروفیل مشخص نشده و نوع براکت خودکار قابل تعیین نیست.",
                }
            )

        rubber_meters = rubber_meters_per_door(
            width, height, door.get("kolaft")
        ) * quantity
        bracket_count = bracket_count_for_height(height) * quantity
        included_door_count += quantity
        total_rubber_meters += rubber_meters
        if bracket_label:
            bracket_totals[bracket_label] += bracket_count
            total_bracket_count += bracket_count
        details.append(
            {
                "door_id": door_id,
                "location": location,
                "width": width,
                "height": height,
                "quantity": quantity,
                "frame_type": normalize_frame_type(door.get("kolaft")),
                "profile_name": profile_name or "نامشخص",
                "bracket_mode": mode,
                "bracket_label": bracket_label or "نیازمند تعیین نوع پروفیل",
                "bracket_count": bracket_count if bracket_label else 0,
                "rubber_meters": rubber_meters,
                "has_warning": any(item["door_id"] == door_id for item in warnings),
            }
        )

    bracket_summary = [
        {"label": label, "quantity": quantity}
        for label, quantity in sorted(bracket_totals.items())
    ]
    return {
        "bracket_summary": bracket_summary,
        "details": details,
        "warnings": warnings,
        "included_door_count": included_door_count,
        "excluded_row_count": excluded_row_count,
        "total_rubber_meters": total_rubber_meters,
        "total_bracket_count": total_bracket_count,
    }
