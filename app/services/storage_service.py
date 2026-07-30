from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import get_settings

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
ALLOWED_UPLOAD_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
_FORBIDDEN_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".js", ".vbs", ".msi", ".com", ".scr", ".dll",
}


class UploadRejected(Exception):
    pass


def validate_upload(*, data: bytes, mime_type: str, filename: str) -> None:
    if len(data) == 0:
        raise UploadRejected("Пустой файл")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("Файл превышает допустимый размер (15 МБ)")
    if mime_type not in ALLOWED_UPLOAD_MIME:
        raise UploadRejected(f"Недопустимый тип файла: {mime_type}")
    suffix = Path(filename).suffix.lower()
    if suffix in _FORBIDDEN_EXTENSIONS:
        raise UploadRejected("Исполняемые файлы запрещены")


def contract_dir(contract_id: int) -> Path:
    settings = get_settings()
    path = settings.documents_dir / str(contract_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def upload_dir_for_client(client_uuid: str) -> Path:
    settings = get_settings()
    path = settings.uploads_dir / client_uuid
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(*, data: bytes, mime_type: str, filename: str) -> Path:
    """Persist an uploaded ID document under a random UUID name in a per-upload directory
    so that one client's files are never guessable or reachable from another client's path."""
    validate_upload(data=data, mime_type=mime_type, filename=filename)
    batch_id = str(uuid.uuid4())
    directory = upload_dir_for_client(batch_id)
    suffix = Path(filename).suffix.lower() or ".bin"
    dest = directory / f"{uuid.uuid4()}{suffix}"
    dest.write_bytes(data)
    return dest


def new_document_path(contract_id: int, kind: str, suffix: str) -> Path:
    directory = contract_dir(contract_id)
    return directory / f"{kind}_{uuid.uuid4()}{suffix}"
