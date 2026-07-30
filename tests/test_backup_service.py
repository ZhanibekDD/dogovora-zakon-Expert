from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.services.backup_service import decrypt_backup


def test_encrypted_backup_round_trip(tmp_path: Path) -> None:
    settings = get_settings()
    fernet = Fernet(settings.backup_encryption_key.encode())

    plaintext = b"-- fake pg_dump output --\nCREATE TABLE example();\n"
    encrypted_path = tmp_path / "backup.sql.enc"
    encrypted_path.write_bytes(fernet.encrypt(plaintext))

    output_path = tmp_path / "restored.sql"
    decrypt_backup(encrypted_path, output_path)

    assert output_path.read_bytes() == plaintext


def test_decrypt_backup_rejects_wrong_key(tmp_path: Path, monkeypatch) -> None:
    from cryptography.fernet import Fernet as FernetForOtherKey

    other_key = FernetForOtherKey.generate_key()
    encrypted_path = tmp_path / "backup.sql.enc"
    encrypted_path.write_bytes(FernetForOtherKey(other_key).encrypt(b"data"))

    from app.services import backup_service

    with pytest.raises(backup_service.BackupError):
        decrypt_backup(encrypted_path, tmp_path / "out.sql")
