#!/usr/bin/env python3
import backup_manager
from config import Config


def main():
    success, result = backup_manager.create_backup(
        reason="scheduled_daily", user="system", metadata={"retention_days": Config.BACKUP_RETENTION_DAYS}
    )
    if not success:
        raise RuntimeError(result)
    deleted = backup_manager.cleanup_old_backups(Config.BACKUP_RETENTION_DAYS)
    print(f"BACKUP_OK path={result} deleted_old={deleted} mirror={Config.BACKUP_MIRROR_DIR or 'not-configured'}")


if __name__ == "__main__":
    main()
