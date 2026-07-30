"""CLI wrapper: create an encrypted database backup. Usage: python scripts/backup_db.py"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.backup_service import create_encrypted_backup  # noqa: E402


async def main() -> None:
    path = await create_encrypted_backup()
    print(f"Backup written to {path}")


if __name__ == "__main__":
    asyncio.run(main())
