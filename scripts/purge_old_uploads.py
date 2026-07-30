"""Deletes source ID-document uploads older than SOURCE_FILE_RETENTION_DAYS.

Intended to be run on a daily schedule (cron / Task Scheduler). The uploads directory only
ever contains the *original* ID photos/PDFs used for OpenAI extraction - the generated
contract DOCX/PDF files (which do not need the same aggressive retention policy) live under
STORAGE_PATH/documents and are untouched by this script.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402

logger = get_logger(__name__)


def main() -> None:
    configure_logging()
    settings = get_settings()
    cutoff = time.time() - settings.source_file_retention_days * 86400
    deleted = 0

    for path in settings.uploads_dir.rglob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            deleted += 1

    for directory in sorted(settings.uploads_dir.glob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()

    logger.info("uploads_purged", deleted_files=deleted, retention_days=settings.source_file_retention_days)
    print(f"Deleted {deleted} file(s) older than {settings.source_file_retention_days} days")


if __name__ == "__main__":
    main()
