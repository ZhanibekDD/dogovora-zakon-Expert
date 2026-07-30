from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class BackupError(Exception):
    pass


def _parse_sync_dsn(database_url_sync: str) -> dict:
    parsed = urlparse(database_url_sync.replace("+psycopg2", ""))
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/postgres").lstrip("/"),
    }


async def create_encrypted_backup() -> Path:
    """Runs pg_dump, then encrypts the resulting SQL dump with Fernet (AES-128-CBC + HMAC)
    using BACKUP_ENCRYPTION_KEY. Only the encrypted .sql.enc artifact is kept on disk."""
    settings = get_settings()
    if not settings.backup_encryption_key:
        raise BackupError("BACKUP_ENCRYPTION_KEY не настроен")

    dsn = _parse_sync_dsn(settings.database_url_sync)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    plain_path = settings.backups_dir / f"backup_{timestamp}.sql"
    encrypted_path = settings.backups_dir / f"backup_{timestamp}.sql.enc"

    env = {"PGPASSWORD": dsn["password"]}
    process = await asyncio.create_subprocess_exec(
        "pg_dump",
        "-h", dsn["host"],
        "-p", dsn["port"],
        "-U", dsn["user"],
        "-d", dsn["dbname"],
        "-f", str(plain_path),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error("pg_dump_failed", returncode=process.returncode)
        raise BackupError("pg_dump завершился с ошибкой")

    fernet = Fernet(settings.backup_encryption_key.encode())
    plain_bytes = plain_path.read_bytes()
    encrypted_bytes = fernet.encrypt(plain_bytes)
    encrypted_path.write_bytes(encrypted_bytes)
    plain_path.unlink(missing_ok=True)

    return encrypted_path


def decrypt_backup(encrypted_path: Path, output_path: Path) -> Path:
    settings = get_settings()
    if not settings.backup_encryption_key:
        raise BackupError("BACKUP_ENCRYPTION_KEY не настроен")

    fernet = Fernet(settings.backup_encryption_key.encode())
    try:
        decrypted = fernet.decrypt(encrypted_path.read_bytes())
    except InvalidToken as exc:
        raise BackupError("Неверный ключ шифрования или повреждённый файл резервной копии") from exc

    output_path.write_bytes(decrypted)
    return output_path
