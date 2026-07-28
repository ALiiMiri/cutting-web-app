"""Persistent grouped cutting orders, reservations, and per-bar consumption."""

from collections import Counter
import json
import math
import sqlite3

from cutting_calculator import (
    CuttingPlanError,
    calculate_cutting_plan,
    make_inventory_variant_key,
    normalize_color_name,
)
from database import (
    _create_inventory_operation,
    _record_inventory_operation_item,
    get_all_profile_types,
    get_db_connection,
    get_doors_for_project_db,
    get_inventory_settings,
    get_project_details_db,
)
from date_utils import get_shamsi_datetime_iso
from profile_names import normalize_profile_name


ORDER_STATUS_LABELS = {
    "draft": "پیش‌نویس",
    "reserved": "رزرو شده",
    "sent_to_factory": "ارسال‌شده به کارخانه",
    "partially_cut": "بخشی برش خورده",
    "completed": "تکمیل‌شده",
    "cancelled": "لغوشده",
}
BAR_STATUS_LABELS = {
    "planned": "برنامه‌ریزی‌شده",
    "reserved": "رزرو شده",
    "cut": "برش خورده",
    "cancelled": "لغوشده",
}
EVENT_LABELS = {
    "created": "ایجاد دستور",
    "version_created": "ایجاد نسخه جدید",
    "reserved": "رزرو منابع",
    "reservations_released": "آزادسازی رزروها",
    "sent_to_factory": "ارسال به کارخانه",
    "inventory_consumed": "مصرف قطعی منبع انبار",
    "remainder_piece_created": "ثبت تکه باقی‌مانده",
    "waste_registered": "ثبت ضایعات",
    "bar_cut": "تأیید برش شاخه",
    "cancelled": "لغو دستور",
    "remaining_cancelled": "لغو شاخه‌های برش‌نخورده",
    "revision_created": "پیوند نسخه جدید",
}


class CuttingOrderError(ValueError):
    pass


def _project_cutting_blockers(cursor, project_ids, *, exclude_order_id=None):
    """Return projects that already have an active/completed cutting history."""
    normalized_ids = sorted({int(value) for value in project_ids if int(value) > 0})
    if not normalized_ids:
        return {}

    placeholders = ",".join("?" for _ in normalized_ids)
    order_params = list(normalized_ids)
    exclude_sql = ""
    if exclude_order_id is not None:
        exclude_sql = " AND co.id != ?"
        order_params.append(int(exclude_order_id))

    blockers = {}
    rows = cursor.execute(
        f"""
        SELECT cop.project_id,co.id AS order_id,co.order_number,co.status
        FROM cutting_order_projects cop
        JOIN cutting_orders co ON co.id=cop.order_id
        WHERE cop.project_id IN ({placeholders})
          AND co.status != 'cancelled'
          {exclude_sql}
        ORDER BY co.id DESC
        """,
        order_params,
    ).fetchall()
    for row in rows:
        project_id = int(row["project_id"])
        blockers.setdefault(
            project_id,
            {
                "source": "cutting_order",
                "order_id": row["order_id"],
                "order_number": row["order_number"],
                "status": row["status"],
                "message": (
                    f"برش این سفارش قبلاً در دستور "
                    f"«{row['order_number'] or row['order_id']}» محاسبه شده است."
                ),
            },
        )

    existing_tables = {
        row["name"]
        for row in cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table'
              AND name IN ('inventory_cutting_applications','inventory_deductions')
            """
        ).fetchall()
    }
    if "inventory_cutting_applications" in existing_tables:
        for row in cursor.execute(
            f"""
            SELECT project_id,applied_at
            FROM inventory_cutting_applications
            WHERE project_id IN ({placeholders})
            """,
            normalized_ids,
        ).fetchall():
            project_id = int(row["project_id"])
            blockers.setdefault(
                project_id,
                {
                    "source": "applied_cutting_plan",
                    "applied_at": row["applied_at"],
                    "message": "برش این سفارش قبلاً انجام و از انبار کسر شده است.",
                },
            )

    if "inventory_deductions" in existing_tables:
        for row in cursor.execute(
            f"""
            SELECT DISTINCT project_id
            FROM inventory_deductions
            WHERE project_id IN ({placeholders})
            """,
            normalized_ids,
        ).fetchall():
            project_id = int(row["project_id"])
            blockers.setdefault(
                project_id,
                {
                    "source": "legacy_inventory_deduction",
                    "message": "برای این سفارش قبلاً کسر انبار ثبت شده است.",
                },
            )
    return blockers


def get_project_cutting_blockers(project_ids):
    """Expose cutting eligibility for project selection screens."""
    conn = get_db_connection()
    try:
        return _project_cutting_blockers(conn.cursor(), project_ids)
    finally:
        conn.close()


def _raise_for_project_cutting_blockers(projects, blockers):
    if not blockers:
        return
    project_by_id = {int(project["id"]): project for project in projects}
    labels = []
    for project_id in sorted(blockers):
        project = project_by_id.get(project_id, {})
        labels.append(
            str(
                project.get("order_ref")
                or project.get("project_code")
                or project_id
            )
        )
    raise CuttingOrderError(
        "سفارش‌های زیر قبلاً محاسبه برش شده‌اند و قابل انتخاب مجدد نیستند: "
        + "، ".join(labels)
    )


def _event(
    cursor,
    order_id,
    event_type,
    actor_user_id,
    *,
    bar_id=None,
    from_status=None,
    to_status=None,
    details=None,
):
    cursor.execute(
        """
        INSERT INTO cutting_order_events
            (order_id,bar_id,event_type,from_status,to_status,actor_user_id,
             details_json,created_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            order_id,
            bar_id,
            event_type,
            from_status,
            to_status,
            actor_user_id,
            json.dumps(details or {}, ensure_ascii=False, separators=(",", ":")),
            get_shamsi_datetime_iso(),
        ),
    )


def _available_pieces_for_variants(variants):
    conn = get_db_connection()
    try:
        result = {}
        profiles = {
            normalize_profile_name(row["name"]): dict(row)
            for row in conn.execute("SELECT id,name FROM profile_types").fetchall()
        }
        colors = {
            normalize_color_name(row["name"]): dict(row)
            for row in conn.execute("SELECT id,name FROM profile_colors").fetchall()
        }
        for profile_name, color_name in variants:
            profile = profiles.get(profile_name)
            color = colors.get(color_name)
            if not profile or not color:
                continue
            rows = conn.execute(
                """
                SELECT ip.id,ip.length,ip.color_id
                FROM inventory_pieces ip
                WHERE ip.profile_type_id=? AND ip.color_id=?
                  AND NOT EXISTS (
                      SELECT 1 FROM inventory_reservations r
                      WHERE r.resource_type='piece' AND r.inventory_piece_id=ip.id
                        AND r.status='active'
                  )
                ORDER BY ip.length DESC,ip.id
                """,
                (profile["id"], color["id"]),
            ).fetchall()
            result[make_inventory_variant_key(profile_name, color_name)] = [
                dict(row) for row in rows
            ]
        return result
    finally:
        conn.close()


def _resolve_variants(cursor):
    profiles = {}
    duplicates = set()
    for row in cursor.execute(
        "SELECT id,name,default_length,weight_per_meter,min_waste FROM profile_types"
    ):
        key = normalize_profile_name(row["name"])
        if key in profiles:
            duplicates.add(key)
        profiles[key] = dict(row)
    for key in duplicates:
        profiles.pop(key, None)
    colors = {
        normalize_color_name(row["name"]): dict(row)
        for row in cursor.execute("SELECT id,name FROM profile_colors")
    }
    return profiles, colors


def create_cutting_order(
    project_ids,
    actor_user_id,
    *,
    parent_order_id=None,
    exclude_piece_keys=None,
):
    """Calculate and persist a grouped order without changing or reserving stock."""
    normalized_ids = []
    for value in project_ids:
        try:
            project_id = int(value)
        except (TypeError, ValueError):
            continue
        if project_id > 0 and project_id not in normalized_ids:
            normalized_ids.append(project_id)
    if not normalized_ids:
        raise CuttingOrderError("حداقل یک سفارش را انتخاب کنید.")

    projects = []
    doors = []
    for project_id in normalized_ids:
        project = get_project_details_db(project_id)
        if not project:
            raise CuttingOrderError(f"سفارش با شناسه {project_id} پیدا نشد.")
        project_doors = get_doors_for_project_db(project_id)
        if not project_doors:
            raise CuttingOrderError(
                f"سفارش «{project.get('order_ref') or project_id}» دربی برای محاسبه ندارد."
            )
        projects.append(project)
        for row_number, door in enumerate(project_doors, start=1):
            doors.append(
                {
                    **door,
                    "_project_id": project_id,
                    "_project_name": project.get("customer_name"),
                    "_project_order_ref": project.get("order_ref"),
                    "_project_code": project.get("project_code"),
                    "row_number": row_number,
                }
            )

    blockers = get_project_cutting_blockers(normalized_ids)
    if parent_order_id is not None:
        conn = get_db_connection()
        try:
            blockers = _project_cutting_blockers(
                conn.cursor(),
                normalized_ids,
                exclude_order_id=parent_order_id,
            )
        finally:
            conn.close()
    _raise_for_project_cutting_blockers(projects, blockers)

    settings = get_inventory_settings()
    use_inventory = bool(settings.get("use_inventory_for_cutting", False))
    prefer_pieces = bool(settings.get("prefer_inventory_pieces", False))
    strategy = settings.get("inventory_optimization_strategy", "minimize_waste")
    variants = {
        (
            normalize_profile_name(door.get("noe_profile")),
            normalize_color_name(door.get("rang")),
        )
        for door in doors
        if normalize_profile_name(door.get("noe_profile"))
    }
    available_pieces = _available_pieces_for_variants(variants) if use_inventory else {}
    try:
        plan = calculate_cutting_plan(
            doors,
            get_all_profile_types(),
            available_pieces_by_profile=available_pieces,
            use_inventory=use_inventory,
            prefer_inventory_pieces=prefer_pieces,
            optimization_strategy=strategy,
            exclude_piece_keys=exclude_piece_keys,
        )
    except CuttingPlanError as exc:
        raise CuttingOrderError(str(exc)) from exc

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        blockers = _project_cutting_blockers(
            cursor,
            normalized_ids,
            exclude_order_id=parent_order_id,
        )
        _raise_for_project_cutting_blockers(projects, blockers)
        profiles, colors = _resolve_variants(cursor)
        version = 1
        if parent_order_id is not None:
            parent = cursor.execute(
                "SELECT id,version FROM cutting_orders WHERE id=?", (parent_order_id,)
            ).fetchone()
            if not parent:
                raise CuttingOrderError("نسخه قبلی سفارش برش پیدا نشد.")
            version = int(parent["version"]) + 1

        now = get_shamsi_datetime_iso()
        settings_snapshot = {
            "use_inventory": use_inventory,
            "prefer_inventory_pieces": prefer_pieces,
            "optimization_strategy": plan["optimization_strategy"],
            "blade_width": plan["blade_width"],
            "stats": plan["stats"],
            "invalid_rows": plan["invalid_rows"],
        }
        cursor.execute(
            """
            INSERT INTO cutting_orders
                (version,parent_order_id,status,fingerprint,settings_snapshot_json,
                 created_by_user_id,created_at)
            VALUES (?,?, 'draft',?,?,?,?)
            """,
            (
                version,
                parent_order_id,
                plan["fingerprint"],
                json.dumps(settings_snapshot, ensure_ascii=False, separators=(",", ":")),
                actor_user_id,
                now,
            ),
        )
        order_id = cursor.lastrowid
        order_number = f"CO-{now[:4]}-{order_id:06d}"
        cursor.execute(
            "UPDATE cutting_orders SET order_number=? WHERE id=?",
            (order_number, order_id),
        )

        project_by_id = {project["id"]: project for project in projects}
        for project in projects:
            cursor.execute(
                """
                INSERT INTO cutting_order_projects
                    (order_id,project_id,project_name_snapshot,
                     project_order_ref_snapshot,project_code_snapshot,
                     measurement_unit_snapshot)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    order_id,
                    project["id"],
                    project.get("customer_name") or f"سفارش {project['id']}",
                    project.get("order_ref"),
                    project.get("project_code"),
                    project.get("measurement_unit") or "cm",
                ),
            )

        for sequence_no, bin_data in enumerate(plan["processed_bins"], start=1):
            profile_key = normalize_profile_name(bin_data["profile_type"])
            color_key = normalize_color_name(bin_data["color_name"])
            profile = profiles.get(profile_key)
            color = colors.get(color_key)
            if not profile:
                raise CuttingOrderError(
                    f"پروفیل «{bin_data['profile_type']}» در انبار یکتا نیست."
                )
            if not color:
                raise CuttingOrderError(
                    f"رنگ «{bin_data['color_name']}» در انبار تعریف نشده است."
                )
            cursor.execute(
                """
                INSERT INTO cutting_order_bars
                    (order_id,sequence_no,profile_type_id,color_id,
                     profile_name_snapshot,color_name_snapshot,source_type,
                     source_inventory_piece_id,initial_length,planned_remaining,
                     min_waste_snapshot,weight_per_meter_snapshot,blade_width,
                     kerf_loss,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'planned')
                """,
                (
                    order_id,
                    sequence_no,
                    profile["id"],
                    color["id"],
                    bin_data["profile_type"],
                    bin_data["color_name"],
                    "inventory_piece"
                    if bin_data["from_inventory_piece"]
                    else "new_stock",
                    bin_data.get("inventory_piece_id"),
                    bin_data["initial_length"],
                    bin_data["remaining"],
                    bin_data["min_waste"],
                    bin_data["weight_per_meter"],
                    plan["blade_width"],
                    bin_data["kerf_loss"],
                ),
            )
            bar_id = cursor.lastrowid
            for piece_no, piece in enumerate(bin_data["piece_details"], start=1):
                source_project = project_by_id.get(piece.get("project_id"), {})
                cursor.execute(
                    """
                    INSERT INTO cutting_order_pieces
                        (bar_id,sequence_no,project_id,project_name_snapshot,
                         project_order_ref_snapshot,project_code_snapshot,door_id,
                         door_row_number,door_location_snapshot,door_quantity_index,
                         member_type,member_label,cut_instruction,length)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        bar_id,
                        piece_no,
                        piece.get("project_id"),
                        piece.get("project_name")
                        or source_project.get("customer_name"),
                        piece.get("project_order_ref")
                        or source_project.get("order_ref"),
                        piece.get("project_code")
                        or source_project.get("project_code"),
                        piece.get("door_id"),
                        piece.get("door_row_number"),
                        piece.get("door_location"),
                        piece.get("door_quantity_index"),
                        piece["member_type"],
                        piece["member_label"],
                        piece["cut_instruction"],
                        piece["length"],
                    ),
                )

        _event(
            cursor,
            order_id,
            "version_created" if parent_order_id is not None else "created",
            actor_user_id,
            to_status="draft",
            details={
                "project_ids": normalized_ids,
                "parent_order_id": parent_order_id,
                "bar_count": plan["total_bins"],
                "invalid_rows": plan["invalid_rows"],
            },
        )
        conn.commit()
        return order_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reserve_cutting_order(order_id, actor_user_id):
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        order = cursor.execute(
            "SELECT * FROM cutting_orders WHERE id=?", (order_id,)
        ).fetchone()
        if not order:
            raise CuttingOrderError("سفارش برش پیدا نشد.")
        if order["status"] == "reserved":
            conn.rollback()
            return False
        if order["status"] != "draft":
            raise CuttingOrderError("فقط سفارش پیش‌نویس را می‌توان رزرو کرد.")

        bars = cursor.execute(
            "SELECT * FROM cutting_order_bars WHERE order_id=? AND status='planned' ORDER BY sequence_no",
            (order_id,),
        ).fetchall()
        if not bars:
            raise CuttingOrderError("این سفارش شاخه‌ای برای رزرو ندارد.")

        stock_needs = Counter(
            (bar["profile_type_id"], bar["color_id"])
            for bar in bars
            if bar["source_type"] == "new_stock"
        )
        errors = []
        for (profile_id, color_id), needed in stock_needs.items():
            row = cursor.execute(
                "SELECT quantity FROM inventory_items WHERE profile_type_id=? AND color_id=?",
                (profile_id, color_id),
            ).fetchone()
            physical = int(row["quantity"]) if row else 0
            reserved = cursor.execute(
                """
                SELECT COUNT(*) FROM inventory_reservations
                WHERE profile_type_id=? AND color_id=? AND resource_type='stock'
                  AND status='active'
                """,
                (profile_id, color_id),
            ).fetchone()[0]
            if physical - int(reserved) < needed:
                sample = next(
                    bar
                    for bar in bars
                    if bar["profile_type_id"] == profile_id
                    and bar["color_id"] == color_id
                )
                errors.append(
                    f"موجودی آزاد «{sample['profile_name_snapshot']} — "
                    f"{sample['color_name_snapshot']}» کافی نیست؛ نیاز {needed}، "
                    f"موجودی آزاد {physical - int(reserved)} شاخه."
                )

        for bar in bars:
            if bar["source_type"] != "inventory_piece":
                continue
            piece = cursor.execute(
                "SELECT id,length,profile_type_id,color_id FROM inventory_pieces WHERE id=?",
                (bar["source_inventory_piece_id"],),
            ).fetchone()
            conflict = cursor.execute(
                """
                SELECT 1 FROM inventory_reservations
                WHERE inventory_piece_id=? AND resource_type='piece' AND status='active'
                """,
                (bar["source_inventory_piece_id"],),
            ).fetchone()
            if (
                not piece
                or conflict
                or piece["profile_type_id"] != bar["profile_type_id"]
                or piece["color_id"] != bar["color_id"]
                or abs(float(piece["length"]) - float(bar["initial_length"])) > 0.001
            ):
                errors.append(
                    f"قطعه انبار شماره {bar['source_inventory_piece_id']} دیگر آزاد یا مطابق طرح نیست."
                )
        if errors:
            raise CuttingOrderError("\n".join(errors))

        now = get_shamsi_datetime_iso()
        for bar in bars:
            cursor.execute(
                """
                INSERT INTO inventory_reservations
                    (order_id,bar_id,profile_type_id,color_id,resource_type,
                     inventory_piece_id,status,reserved_at,reserved_by_user_id)
                VALUES (?,?,?,?,?,?,'active',?,?)
                """,
                (
                    order_id,
                    bar["id"],
                    bar["profile_type_id"],
                    bar["color_id"],
                    "piece" if bar["source_type"] == "inventory_piece" else "stock",
                    bar["source_inventory_piece_id"],
                    now,
                    actor_user_id,
                ),
            )
            cursor.execute(
                "UPDATE cutting_order_bars SET status='reserved',reserved_at=? WHERE id=?",
                (now, bar["id"]),
            )
        cursor.execute(
            """
            UPDATE cutting_orders
            SET status='reserved',reserved_at=?,reserved_by_user_id=?
            WHERE id=? AND status='draft'
            """,
            (now, actor_user_id, order_id),
        )
        _event(
            cursor,
            order_id,
            "reserved",
            actor_user_id,
            from_status="draft",
            to_status="reserved",
            details={"bar_count": len(bars)},
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def send_cutting_order(order_id, actor_user_id):
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        order = cursor.execute(
            "SELECT status FROM cutting_orders WHERE id=?", (order_id,)
        ).fetchone()
        if not order:
            raise CuttingOrderError("سفارش برش پیدا نشد.")
        if order["status"] == "sent_to_factory":
            conn.rollback()
            return False
        if order["status"] != "reserved":
            raise CuttingOrderError("ابتدا باید همه منابع این سفارش رزرو شوند.")
        now = get_shamsi_datetime_iso()
        cursor.execute(
            """
            UPDATE cutting_orders
            SET status='sent_to_factory',sent_at=?,sent_by_user_id=?,locked_at=?
            WHERE id=? AND status='reserved'
            """,
            (now, actor_user_id, now, order_id),
        )
        _event(
            cursor,
            order_id,
            "sent_to_factory",
            actor_user_id,
            from_status="reserved",
            to_status="sent_to_factory",
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _confirm_bar_cut_in_transaction(
    cursor,
    order,
    bar,
    actor_user_id,
    actual_remaining=None,
):
    """Consume one bar using the caller's open inventory transaction."""
    order_id = int(order["id"])
    bar_id = int(bar["id"])
    if bar["status"] == "cut":
        return False
    if order["status"] not in ("sent_to_factory", "partially_cut"):
        raise CuttingOrderError("این سفارش هنوز برای کارخانه ارسال نشده است.")
    if bar["status"] != "reserved":
        raise CuttingOrderError("این شاخه رزرو فعال ندارد.")
    reservation = cursor.execute(
        """
        SELECT * FROM inventory_reservations
        WHERE bar_id=? AND order_id=? AND status='active'
        """,
        (bar_id, order_id),
    ).fetchone()
    if not reservation:
        raise CuttingOrderError("رزرو فعال این شاخه پیدا نشد.")

    if actual_remaining in (None, ""):
        remaining = float(bar["planned_remaining"])
    else:
        try:
            remaining = float(actual_remaining)
        except (TypeError, ValueError) as exc:
            raise CuttingOrderError("طول باقی‌مانده واقعی معتبر نیست.") from exc
    if (
        not math.isfinite(remaining)
        or remaining < 0
        or remaining > float(bar["initial_length"])
    ):
        raise CuttingOrderError("طول باقی‌مانده باید بین صفر و طول اولیه شاخه باشد.")

    project_rows = cursor.execute(
        "SELECT project_id FROM cutting_order_projects WHERE order_id=?",
        (order_id,),
    ).fetchall()
    project_id = project_rows[0]["project_id"] if len(project_rows) == 1 else None
    now = get_shamsi_datetime_iso()
    operation_id = _create_inventory_operation(
        cursor,
        "cutting_order_bar",
        description=(
            f"تأیید برش شاخه {bar['sequence_no']} از سفارش "
            f"{order['order_number']}"
        ),
        project_id=project_id,
        actor_user_id=actor_user_id,
        is_reversible=False,
    )
    if reservation["resource_type"] == "stock":
        stock = cursor.execute(
            "SELECT quantity FROM inventory_items WHERE profile_type_id=? AND color_id=?",
            (bar["profile_type_id"], bar["color_id"]),
        ).fetchone()
        before = int(stock["quantity"]) if stock else 0
        cursor.execute(
            """
            UPDATE inventory_items SET quantity=quantity-1,last_updated=CURRENT_TIMESTAMP
            WHERE profile_type_id=? AND color_id=? AND quantity>=1
            """,
            (bar["profile_type_id"], bar["color_id"]),
        )
        if cursor.rowcount != 1:
            raise CuttingOrderError("موجودی فیزیکی شاخه کامل دیگر کافی نیست.")
        _record_inventory_operation_item(
            cursor,
            operation_id,
            1,
            "stock_delta",
            bar["profile_type_id"],
            bar["profile_name_snapshot"],
            quantity_delta=-1,
            before_quantity=before,
            after_quantity=before - 1,
            color_id=bar["color_id"],
            color_name=bar["color_name_snapshot"],
        )
        cursor.execute(
            """
            INSERT INTO inventory_logs
                (profile_type_id,color_id,color_name_snapshot,change_type,
                 quantity,project_id,description,timestamp,operation_id)
            VALUES (?,?,?,'remove_stock',1,?,?,?,?)
            """,
            (
                bar["profile_type_id"],
                bar["color_id"],
                bar["color_name_snapshot"],
                project_id,
                f"برش شاخه {bar['sequence_no']} سفارش {order['order_number']}",
                now,
                operation_id,
            ),
        )
    else:
        piece = cursor.execute(
            "SELECT * FROM inventory_pieces WHERE id=?",
            (reservation["inventory_piece_id"],),
        ).fetchone()
        if not piece:
            raise CuttingOrderError("قطعه رزروشده دیگر در انبار وجود ندارد.")
        cursor.execute(
            "DELETE FROM inventory_pieces WHERE id=?",
            (reservation["inventory_piece_id"],),
        )
        if cursor.rowcount != 1:
            raise CuttingOrderError("مصرف قطعه رزروشده انجام نشد.")
        _record_inventory_operation_item(
            cursor,
            operation_id,
            1,
            "piece_remove",
            bar["profile_type_id"],
            bar["profile_name_snapshot"],
            piece_id=piece["id"],
            length=piece["length"],
            color_id=bar["color_id"],
            color_name=bar["color_name_snapshot"],
        )
        cursor.execute(
            """
            INSERT INTO inventory_logs
                (profile_type_id,color_id,color_name_snapshot,change_type,
                 length,piece_id,project_id,description,timestamp,operation_id)
            VALUES (?,?,?,'remove_piece',?,?,?,?,?,?)
            """,
            (
                bar["profile_type_id"],
                bar["color_id"],
                bar["color_name_snapshot"],
                piece["length"],
                piece["id"],
                project_id,
                f"برش شاخه {bar['sequence_no']} سفارش {order['order_number']}",
                now,
                operation_id,
            ),
        )

    _event(
        cursor,
        order_id,
        "inventory_consumed",
        actor_user_id,
        bar_id=bar_id,
        details={
            "resource_type": reservation["resource_type"],
            "inventory_piece_id": reservation["inventory_piece_id"],
            "inventory_operation_id": operation_id,
        },
    )

    returned_piece_id = None
    waste_item_id = None
    if remaining >= float(bar["min_waste_snapshot"]) and remaining > 0:
        cursor.execute(
            """
            INSERT INTO inventory_pieces
                (profile_type_id,color_id,length,source_cutting_order_id,
                 source_cutting_bar_id)
            VALUES (?,?,?,?,?)
            """,
            (
                bar["profile_type_id"],
                bar["color_id"],
                remaining,
                order_id,
                bar_id,
            ),
        )
        returned_piece_id = cursor.lastrowid
        _record_inventory_operation_item(
            cursor,
            operation_id,
            2,
            "piece_add",
            bar["profile_type_id"],
            bar["profile_name_snapshot"],
            piece_id=returned_piece_id,
            length=remaining,
            color_id=bar["color_id"],
            color_name=bar["color_name_snapshot"],
        )
        cursor.execute(
            """
            INSERT INTO inventory_logs
                (profile_type_id,color_id,color_name_snapshot,change_type,
                 length,piece_id,project_id,description,timestamp,operation_id)
            VALUES (?,?,?,'add_piece',?,?,?,?,?,?)
            """,
            (
                bar["profile_type_id"],
                bar["color_id"],
                bar["color_name_snapshot"],
                remaining,
                returned_piece_id,
                project_id,
                f"باقی‌مانده شاخه {bar['sequence_no']} سفارش {order['order_number']}",
                now,
                operation_id,
            ),
        )
        _event(
            cursor,
            order_id,
            "remainder_piece_created",
            actor_user_id,
            bar_id=bar_id,
            details={"piece_id": returned_piece_id, "length": remaining},
        )
    elif remaining > 0:
        calculated_weight = (
            remaining / 100.0 * float(bar["weight_per_meter_snapshot"])
        )
        cursor.execute(
            """
            INSERT INTO inventory_waste_items
                (cutting_operation_id,project_id,profile_type_id,color_id,
                 profile_name_snapshot,color_name_snapshot,length_cm,
                 weight_per_meter_snapshot,calculated_weight_kg,source_type,
                 source_piece_id,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'available',?,?)
            """,
            (
                operation_id,
                project_id,
                bar["profile_type_id"],
                bar["color_id"],
                bar["profile_name_snapshot"],
                bar["color_name_snapshot"],
                remaining,
                bar["weight_per_meter_snapshot"],
                calculated_weight,
                bar["source_type"],
                bar["source_inventory_piece_id"],
                now,
                now,
            ),
        )
        waste_item_id = cursor.lastrowid
        _event(
            cursor,
            order_id,
            "waste_registered",
            actor_user_id,
            bar_id=bar_id,
            details={"waste_item_id": waste_item_id, "length": remaining},
        )

    cursor.execute(
        """
        UPDATE inventory_reservations
        SET status='consumed',consumed_at=?,consumed_by_user_id=?
        WHERE id=? AND status='active'
        """,
        (now, actor_user_id, reservation["id"]),
    )
    cursor.execute(
        """
        UPDATE cutting_order_bars
        SET status='cut',cut_at=?,cut_by_user_id=?,actual_remaining=?,
            inventory_operation_id=?,returned_piece_id=?,waste_item_id=?
        WHERE id=? AND status='reserved'
        """,
        (
            now,
            actor_user_id,
            remaining,
            operation_id,
            returned_piece_id,
            waste_item_id,
            bar_id,
        ),
    )
    uncut_count = cursor.execute(
        """
        SELECT COUNT(*) FROM cutting_order_bars
        WHERE order_id=? AND status IN ('planned','reserved')
        """,
        (order_id,),
    ).fetchone()[0]
    next_status = "completed" if uncut_count == 0 else "partially_cut"
    cursor.execute(
        """
        UPDATE cutting_orders
        SET status=?,completed_at=CASE WHEN ?='completed' THEN ? ELSE completed_at END
        WHERE id=?
        """,
        (next_status, next_status, now, order_id),
    )
    _event(
        cursor,
        order_id,
        "bar_cut",
        actor_user_id,
        bar_id=bar_id,
        from_status=order["status"],
        to_status=next_status,
        details={
            "actual_remaining": remaining,
            "returned_piece_id": returned_piece_id,
            "waste_item_id": waste_item_id,
            "inventory_operation_id": operation_id,
        },
    )
    return True


def confirm_bar_cut(order_id, bar_id, actor_user_id, actual_remaining=None):
    """Consume one reserved physical source and register only its own remainder."""
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        order = cursor.execute(
            "SELECT * FROM cutting_orders WHERE id=?", (order_id,)
        ).fetchone()
        bar = cursor.execute(
            "SELECT * FROM cutting_order_bars WHERE id=? AND order_id=?",
            (bar_id, order_id),
        ).fetchone()
        if not order or not bar:
            raise CuttingOrderError("سفارش یا شاخه موردنظر پیدا نشد.")
        changed = _confirm_bar_cut_in_transaction(
            cursor,
            order,
            bar,
            actor_user_id,
            actual_remaining,
        )
        if not changed:
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def confirm_bars_cut(order_id, bar_updates, actor_user_id):
    """Confirm multiple bars atomically; any failure rolls the whole batch back."""
    normalized = []
    seen = set()
    for update in bar_updates or []:
        try:
            bar_id = int(update.get("bar_id"))
        except (AttributeError, TypeError, ValueError):
            raise CuttingOrderError("انتخاب شاخه‌ها معتبر نیست.")
        if bar_id <= 0 or bar_id in seen:
            raise CuttingOrderError("انتخاب شاخه‌ها معتبر نیست.")
        seen.add(bar_id)
        normalized.append(
            {
                "bar_id": bar_id,
                "actual_remaining": update.get("actual_remaining"),
            }
        )
    if not normalized:
        raise CuttingOrderError("حداقل یک شاخه را برای تأیید انتخاب کنید.")

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        order = cursor.execute(
            "SELECT * FROM cutting_orders WHERE id=?", (order_id,)
        ).fetchone()
        if not order:
            raise CuttingOrderError("سفارش برش پیدا نشد.")
        if order["status"] not in ("sent_to_factory", "partially_cut"):
            raise CuttingOrderError("این سفارش هنوز برای کارخانه ارسال نشده است.")

        for update in normalized:
            current_order = cursor.execute(
                "SELECT * FROM cutting_orders WHERE id=?", (order_id,)
            ).fetchone()
            bar = cursor.execute(
                "SELECT * FROM cutting_order_bars WHERE id=? AND order_id=?",
                (update["bar_id"], order_id),
            ).fetchone()
            if not bar:
                raise CuttingOrderError("یکی از شاخه‌های انتخاب‌شده پیدا نشد.")
            if bar["status"] != "reserved":
                raise CuttingOrderError(
                    f"شاخه {bar['sequence_no']} دیگر در انتظار تأیید نیست."
                )
            _confirm_bar_cut_in_transaction(
                cursor,
                current_order,
                bar,
                actor_user_id,
                update["actual_remaining"],
            )
        conn.commit()
        return len(normalized)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cancel_cutting_order(order_id, actor_user_id, reason):
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise CuttingOrderError("دلیل لغو را وارد کنید.")
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        order = cursor.execute(
            "SELECT status FROM cutting_orders WHERE id=?", (order_id,)
        ).fetchone()
        if not order:
            raise CuttingOrderError("سفارش برش پیدا نشد.")
        if order["status"] in ("completed", "cancelled"):
            conn.rollback()
            return False
        now = get_shamsi_datetime_iso()
        released_count = cursor.execute(
            """
            SELECT COUNT(*) FROM inventory_reservations
            WHERE order_id=? AND status='active'
            """,
            (order_id,),
        ).fetchone()[0]
        cursor.execute(
            """
            UPDATE inventory_reservations
            SET status='released',released_at=?,released_by_user_id=?,release_reason=?
            WHERE order_id=? AND status='active'
            """,
            (now, actor_user_id, reason, order_id),
        )
        cursor.execute(
            """
            UPDATE cutting_order_bars SET status='cancelled'
            WHERE order_id=? AND status IN ('planned','reserved')
            """,
            (order_id,),
        )
        cut_count = cursor.execute(
            "SELECT COUNT(*) FROM cutting_order_bars WHERE order_id=? AND status='cut'",
            (order_id,),
        ).fetchone()[0]
        next_status = "completed" if cut_count else "cancelled"
        cursor.execute(
            """
            UPDATE cutting_orders
            SET status=?,cancelled_at=?,cancelled_by_user_id=?,
                cancellation_reason=?,
                completed_at=CASE WHEN ?='completed' THEN ? ELSE completed_at END
            WHERE id=?
            """,
            (
                next_status,
                now,
                actor_user_id,
                reason,
                next_status,
                now,
                order_id,
            ),
        )
        _event(
            cursor,
            order_id,
            "remaining_cancelled" if cut_count else "cancelled",
            actor_user_id,
            from_status=order["status"],
            to_status=next_status,
            details={"reason": reason, "cut_bar_count": cut_count},
        )
        if released_count:
            _event(
                cursor,
                order_id,
                "reservations_released",
                actor_user_id,
                from_status=order["status"],
                to_status=next_status,
                details={"reason": reason, "released_count": released_count},
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def revise_cutting_order(order_id, actor_user_id, reason):
    """Release uncut sources and create a new version without already-cut members."""
    order = get_cutting_order(order_id)
    if not order:
        raise CuttingOrderError("سفارش برش پیدا نشد.")
    if order["status"] in ("completed", "cancelled"):
        raise CuttingOrderError("سفارش بسته‌شده قابل بازنگری نیست.")
    cut_piece_keys = {
        (
            piece.get("project_id"),
            piece.get("door_id"),
            piece.get("door_quantity_index"),
            piece.get("member_type"),
        )
        for bar in order["bars"]
        if bar["status"] == "cut"
        for piece in bar["pieces"]
    }
    project_ids = [
        project["project_id"]
        for project in order["projects"]
        if project.get("project_id") is not None
    ]
    cancel_cutting_order(order_id, actor_user_id, reason)
    new_order_id = create_cutting_order(
        project_ids,
        actor_user_id,
        parent_order_id=order_id,
        exclude_piece_keys=cut_piece_keys,
    )
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _event(
            conn.cursor(),
            order_id,
            "revision_created",
            actor_user_id,
            details={"new_order_id": new_order_id, "reason": reason},
        )
        conn.commit()
    finally:
        conn.close()
    return new_order_id


def get_cutting_order(order_id):
    conn = get_db_connection()
    try:
        order = conn.execute(
            """
            SELECT co.*,creator.username AS creator_username,
                   reserver.username AS reserver_username,sender.username AS sender_username
            FROM cutting_orders co
            LEFT JOIN users creator ON creator.id=co.created_by_user_id
            LEFT JOIN users reserver ON reserver.id=co.reserved_by_user_id
            LEFT JOIN users sender ON sender.id=co.sent_by_user_id
            WHERE co.id=?
            """,
            (order_id,),
        ).fetchone()
        if not order:
            return None
        result = dict(order)
        result["status_label"] = ORDER_STATUS_LABELS.get(
            result["status"], result["status"]
        )
        result["projects"] = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM cutting_order_projects WHERE order_id=? ORDER BY project_id",
                (order_id,),
            )
        ]
        bars = []
        for row in conn.execute(
            """
            SELECT b.*,u.username AS cut_by_username
            FROM cutting_order_bars b
            LEFT JOIN users u ON u.id=b.cut_by_user_id
            WHERE b.order_id=? ORDER BY b.sequence_no
            """,
            (order_id,),
        ):
            bar = dict(row)
            bar["status_label"] = BAR_STATUS_LABELS.get(
                bar["status"], bar["status"]
            )
            bar["pieces"] = [
                dict(piece)
                for piece in conn.execute(
                    "SELECT * FROM cutting_order_pieces WHERE bar_id=? ORDER BY sequence_no",
                    (bar["id"],),
                )
            ]
            bars.append(bar)
        result["bars"] = bars
        result["inventory_summary"] = [
            dict(row)
            for row in conn.execute(
                """
                SELECT variants.profile_type_id,variants.color_id,
                       variants.profile_name_snapshot,variants.color_name_snapshot,
                       COALESCE(ii.quantity,0) AS physical_stock,
                       (
                           SELECT COUNT(*) FROM inventory_reservations r
                           WHERE r.profile_type_id=variants.profile_type_id
                             AND r.color_id=variants.color_id
                             AND r.resource_type='stock' AND r.status='active'
                       ) AS reserved_stock,
                       MAX(0,COALESCE(ii.quantity,0)-(
                           SELECT COUNT(*) FROM inventory_reservations r
                           WHERE r.profile_type_id=variants.profile_type_id
                             AND r.color_id=variants.color_id
                             AND r.resource_type='stock' AND r.status='active'
                       )) AS available_stock,
                       (
                           SELECT COUNT(*) FROM inventory_pieces ip
                           WHERE ip.profile_type_id=variants.profile_type_id
                             AND ip.color_id=variants.color_id
                       ) AS physical_pieces,
                       (
                           SELECT COUNT(*) FROM inventory_reservations r
                           WHERE r.profile_type_id=variants.profile_type_id
                             AND r.color_id=variants.color_id
                             AND r.resource_type='piece' AND r.status='active'
                       ) AS reserved_pieces,
                       MAX(0,(
                           SELECT COUNT(*) FROM inventory_pieces ip
                           WHERE ip.profile_type_id=variants.profile_type_id
                             AND ip.color_id=variants.color_id
                       )-(
                           SELECT COUNT(*) FROM inventory_reservations r
                           WHERE r.profile_type_id=variants.profile_type_id
                             AND r.color_id=variants.color_id
                             AND r.resource_type='piece' AND r.status='active'
                       )) AS available_pieces
                FROM (
                    SELECT DISTINCT profile_type_id,color_id,
                           profile_name_snapshot,color_name_snapshot
                    FROM cutting_order_bars WHERE order_id=?
                ) variants
                LEFT JOIN inventory_items ii
                  ON ii.profile_type_id=variants.profile_type_id
                 AND ii.color_id=variants.color_id
                ORDER BY variants.profile_name_snapshot,variants.color_name_snapshot
                """,
                (order_id,),
            )
        ]
        result["events"] = []
        for row in conn.execute(
                """
                SELECT e.*,u.username AS actor_username
                FROM cutting_order_events e
                LEFT JOIN users u ON u.id=e.actor_user_id
                WHERE e.order_id=? ORDER BY e.id DESC
                """,
                (order_id,),
            ):
            event = dict(row)
            event["event_label"] = EVENT_LABELS.get(
                event["event_type"], event["event_type"]
            )
            result["events"].append(event)
        return result
    finally:
        conn.close()


def list_cutting_orders(user_id, role, limit=100):
    conn = get_db_connection()
    try:
        params = []
        where = ""
        if role == "staff":
            where = """
                WHERE co.created_by_user_id=? OR EXISTS (
                    SELECT 1 FROM cutting_order_projects cop
                    JOIN projects p ON p.id=cop.project_id
                    WHERE cop.order_id=co.id AND p.assigned_to_user_id=?
                )
            """
            params.extend([user_id, user_id])
        elif role == "factory":
            where = (
                "WHERE co.status IN "
                "('sent_to_factory','partially_cut','completed')"
            )
        rows = conn.execute(
            f"""
            SELECT co.*,u.username AS creator_username,
                   (SELECT COUNT(*) FROM cutting_order_bars b WHERE b.order_id=co.id) AS bar_count,
                   (SELECT COUNT(*) FROM cutting_order_bars b WHERE b.order_id=co.id AND b.status='cut') AS cut_count,
                   (SELECT COUNT(*) FROM cutting_order_projects p WHERE p.order_id=co.id) AS project_count
            FROM cutting_orders co
            LEFT JOIN users u ON u.id=co.created_by_user_id
            {where}
            ORDER BY co.id DESC LIMIT ?
            """,
            (*params, int(limit)),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["status_label"] = ORDER_STATUS_LABELS.get(
                item["status"], item["status"]
            )
            result.append(item)
        return result
    finally:
        conn.close()


def can_view_cutting_order(order_id, user_id, role):
    if role in ("admin", "manager", "read_only"):
        return True
    conn = get_db_connection()
    try:
        if role == "factory":
            return (
                conn.execute(
                    """
                    SELECT 1 FROM cutting_orders
                    WHERE id=? AND status IN
                        ('sent_to_factory','partially_cut','completed')
                    """,
                    (order_id,),
                ).fetchone()
                is not None
            )
        return (
            conn.execute(
                """
                SELECT 1 FROM cutting_orders co
                WHERE co.id=? AND (
                    co.created_by_user_id=? OR EXISTS (
                        SELECT 1 FROM cutting_order_projects cop
                        JOIN projects p ON p.id=cop.project_id
                        WHERE cop.order_id=co.id AND p.assigned_to_user_id=?
                    )
                )
                """,
                (order_id, user_id, user_id),
            ).fetchone()
            is not None
        )
    finally:
        conn.close()


def project_cutting_history(project_id):
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT cop.order_id) AS order_count,
                   SUM(CASE WHEN b.status='cut' THEN 1 ELSE 0 END) AS cut_bar_count,
                   SUM(CASE WHEN r.status='active' THEN 1 ELSE 0 END) AS active_reservations
            FROM cutting_order_projects cop
            LEFT JOIN cutting_order_bars b ON b.order_id=cop.order_id
            LEFT JOIN inventory_reservations r ON r.bar_id=b.id
            WHERE cop.project_id=?
            """,
            (project_id,),
        ).fetchone()
        return {
            "order_count": int(row["order_count"] or 0),
            "cut_bar_count": int(row["cut_bar_count"] or 0),
            "active_reservations": int(row["active_reservations"] or 0),
        }
    finally:
        conn.close()


def archive_project(project_id):
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "UPDATE projects SET archived_at=? WHERE id=? AND archived_at IS NULL",
            (get_shamsi_datetime_iso(), project_id),
        )
        conn.commit()
        return cursor.rowcount == 1
    finally:
        conn.close()


def archive_project_safely(project_id, actor_user_id):
    """Cancel only uncut work linked to a project, then soft-delete the project."""
    conn = get_db_connection()
    try:
        order_ids = [
            row["id"]
            for row in conn.execute(
                """
                SELECT DISTINCT co.id
                FROM cutting_orders co
                JOIN cutting_order_projects cop ON cop.order_id=co.id
                WHERE cop.project_id=?
                  AND co.status NOT IN ('completed','cancelled')
                ORDER BY co.id
                """,
                (project_id,),
            )
        ]
    finally:
        conn.close()
    for order_id in order_ids:
        cancel_cutting_order(
            order_id,
            actor_user_id,
            f"بایگانی پروژه {project_id}؛ آزادسازی فقط منابع برش‌نخورده",
        )
    return archive_project(project_id), order_ids
