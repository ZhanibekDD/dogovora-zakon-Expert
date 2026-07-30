from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Only the hash is persisted."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def verify_token(raw_token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_token(raw_token), stored_hash)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
