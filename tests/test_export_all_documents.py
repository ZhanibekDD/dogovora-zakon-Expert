from __future__ import annotations

import zipfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.client import Client
from app.database.models.contract import Contract
from app.database.models.user import User
from app.database.repositories.user_repo import get_role_by_code
from scripts.export_all_documents import collect_files, write_zip


async def _manager(session: AsyncSession) -> User:
    role = await get_role_by_code(session, "manager")
    user = User(telegram_id=88, full_name="Test Manager", role_id=role.id)
    session.add(user)
    await session.flush()
    return user


async def _contract_with_files(session: AsyncSession, tmp_path: Path, *, number: int) -> Contract:
    manager = await _manager(session)
    client = Client(full_name=f"Клиент {number}", iin="010312500019")
    session.add(client)
    await session.flush()

    pdf_path = tmp_path / f"final_v1_{number}.pdf"
    docx_path = tmp_path / f"final_v1_{number}.docx"
    pdf_path.write_bytes(b"%PDF-fake")
    docx_path.write_bytes(b"PK-fake-docx")

    contract = Contract(
        contract_number=number,
        status="approved",
        client_id=client.id,
        manager_id=manager.id,
        amount=10000,
        currency="KZT",
        payment_type="prepayment",
        payment_status="pending",
        pdf_path=str(pdf_path),
        docx_path=str(docx_path),
    )
    session.add(contract)
    await session.flush()
    return contract


async def test_collect_files_includes_pdf_and_docx_for_each_contract(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    await _contract_with_files(db_session, tmp_path, number=1)

    files = await collect_files(db_session)
    assert len(files) == 2
    names = {name for _, name in files}
    assert any(name.endswith(".pdf") for name in names)
    assert any(name.endswith(".docx") for name in names)


async def test_collect_files_skips_contracts_without_documents(db_session: AsyncSession) -> None:
    manager = await _manager(db_session)
    client = Client(full_name="Без договора", iin="010312500019")
    db_session.add(client)
    await db_session.flush()
    contract = Contract(
        contract_number=1,
        status="draft",
        client_id=client.id,
        manager_id=manager.id,
        amount=0,
        currency="KZT",
        payment_type="custom",
        payment_status="pending",
    )
    db_session.add(contract)
    await db_session.flush()

    files = await collect_files(db_session)
    assert files == []


def test_write_zip_produces_archive_with_expected_names(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-fake")
    output_path = tmp_path / "out.zip"

    write_zip([(source, "Договор № 1 Клиент 10000 тенге.pdf")], output_path)

    with zipfile.ZipFile(output_path) as archive:
        assert archive.namelist() == ["Договор № 1 Клиент 10000 тенге.pdf"]
        assert archive.read("Договор № 1 Клиент 10000 тенге.pdf") == b"%PDF-fake"


def test_write_zip_deduplicates_colliding_names(tmp_path: Path) -> None:
    source_a = tmp_path / "a.pdf"
    source_b = tmp_path / "b.pdf"
    source_a.write_bytes(b"A")
    source_b.write_bytes(b"B")
    output_path = tmp_path / "out.zip"

    write_zip([(source_a, "same.pdf"), (source_b, "same.pdf")], output_path)

    with zipfile.ZipFile(output_path) as archive:
        names = archive.namelist()
        assert len(names) == 2
        assert len(set(names)) == 2
