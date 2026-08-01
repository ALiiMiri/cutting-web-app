"""Validation and presentation helpers for structured door hardware."""


class HardwareValidationError(ValueError):
    """Raised when a hardware payload violates the ordering rules."""


HANDLE_TYPES = {"two_piece", "single_rosette"}
LOCK_SOURCES = {"separate", "own_brand"}
MAX_TEXT_LENGTH = 120

HARDWARE_CATALOG_CATEGORIES = {
    "hinge_brand": "برند لولا",
    "hinge_color": "رنگ لولا",
    "handle_brand": "برند دستگیره",
    "handle_model": "مدل دستگیره",
    "handle_color": "رنگ دستگیره",
    "lock_brand": "برند قفل",
    "lock_model": "مدل قفل",
    "cylinder_brand": "برند سیلندر",
    "cylinder_model": "مدل سیلندر",
}


def _clean_text(value, label, *, required=False):
    cleaned = " ".join(str(value or "").split())
    if required and not cleaned:
        raise HardwareValidationError(f"{label} را وارد کنید.")
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise HardwareValidationError(
            f"{label} نباید بیشتر از {MAX_TEXT_LENGTH} نویسه باشد."
        )
    return cleaned or None


def _parse_bool(value, label):
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "on", "yes"):
        return True
    if value in (0, "0", "false", "off", "no"):
        return False
    raise HardwareValidationError(f"{label} نامعتبر است.")


def normalize_door_hardware(payload):
    """Return a canonical, database-ready hardware dictionary."""
    data = payload or {}
    hinge_brand = _clean_text(data.get("hinge_brand"), "برند لولا", required=True)
    hinge_color = _clean_text(data.get("hinge_color"), "رنگ لولا", required=True)
    try:
        hinge_count = int(data.get("hinge_count"))
    except (TypeError, ValueError):
        raise HardwareValidationError("تعداد لولا باید عدد صحیح باشد.") from None
    if not 1 <= hinge_count <= 20:
        raise HardwareValidationError("تعداد لولا باید بین ۱ تا ۲۰ باشد.")

    has_handle = _parse_bool(data.get("has_handle"), "وضعیت دستگیره")
    normalized = {
        "hinge_brand": hinge_brand,
        "hinge_color": hinge_color,
        "hinge_count": hinge_count,
        "has_handle": 1 if has_handle else 0,
        "handle_type": None,
        "handle_brand": None,
        "handle_model": None,
        "handle_color": None,
        "lock_source": None,
        "lock_brand": None,
        "lock_model": None,
        "cylinder_brand": None,
        "cylinder_model": None,
    }
    if not has_handle:
        return normalized

    handle_type = _clean_text(data.get("handle_type"), "نوع دستگیره", required=True)
    if handle_type not in HANDLE_TYPES:
        raise HardwareValidationError("نوع دستگیره باید دوتکه یا تک‌رزت باشد.")
    normalized.update(
        {
            "handle_type": handle_type,
            "handle_brand": _clean_text(
                data.get("handle_brand"), "برند دستگیره", required=True
            ),
            "handle_model": _clean_text(
                data.get("handle_model"), "مدل دستگیره", required=True
            ),
            "handle_color": _clean_text(
                data.get("handle_color"), "رنگ دستگیره", required=True
            ),
        }
    )

    if handle_type == "two_piece":
        normalized.update(
            {
                "lock_source": "separate",
                "lock_brand": _clean_text(
                    data.get("lock_brand"), "برند قفل", required=True
                ),
                "lock_model": _clean_text(
                    data.get("lock_model"), "مدل قفل", required=True
                ),
                "cylinder_brand": _clean_text(
                    data.get("cylinder_brand"), "برند سیلندر", required=True
                ),
                "cylinder_model": _clean_text(
                    data.get("cylinder_model"), "مدل سیلندر", required=True
                ),
            }
        )
        return normalized

    lock_source = _clean_text(data.get("lock_source"), "نوع قفل", required=True)
    if lock_source not in LOCK_SOURCES:
        raise HardwareValidationError(
            "برای تک‌رزت، قفل مخصوص همان برند یا قفل جداگانه را انتخاب کنید."
        )
    normalized["lock_source"] = lock_source
    if lock_source == "separate":
        normalized["lock_brand"] = _clean_text(
            data.get("lock_brand"), "برند قفل جداگانه", required=True
        )
        normalized["lock_model"] = _clean_text(
            data.get("lock_model"), "مدل قفل جداگانه", required=True
        )
    return normalized


def hardware_summary(hardware):
    """Build a short Persian summary for tables and confirmations."""
    if not hardware or not hardware.get("hardware_configured", True):
        return "یراق ثبت نشده"
    hinge = (
        f"لولا {hardware.get('hinge_brand') or '—'}، "
        f"{hardware.get('hinge_color') or '—'}، "
        f"{hardware.get('hinge_count') or '—'} عدد"
    )
    if not hardware.get("has_handle"):
        return f"{hinge}؛ بدون دستگیره"
    handle_type = "دوتکه" if hardware.get("handle_type") == "two_piece" else "تک‌رزت"
    handle = (
        f"دستگیره {handle_type} {hardware.get('handle_brand') or '—'}"
        f"، مدل {hardware.get('handle_model') or '—'}"
        f"، {hardware.get('handle_color') or '—'}"
    )
    if hardware.get("lock_source") == "own_brand":
        lock = f"قفل مخصوص {hardware.get('handle_brand') or 'همان برند'}"
    else:
        lock = (
            f"قفل {hardware.get('lock_brand') or '—'}"
            f"، مدل {hardware.get('lock_model') or '—'}"
        )
    if hardware.get("handle_type") == "two_piece":
        cylinder = (
            f"سیلندر {hardware.get('cylinder_brand') or '—'}"
            f"، مدل {hardware.get('cylinder_model') or '—'}"
        )
    else:
        cylinder = "بدون سیلندر"
    return f"{hinge}؛ {handle}؛ {lock}؛ {cylinder}"
