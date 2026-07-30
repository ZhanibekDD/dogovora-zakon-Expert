"""Deletes a client's personal data on request (right to erasure).

Removes the client's row, their contracts' generated documents from disk, and their client
signature images. Contract financial/audit records are anonymized rather than deleted outright
so the numbering ledger and audit trail stay intact for accounting/legal purposes.

Usage: python scripts/delete_client_data.py <client_id>
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.database.models.client import Client  # noqa: E402
from app.database.models.contract import Contract  # noqa: E402
from app.database.session import session_scope  # noqa: E402
from app.services.audit_service import log_action  # noqa: E402


async def delete_client_data(client_id: int) -> None:
    async with session_scope() as session:
        client = await session.get(Client, client_id)
        if client is None:
            print(f"Client {client_id} not found")
            return

        result = await session.execute(select(Contract).where(Contract.client_id == client_id))
        contracts = result.scalars().all()

        for contract in contracts:
            contract_dir: Path | None = None
            for path_str in (contract.docx_path, contract.pdf_path):
                if path_str:
                    path = Path(path_str)
                    contract_dir = path.parent
                    if path.exists():
                        path.unlink()
            if contract_dir and contract_dir.exists() and not any(contract_dir.iterdir()):
                shutil.rmtree(contract_dir, ignore_errors=True)

        client.full_name = "УДАЛЕНО ПО ЗАПРОСУ"
        client.last_name = None
        client.first_name = None
        client.middle_name = None
        client.iin = None
        client.phone = None
        client.address = None
        client.document_number = None

        await log_action(
            session, action="client_data_erased", entity_type="client", entity_id=client_id
        )

    print(f"Personal data for client {client_id} erased; {len(contracts)} contract file(s) removed.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        print("Usage: python scripts/delete_client_data.py <client_id>")
        sys.exit(1)
    asyncio.run(delete_client_data(int(sys.argv[1])))
