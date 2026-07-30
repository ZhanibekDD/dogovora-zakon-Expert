from __future__ import annotations

import pytest

from app.services.storage_service import UploadRejected, save_upload, validate_upload


def test_rejects_empty_file() -> None:
    with pytest.raises(UploadRejected):
        validate_upload(data=b"", mime_type="image/jpeg", filename="id.jpg")


def test_rejects_oversized_file() -> None:
    big_data = b"0" * (16 * 1024 * 1024)
    with pytest.raises(UploadRejected):
        validate_upload(data=big_data, mime_type="image/jpeg", filename="id.jpg")


def test_rejects_disallowed_mime_type() -> None:
    with pytest.raises(UploadRejected):
        validate_upload(data=b"data", mime_type="application/zip", filename="id.zip")


def test_rejects_executable_extension() -> None:
    with pytest.raises(UploadRejected):
        validate_upload(data=b"MZ\x90\x00", mime_type="image/jpeg", filename="virus.exe")


def test_accepts_valid_jpeg() -> None:
    validate_upload(data=b"\xff\xd8\xff data", mime_type="image/jpeg", filename="id.jpg")


def test_save_upload_uses_random_uuid_path() -> None:
    path1 = save_upload(data=b"\xff\xd8\xff a", mime_type="image/jpeg", filename="id.jpg")
    path2 = save_upload(data=b"\xff\xd8\xff a", mime_type="image/jpeg", filename="id.jpg")
    assert path1 != path2
    assert path1.parent != path2.parent  # different clients never share an upload directory
