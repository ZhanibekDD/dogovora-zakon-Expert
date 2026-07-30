"""CLI wrapper: decrypt a backup and restore it with psql.

Usage: python scripts/restore_db.py backup_20260713_120000.sql.enc
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.services.backup_service import decrypt_backup  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/restore_db.py <backup_file.sql.enc>")
        sys.exit(1)

    settings = get_settings()
    encrypted_path = Path(sys.argv[1])
    if not encrypted_path.is_absolute():
        encrypted_path = settings.backups_dir / encrypted_path

    with tempfile.TemporaryDirectory() as tmp_dir:
        plain_path = Path(tmp_dir) / "restore.sql"
        decrypt_backup(encrypted_path, plain_path)

        parsed = urlparse(settings.database_url_sync.replace("+psycopg2", ""))
        env = {"PGPASSWORD": parsed.password or ""}
        result = subprocess.run(
            [
                "psql",
                "-h", parsed.hostname or "localhost",
                "-p", str(parsed.port or 5432),
                "-U", parsed.username or "postgres",
                "-d", (parsed.path or "/postgres").lstrip("/"),
                "-f", str(plain_path),
            ],
            env=env,
        )
        if result.returncode != 0:
            print("Restore failed")
            sys.exit(1)

    print("Restore completed successfully")


if __name__ == "__main__":
    main()
