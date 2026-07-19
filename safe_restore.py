#!/usr/bin/env python3
import os
import sys

import backup_manager
from maintenance import disable_maintenance, enable_maintenance
from safe_upgrade import run_upgrade


def main(filename):
    enable_maintenance("database_restore", {"backup": filename})
    try:
        success, message = backup_manager.restore_backup(filename, create_pre_restore_backup=True)
        if not success:
            raise RuntimeError(message)
        print(message)
    finally:
        disable_maintenance()
    return run_upgrade()


if __name__ == "__main__":
    if len(sys.argv) != 2 or os.path.basename(sys.argv[1]) != sys.argv[1]:
        print("Usage: safe_restore.py backup_NAME.db", file=sys.stderr)
        raise SystemExit(2)
    try:
        raise SystemExit(main(sys.argv[1]))
    except Exception as exc:
        print(f"SAFE_RESTORE_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
