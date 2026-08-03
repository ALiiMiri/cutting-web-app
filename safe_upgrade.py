#!/usr/bin/env python3
import fcntl
import os
import sqlite3
import sys

import backup_manager
import database
from config import Config
from maintenance import disable_maintenance, enable_maintenance


PROTECTED_TABLES = (
    "projects", "doors", "profile_types", "inventory_items", "inventory_pieces",
    "inventory_logs", "inventory_operations", "inventory_waste_items", "users",
    "door_hardware",
    "door_installation_locations",
    "hardware_catalog_options",
)


def _counts(db_path):
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in PROTECTED_TABLES if table in tables
        }
    finally:
        conn.close()


def _validate(db_path, before_counts):
    conn = sqlite3.connect(db_path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"integrity_check: {integrity}")
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise RuntimeError(f"foreign_key_check: {len(foreign_keys)} errors")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
    finally:
        conn.close()
    after_counts = _counts(db_path)
    decreased = {
        table: (count, after_counts.get(table, 0))
        for table, count in before_counts.items()
        if after_counts.get(table, 0) < count
    }
    if decreased:
        raise RuntimeError(f"کاهش غیرمجاز تعداد رکوردها: {decreased}")
    return after_counts


def run_upgrade():
    os.makedirs(os.path.dirname(Config.DB_NAME), exist_ok=True)
    lock_path = f"{Config.DB_NAME}.upgrade.lock"
    with open(lock_path, "w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        enable_maintenance("database_upgrade", {"database": Config.DB_NAME})
        backup_filename = None
        before = _counts(Config.DB_NAME)
        try:
            if os.path.exists(Config.DB_NAME):
                ok, backup_path = backup_manager.create_backup(
                    reason="before_safe_upgrade",
                    user="system",
                    metadata={"before_counts": before},
                )
                if not ok:
                    raise RuntimeError(f"بکاپ پیش از ارتقا ناموفق بود: {backup_path}")
                backup_filename = os.path.basename(backup_path)
            database.init_db(allow_migrations=True)
            after = _validate(Config.DB_NAME, before)
            print(f"SAFE_UPGRADE_OK backup={backup_filename} counts={after}")
            return 0
        except Exception:
            if backup_filename:
                restored, message = backup_manager.restore_backup(
                    backup_filename, create_pre_restore_backup=False
                )
                print(f"ROLLBACK {'OK' if restored else 'FAILED'}: {message}", file=sys.stderr)
            raise
        finally:
            disable_maintenance()


if __name__ == "__main__":
    try:
        raise SystemExit(run_upgrade())
    except Exception as exc:
        print(f"SAFE_UPGRADE_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
