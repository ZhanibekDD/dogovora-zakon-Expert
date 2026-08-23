"""Bundles every previously generated contract document (PDF + DOCX) into one ZIP archive.

Reuses the same human-readable naming as the files sent to employees in Telegram
(quick_contract_service.build_display_filename), so the archive is browsable without opening
each file. Only contracts that actually have a rendered document on disk are included -
abandoned drafts that never got approved are skipped.

Usage: python scripts/export_all_documents.py [output_path.zip]
Defaults to storage/backups/all_documents_<timestamp>.zip if no path is given.
"""
from __future__ import annotations

import asyncio
import datetime
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.database.models.contract import Contract  # noqa: E402
from app.database.session import session_scope  # noqa: E402
from app.services.quick_contract_service import build_display_filename  # noqa: E402


async def collect_files(session: AsyncSession) -> list[tuple[Path, str]]:
    """Returns (path_on_disk, archive_name) pairs for every contract with a rendered document."""
    result = await session.execute(
        select(Contract).options(selectinload(Contract.client)).order_by(Contract.contract_number)
    )
    contracts = result.scalars().all()

    files: list[tuple[Path, str]] = []
    for contract in contracts:
        client = contract.client
        base_name = build_display_filename(
            contract_number=contract.contract_number,
            client_full_name=client.full_name if client else "",
            amount_kzt=int(contract.amount) if contract.amount else None,
        )
        for path_str, ext in ((contract.pdf_path, ".pdf"), (contract.docx_path, ".docx")):
            if not path_str:
                continue
            path = Path(path_str)
            if path.exists():
                files.append((path, f"{base_name}{ext}"))
    return files


def write_zip(files: list[tuple[Path, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seen_names: dict[str, int] = {}
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            # Same contract can legitimately contribute a .pdf and a .docx with the same base
            # name - that's fine (different extensions). Guard only against genuine collisions.
            count = seen_names.get(name, 0)
            seen_names[name] = count + 1
            final_name = name if count == 0 else f"{Path(name).stem} ({count}){Path(name).suffix}"
            archive.write(path, arcname=final_name)


async def main() -> None:
    settings = get_settings()
    if len(sys.argv) > 1:
        output_path = Path(sys.argv[1])
    else:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = settings.backups_dir / f"all_documents_{timestamp}.zip"

    async with session_scope() as session:
        files = await collect_files(session)
    write_zip(files, output_path)
    print(f"Archived {len(files)} file(s) from {len({p for p, _ in files})} document(s) to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
