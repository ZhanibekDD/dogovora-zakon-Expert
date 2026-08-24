"""Force a specific already-approved contract to regenerate its DOCX/PDF from the current
master template, without touching any of its stored terms (amount, payment type, phone, etc).

This exists for the case where a template/branding bug (wrong logo, clipped seal, ...) shipped
into a contract's already-rendered files: fixing the template code alone does not change a file
that was already written to disk, so the affected contract needs to be explicitly reissued once
the fix is deployed. It follows the exact same convention as
quick_contract_service.revise_contract_from_reply (bump contract.version, then re-run
contract_service.approve_contract_documents so the file is written to a fresh
final_v{version}.{docx,pdf} path) but skips the natural-language edit step entirely, since here
nothing about the contract's terms is changing - only the rendering.

Refuses to touch a contract that has already been sent for signature or signed, for the same
reason revise_contract_from_reply does: at that point the client is looking at a specific PDF,
and silently swapping its content would be wrong.

Usage: python scripts/reissue_contract.py <contract_number> [approved_by_telegram_id]
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.database.models.contract import Contract  # noqa: E402
from app.database.models.user import User  # noqa: E402
from app.database.session import session_scope  # noqa: E402
from app.services import contract_service  # noqa: E402


class ContractNotReissuableError(RuntimeError):
    pass


async def reissue_contract(
    session: AsyncSession, *, contract_number: int, approved_by_telegram_id: int | None = None
) -> tuple[str, str]:
    result = await session.execute(
        select(Contract)
        .options(selectinload(Contract.client))
        .where(Contract.contract_number == contract_number)
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise ContractNotReissuableError(f"Договор №{contract_number} не найден")
    if contract.status in ("signed", "sent_for_signature"):
        raise ContractNotReissuableError(
            f"Договор №{contract_number} уже отправлен клиенту на подписание или подписан; "
            "перевыпуск невозможен."
        )

    approved_by_id = contract.approved_by_id
    if approved_by_telegram_id is not None:
        user_result = await session.execute(
            select(User).where(User.telegram_id == approved_by_telegram_id)
        )
        user = user_result.scalar_one_or_none()
        if user is not None:
            approved_by_id = user.id
    if approved_by_id is None:
        raise ContractNotReissuableError(
            f"Не удалось определить approved_by_id для договора №{contract_number}; "
            "передайте approved_by_telegram_id явно."
        )

    contract.version += 1
    return await contract_service.approve_contract_documents(
        session, contract, contract.client, approved_by_id=approved_by_id
    )


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/reissue_contract.py <contract_number> [approved_by_telegram_id]")
        raise SystemExit(2)
    contract_number = int(sys.argv[1])
    approved_by_telegram_id = int(sys.argv[2]) if len(sys.argv) > 2 else None

    async with session_scope() as session:
        docx_path, pdf_path = await reissue_contract(
            session, contract_number=contract_number, approved_by_telegram_id=approved_by_telegram_id
        )
    print(f"Reissued contract №{contract_number}")
    print(f"docx: {docx_path}")
    print(f"pdf:  {pdf_path}")


if __name__ == "__main__":
    asyncio.run(main())
