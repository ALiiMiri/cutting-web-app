import json
import os
from datetime import datetime, timezone

from config import Config


def enable_maintenance(reason, details=None):
    payload = {
        "reason": str(reason),
        "details": details or {},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }
    temporary = f"{Config.MAINTENANCE_FILE}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, Config.MAINTENANCE_FILE)
    return payload


def disable_maintenance():
    try:
        os.remove(Config.MAINTENANCE_FILE)
    except FileNotFoundError:
        pass


def maintenance_status():
    try:
        with open(Config.MAINTENANCE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
