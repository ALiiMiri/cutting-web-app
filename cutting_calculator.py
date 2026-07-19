"""Pure cutting-plan calculations shared by the web report and Excel export."""

from collections import defaultdict

from profile_names import normalize_profile_name


UNKNOWN_COLOR = "تعیین‌نشده"
VARIANT_SEPARATOR = " ⟡ "
BLADE_WIDTH_CM = 0.5  # 5 millimeters
TWO_SIDED_FRAME = "دو طرفه"
THREE_SIDED_FRAME = "سه طرفه"
OPTIMIZATION_STRATEGIES = {
    "minimize_waste",
    "minimize_pieces",
    "minimize_new_profiles",
}


def normalize_color_name(value):
    return " ".join(str(value or "").split()) or UNKNOWN_COLOR


def normalize_frame_type(value):
    """Return the supported frame type, preserving old rows as three-sided.

    Historically the custom field was called ``kolaft`` and was ignored by
    cutting calculations. Therefore blank, missing, and retired legacy values
    must keep the former three-sided calculation instead of silently reducing
    inventory consumption.
    """
    normalized = " ".join(str(value or "").split())
    return TWO_SIDED_FRAME if normalized == TWO_SIDED_FRAME else THREE_SIDED_FRAME


def make_inventory_variant_key(profile_name, color_name=None):
    profile_name = normalize_profile_name(profile_name)
    color_name = normalize_color_name(color_name)
    return profile_name if color_name == UNKNOWN_COLOR else f"{profile_name}{VARIANT_SEPARATOR}{color_name}"


class CuttingPlanError(ValueError):
    """Raised when a cutting plan cannot be calculated safely."""


def _as_positive_float(value, field_name, profile_name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CuttingPlanError(
            f"مقدار «{field_name}» برای پروفیل «{profile_name}» معتبر نیست."
        ) from exc
    if number <= 0:
        raise CuttingPlanError(
            f"مقدار «{field_name}» برای پروفیل «{profile_name}» باید بزرگ‌تر از صفر باشد."
        )
    return number


def _profile_settings_for(required_profiles, profiles):
    profiles_by_name = {
        normalize_profile_name(profile.get("name", "")): profile for profile in profiles
    }
    settings = {}

    for profile_name, color_name in required_profiles:
        profile = profiles_by_name.get(profile_name)
        if profile is None:
            raise CuttingPlanError(
                f"پروفیل «{profile_name}» در انبار تعریف نشده است. "
                "ابتدا نوع پروفیل را در مدیریت انبار تعریف یا نام آن را اصلاح کنید."
            )

        weight_per_meter = _as_positive_float(
            profile.get("weight_per_meter"), "وزن هر متر", profile_name
        )
        try:
            min_waste = float(profile.get("min_waste", 70))
        except (TypeError, ValueError) as exc:
            raise CuttingPlanError(
                f"حد ضایعات پروفیل «{profile_name}» معتبر نیست."
            ) from exc
        if min_waste < 0:
            raise CuttingPlanError(
                f"حد ضایعات پروفیل «{profile_name}» نمی‌تواند منفی باشد."
            )

        settings[(profile_name, color_name)] = {
            "id": profile.get("id"),
            "weight_per_meter": weight_per_meter,
            "min_waste": min_waste,
            "default_length": _as_positive_float(
                profile.get("default_length") or 600, "طول پیش‌فرض", profile_name
            ),
        }

    return settings


def _collect_requirements(doors):
    requirements = defaultdict(list)
    valid_rows = 0
    invalid_rows = []

    for row_number, door in enumerate(doors, start=1):
        try:
            width = float(door["width"])
            height = float(door["height"])
            quantity = int(door["quantity"])
            profile_name = normalize_profile_name(door.get("noe_profile"))
            color_name = normalize_color_name(door.get("rang"))
            if width <= 0 or height <= 0 or quantity <= 0 or not profile_name:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            invalid_rows.append(door.get("id", row_number))
            continue

        frame_type = normalize_frame_type(door.get("kolaft"))
        requirements[(profile_name, color_name)].extend([height] * (quantity * 2))
        if frame_type == THREE_SIDED_FRAME:
            requirements[(profile_name, color_name)].extend([width] * quantity)
        valid_rows += 1

    if not requirements:
        raise CuttingPlanError(
            "هیچ درب معتبری با عرض، ارتفاع، تعداد و نوع پروفیل معتبر برای محاسبه یافت نشد."
        )

    return dict(requirements), valid_rows, invalid_rows


def _future_fit_score(capacity, current_consumed, later_consumed):
    """Estimate how many required cuts can share a newly opened source."""
    remaining = capacity - current_consumed
    count = 1
    used = current_consumed
    for consumed in sorted(later_consumed):
        if consumed <= remaining:
            remaining -= consumed
            used += consumed
            count += 1
    return count, used, remaining


def _choose_open_bin(bins, consumed_length, optimization_strategy):
    fitting = [item for item in bins if item["remaining"] >= consumed_length]
    if not fitting:
        return None

    if optimization_strategy == "minimize_new_profiles":
        fitting.sort(
            key=lambda item: (
                not item["from_inventory_piece"],
                item["remaining"] - consumed_length,
            )
        )
    else:
        # Best-fit keeps larger opened sources available for longer future cuts.
        fitting.sort(key=lambda item: item["remaining"] - consumed_length)
    return fitting[0]


def _choose_new_source(
    available_pieces,
    consumed_length,
    later_consumed,
    stock_length,
    optimization_strategy,
    prefer_inventory_pieces,
):
    fitting_inventory = []
    for index, piece in enumerate(available_pieces):
        try:
            length = float(piece["length"])
        except (KeyError, TypeError, ValueError):
            continue
        if length >= consumed_length:
            fitting_inventory.append((index, piece, length))

    # Explicit inventory preference and the "minimize new profiles" strategy both
    # mean: use the smallest suitable offcut before opening a complete profile.
    if fitting_inventory and (
        prefer_inventory_pieces or optimization_strategy == "minimize_new_profiles"
    ):
        return min(fitting_inventory, key=lambda item: (item[2], item[1].get("id", 0)))

    if optimization_strategy == "minimize_pieces":
        candidates = [
            (
                *_future_fit_score(length, consumed_length, later_consumed),
                True,
                index,
                piece,
                length,
            )
            for index, piece, length in fitting_inventory
        ]
        candidates.append(
            (
                *_future_fit_score(stock_length, consumed_length, later_consumed),
                False,
                None,
                None,
                stock_length,
            )
        )
        # More cuts in one source is primary. On a tie prefer inventory, then the
        # smaller source, so the strategy never opens a full profile needlessly.
        selected = max(candidates, key=lambda item: (item[0], item[1], item[3], -item[6]))
        if selected[3]:
            return selected[4], selected[5], selected[6]
        return None

    if fitting_inventory:
        # Best fit: the smallest inventory piece that can satisfy this cut.
        return min(
            fitting_inventory,
            key=lambda item: (
                item[2],
                item[1].get("id", 0),
            ),
        )
    return None


def calculate_cutting_plan(
    doors,
    profiles,
    *,
    available_pieces_by_profile=None,
    use_inventory=False,
    prefer_inventory_pieces=False,
    optimization_strategy="minimize_waste",
    stock_length=600,
    blade_width=BLADE_WIDTH_CM,
):
    """Calculate a cutting plan and weight-aware remaining-material statistics.

    Lengths are in centimeters and ``weight_per_meter`` is in kilograms per meter.
    A remaining piece shorter than its profile's ``min_waste`` is discarded waste;
    longer pieces are reusable inventory.
    """

    stock_length = float(stock_length)
    if stock_length <= 0:
        raise CuttingPlanError("طول شاخه باید بزرگ‌تر از صفر باشد.")
    blade_width = float(blade_width)
    if blade_width < 0:
        raise CuttingPlanError("ضخامت تیغ برش نمی‌تواند منفی باشد.")
    if optimization_strategy not in OPTIMIZATION_STRATEGIES:
        optimization_strategy = "minimize_waste"

    requirements, valid_rows, invalid_rows = _collect_requirements(doors)
    profile_settings = _profile_settings_for(requirements, profiles)
    available_pieces_by_profile = available_pieces_by_profile or {}

    results_by_profile = {}
    used_inventory_pieces = {}
    all_bins = []

    for (profile_name, color_name), required_pieces in requirements.items():
        variant_key = make_inventory_variant_key(profile_name, color_name)
        settings = profile_settings[(profile_name, color_name)]
        bins = []
        used_piece_ids = []
        available_pieces = [
            dict(piece)
            for piece in available_pieces_by_profile.get(
                variant_key, available_pieces_by_profile.get((profile_name, color_name), [])
            )
        ]

        sorted_pieces = sorted(required_pieces, reverse=True)
        consumed_requirements = [length + blade_width for length in sorted_pieces]
        for requirement_index, piece_length in enumerate(sorted_pieces):
            consumed_length = piece_length + blade_width
            if consumed_length > stock_length:
                raise CuttingPlanError(
                    f"امکان برش قطعه {piece_length:g} سانتی‌متری از شاخه "
                    f"{stock_length:g} سانتی‌متری با تیغ ۵ میلی‌متری وجود ندارد "
                    f"(پروفیل: {profile_name})."
                )

            placed = False
            open_bin = _choose_open_bin(bins, consumed_length, optimization_strategy)
            if open_bin is not None:
                open_bin["pieces"].append(piece_length)
                open_bin["remaining"] -= consumed_length
                placed = True

            if not placed and use_inventory:
                selected_piece = _choose_new_source(
                    available_pieces,
                    consumed_length,
                    consumed_requirements[requirement_index + 1 :],
                    stock_length,
                    optimization_strategy,
                    prefer_inventory_pieces,
                )
                if selected_piece is not None:
                    piece_index, inventory_piece, inventory_length = selected_piece
                    piece_id = inventory_piece.get("id")
                    if piece_id is not None:
                        used_piece_ids.append(piece_id)
                    available_pieces.pop(piece_index)
                    bins.append(
                        {
                            "pieces": [piece_length],
                            "remaining": inventory_length - consumed_length,
                            "profile_type": profile_name,
                            "color_name": color_name,
                            "from_inventory_piece": True,
                            "inventory_piece_id": piece_id,
                            "initial_length": inventory_length,
                        }
                    )
                    placed = True

            if not placed:
                bins.append(
                    {
                        "pieces": [piece_length],
                        "remaining": stock_length - consumed_length,
                        "profile_type": profile_name,
                        "color_name": color_name,
                        "from_inventory_piece": False,
                        "initial_length": stock_length,
                    }
                )

        for bin_data in bins:
            remaining = max(0.0, float(bin_data["remaining"]))
            initial_length = float(bin_data["initial_length"])
            weight_per_meter = settings["weight_per_meter"]
            min_waste = settings["min_waste"]
            remaining_weight = remaining / 100.0 * weight_per_meter

            if 0 < remaining < min_waste:
                remaining_type = "discarded"
            elif remaining > 0:
                remaining_type = "reusable"
            else:
                remaining_type = "none"

            if remaining_type == "discarded":
                display_type = "small"
            elif remaining < stock_length / 2:
                display_type = "medium"
            else:
                display_type = "large"

            bin_data.update(
                {
                    "remaining": remaining,
                    "weight_per_meter": weight_per_meter,
                    "remaining_weight": remaining_weight,
                    "min_waste": min_waste,
                    "remaining_type": remaining_type,
                    "waste_type": display_type,
                    "used_length": initial_length - remaining,
                    "cut_count": len(bin_data["pieces"]),
                    "kerf_loss": len(bin_data["pieces"]) * blade_width,
                }
            )

        if used_piece_ids:
            used_inventory_pieces[variant_key] = used_piece_ids
        results_by_profile[variant_key] = {
            "profile_name": profile_name,
            "color_name": color_name,
            "bins": bins,
            "total_bins": len(bins),
        }
        all_bins.extend(bins)

    stats = {
        "discarded_count": 0,
        "discarded_length": 0.0,
        "discarded_weight": 0.0,
        "reusable_count": 0,
        "reusable_length": 0.0,
        "reusable_weight": 0.0,
        "total_remaining_length": 0.0,
        "total_remaining_weight": 0.0,
        "total_initial_length": 0.0,
        "total_remaining_percentage": 0.0,
        "total_kerf_length": 0.0,
    }
    profile_summaries = {}

    for variant_key, profile_result in results_by_profile.items():
        profile_name = profile_result["profile_name"]
        color_name = profile_result["color_name"]
        settings = profile_settings[(profile_name, color_name)]
        profile_bins = profile_result["bins"]
        summary = {
            "profile_type": profile_name,
            "color_name": color_name,
            "weight_per_meter": settings["weight_per_meter"],
            "min_waste": settings["min_waste"],
            "bin_count": len(profile_bins),
            "discarded_length": 0.0,
            "discarded_weight": 0.0,
            "reusable_length": 0.0,
            "reusable_weight": 0.0,
            "total_remaining_length": 0.0,
            "total_remaining_weight": 0.0,
        }
        for bin_data in profile_bins:
            remaining = bin_data["remaining"]
            remaining_weight = bin_data["remaining_weight"]
            stats["total_initial_length"] += bin_data["initial_length"]
            stats["total_kerf_length"] += bin_data["kerf_loss"]
            stats["total_remaining_length"] += remaining
            stats["total_remaining_weight"] += remaining_weight
            summary["total_remaining_length"] += remaining
            summary["total_remaining_weight"] += remaining_weight

            if bin_data["remaining_type"] == "discarded":
                stats["discarded_count"] += 1
                stats["discarded_length"] += remaining
                stats["discarded_weight"] += remaining_weight
                summary["discarded_length"] += remaining
                summary["discarded_weight"] += remaining_weight
            elif bin_data["remaining_type"] == "reusable":
                stats["reusable_count"] += 1
                stats["reusable_length"] += remaining
                stats["reusable_weight"] += remaining_weight
                summary["reusable_length"] += remaining
                summary["reusable_weight"] += remaining_weight

        profile_summaries[variant_key] = summary

    if stats["total_initial_length"] > 0:
        stats["total_remaining_percentage"] = (
            stats["total_remaining_length"] / stats["total_initial_length"] * 100
        )

    processed_bins = []
    for index, bin_data in enumerate(all_bins, start=1):
        initial_length = bin_data["initial_length"]
        used_percent = int(bin_data["used_length"] / initial_length * 100) if initial_length else 0
        remaining_percent = int(bin_data["remaining"] / initial_length * 100) if initial_length else 0
        processed_bins.append(
            {
                **bin_data,
                "index": index,
                "pieces": [round(piece, 1) for piece in bin_data["pieces"]],
                "remaining": round(bin_data["remaining"], 1),
                "remaining_weight": round(bin_data["remaining_weight"], 2),
                "initial_length": round(initial_length, 1),
                "used_length": round(bin_data["used_length"], 1),
                "weight_per_meter": round(bin_data["weight_per_meter"], 3),
                "used_percent": used_percent,
                "waste_percent": remaining_percent,
                "used_percent_style": f"{used_percent}%",
                "waste_percent_style": f"{remaining_percent}%",
                "source_text": (
                    f"قطعه انبار با شناسه {bin_data.get('inventory_piece_id')}"
                    if bin_data["from_inventory_piece"]
                    else f"از شاخه جدید {stock_length:g} سانتی‌متری"
                ),
                "source_class": "source-inventory" if bin_data["from_inventory_piece"] else "source-new",
            }
        )

    return {
        "requirements": {
            make_inventory_variant_key(profile_name, color_name): pieces
            for (profile_name, color_name), pieces in requirements.items()
        },
        "results_by_profile": results_by_profile,
        "inventory_application_data": {
            variant_key: {
                "profile_name": profile_result["profile_name"],
                "color_name": profile_result["color_name"],
                "total_bins": profile_result["total_bins"],
                "min_waste": profile_settings[(profile_result["profile_name"], profile_result["color_name"])]["min_waste"],
                "bins": [
                    {
                        "remaining": bin_data["remaining"],
                        "initial_length": bin_data["initial_length"],
                        "from_inventory_piece": bin_data["from_inventory_piece"],
                        "inventory_piece_id": bin_data.get("inventory_piece_id"),
                    }
                    for bin_data in profile_result["bins"]
                ],
            }
            for variant_key, profile_result in results_by_profile.items()
        },
        "used_inventory_pieces": used_inventory_pieces,
        "bins": all_bins,
        "processed_bins": processed_bins,
        "profile_summaries": list(profile_summaries.values()),
        "stats": stats,
        "total_bins": len(all_bins),
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "stock_length": stock_length,
        "blade_width": blade_width,
        "optimization_strategy": optimization_strategy,
    }
