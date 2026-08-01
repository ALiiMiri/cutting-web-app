"""Project hardware-list calculations shared by the preview and Excel export."""

from collections import defaultdict
from math import ceil


GROUP_ORDER = {"لولا": 1, "قفل": 2, "دستگیره": 3, "سیلندر": 4}


def _clean(value):
    return " ".join(str(value or "").replace("\u200c", " ").split())


def _compact(value):
    return _clean(value).replace(" ", "").replace("-", "")


def _is_without(value, item_name):
    compact = _compact(value)
    return compact in {
        "ندارد",
        "بدون",
        f"بدون{_compact(item_name)}",
        f"فاقد{_compact(item_name)}",
    }


def hinge_count_for_height(height_cm):
    """Use the established price-calculator hinge thresholds."""
    height = float(height_cm)
    if height <= 0:
        return 0
    if height <= 180:
        return 2
    if height <= 240:
        return 3
    if height <= 270:
        return 4
    if height <= 320:
        return 5
    return 6


def bracket_count_for_height(height_cm):
    """One bracket per 60 cm on each of the two installation sides."""
    height = float(height_cm)
    return ceil(height / 60.0) * 2 if height > 0 else 0


def handle_requires_cylinder(handle_model):
    """Return false for handle families that do not use a cylinder."""
    compact = _compact(handle_model)
    no_cylinder_markers = (
        "مونتیس",
        "مورتایس",
        "تکروزه",
        "تکروزت",
        "تکرزه",
        "تکرزت",
    )
    return not any(marker in compact for marker in no_cylinder_markers)


def calculate_project_hardware(doors):
    """Build project summary, per-door details and data-completeness warnings."""
    totals = defaultdict(int)
    details = []
    warnings = []
    included_door_count = 0
    excluded_row_count = 0

    def add_total(group, model, count):
        if count > 0:
            totals[(group, model, "عدد")] += int(count)

    for row_number, door in enumerate(doors, start=1):
        status = _clean(door.get("vaziat"))
        if _compact(status) == "بدوندرب":
            excluded_row_count += 1
            continue

        location = _clean(door.get("location")) or f"ردیف {row_number}"
        door_id = door.get("id")
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
                    "field": "ابعاد یا تعداد",
                    "message": "عرض، ارتفاع یا تعداد این درب معتبر نیست و در گزارش محاسبه نشد.",
                }
            )
            continue

        included_door_count += quantity

        if door.get("hardware_configured"):
            hinge_brand = _clean(door.get("hinge_brand"))
            hinge_color = _clean(door.get("hinge_color"))
            hinge_model = " — ".join(
                item for item in (hinge_brand, hinge_color) if item
            ) or "نامشخص"
            try:
                hinge_per_door = int(door.get("hinge_count"))
                if hinge_per_door <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                hinge_per_door = 0
                warnings.append(
                    {
                        "door_id": door_id,
                        "location": location,
                        "field": "لولا",
                        "message": "تعداد لولای ثبت‌شده معتبر نیست.",
                    }
                )
            hinge_count = hinge_per_door * quantity
            if not hinge_brand or not hinge_color:
                warnings.append(
                    {
                        "door_id": door_id,
                        "location": location,
                        "field": "لولا",
                        "message": "برند یا رنگ لولا کامل نیست.",
                    }
                )
            add_total("لولا", hinge_model, hinge_count)

            handle_count = 0
            lock_count = 0
            cylinder_count = 0
            lock_model = "بدون قفل"
            handle_model = "بدون دستگیره"
            has_handle = bool(door.get("has_handle"))
            if has_handle:
                handle_type = door.get("handle_type")
                handle_type_label = (
                    "دوتکه" if handle_type == "two_piece" else "تک‌رزت"
                )
                handle_parts = [
                    handle_type_label,
                    _clean(door.get("handle_brand")),
                    _clean(door.get("handle_model")),
                    _clean(door.get("handle_color")),
                ]
                handle_model = " — ".join(item for item in handle_parts if item)
                handle_count = quantity
                add_total("دستگیره", handle_model, handle_count)

                if door.get("lock_source") == "own_brand":
                    lock_model = (
                        f"قفل مخصوص {_clean(door.get('handle_brand')) or 'تک‌رزت'}"
                    )
                else:
                    lock_model = " — ".join(
                        item
                        for item in (
                            _clean(door.get("lock_brand")),
                            _clean(door.get("lock_model")),
                        )
                        if item
                    ) or "نامشخص"
                lock_count = quantity
                add_total("قفل", lock_model, lock_count)

                if handle_type == "two_piece":
                    cylinder_model = " — ".join(
                        item
                        for item in (
                            _clean(door.get("cylinder_brand")),
                            _clean(door.get("cylinder_model")),
                        )
                        if item
                    ) or "نامشخص"
                    cylinder_count = quantity
                    add_total("سیلندر", cylinder_model, cylinder_count)

            details.append(
                {
                    "door_id": door_id,
                    "location": location,
                    "width": width,
                    "height": height,
                    "quantity": quantity,
                    "hinge_model": hinge_model,
                    "hinge_count": hinge_count,
                    "lock_model": lock_model,
                    "lock_count": lock_count,
                    "handle_model": handle_model,
                    "handle_count": handle_count,
                    "cylinder_count": cylinder_count,
                    "has_warning": any(
                        item["door_id"] == door_id for item in warnings
                    ),
                }
            )
            continue

        hinge_model = _clean(door.get("lola"))
        lock_model = _clean(door.get("ghofl"))
        handle_model = _clean(door.get("dastgire"))

        hinge_count = 0
        if not hinge_model:
            warnings.append(
                {"door_id": door_id, "location": location, "field": "لولا", "message": "مدل لولا مشخص نشده است."}
            )
        elif not _is_without(hinge_model, "لولا"):
            hinge_count = hinge_count_for_height(height) * quantity
            add_total("لولا", hinge_model, hinge_count)

        lock_count = 0
        lock_selected = bool(lock_model and not _is_without(lock_model, "قفل"))
        if not lock_model:
            warnings.append(
                {"door_id": door_id, "location": location, "field": "قفل", "message": "مدل قفل مشخص نشده است."}
            )
        elif lock_selected:
            lock_count = quantity
            add_total("قفل", lock_model, lock_count)

        handle_count = 0
        handle_selected = bool(handle_model and not _is_without(handle_model, "دستگیره"))
        if not handle_model:
            warnings.append(
                {"door_id": door_id, "location": location, "field": "دستگیره", "message": "مدل دستگیره مشخص نشده است."}
            )
        elif handle_selected:
            handle_count = quantity
            add_total("دستگیره", handle_model, handle_count)

        cylinder_count = 0
        if lock_selected:
            if not handle_model:
                warnings.append(
                    {
                        "door_id": door_id,
                        "location": location,
                        "field": "سیلندر",
                        "message": "به‌دلیل نامشخص بودن دستگیره، تعداد سیلندر قابل تعیین نیست.",
                    }
                )
            elif not handle_selected or handle_requires_cylinder(handle_model):
                cylinder_count = quantity
                add_total("سیلندر", "سیلندر استاندارد", cylinder_count)

        details.append(
            {
                "door_id": door_id,
                "location": location,
                "width": width,
                "height": height,
                "quantity": quantity,
                "hinge_model": hinge_model or "نامشخص",
                "hinge_count": hinge_count,
                "lock_model": lock_model or "نامشخص",
                "lock_count": lock_count,
                "handle_model": handle_model or "نامشخص",
                "handle_count": handle_count,
                "cylinder_count": cylinder_count,
                "has_warning": any(item["door_id"] == door_id for item in warnings),
            }
        )

    summary = [
        {"group": group, "model": model, "quantity": quantity, "unit": unit}
        for (group, model, unit), quantity in totals.items()
    ]
    summary.sort(key=lambda item: (GROUP_ORDER.get(item["group"], 99), item["model"]))

    return {
        "summary": summary,
        "details": details,
        "warnings": warnings,
        "included_door_count": included_door_count,
        "excluded_row_count": excluded_row_count,
        "total_item_count": sum(item["quantity"] for item in summary),
    }
