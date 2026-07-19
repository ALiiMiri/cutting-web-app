import os
from pathlib import Path

# Optional dependency: python-dotenv
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

# Load environment variables from .env file
if load_dotenv:
    load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _absolute_path(value, default):
    path = Path(value or default).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path.resolve())


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default-dev-key-change-in-prod")
    DB_NAME = _absolute_path(os.getenv("CUTTING_DB_PATH"), "cutting_web_data.db")
    BACKUP_DIR = _absolute_path(os.getenv("CUTTING_BACKUP_DIR"), "backups")
    BACKUP_MIRROR_DIR = (
        _absolute_path(os.getenv("CUTTING_BACKUP_MIRROR_DIR"), "backups-mirror")
        if os.getenv("CUTTING_BACKUP_MIRROR_DIR")
        else None
    )
    MAINTENANCE_FILE = _absolute_path(
        os.getenv("CUTTING_MAINTENANCE_FILE"), ".maintenance.json"
    )
    BACKUP_RETENTION_DAYS = int(os.getenv("CUTTING_BACKUP_RETENTION_DAYS", "30"))
