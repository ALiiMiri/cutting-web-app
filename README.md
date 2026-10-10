# Database backups (offsite mirror)

Automatic daily backups of the Cutting Web App database.
This branch is machine-managed by the server and force-pushed each night.
Do NOT edit or merge it into `main`.

Each file `backup_YYYY-MM-DD.db` is a full SQLite snapshot.
The last 30 days are kept.
