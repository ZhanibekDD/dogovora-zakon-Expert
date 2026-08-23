from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.client import Client
from app.database.models.contract import Contract
from app.database.models.user import User
from app.database.repositories.user_repo import get_role_by_code
from scripts.export_clients_xlsx import HEADERS, fetch_rows, write_workbook


async def _manager(session: AsyncSession) -> User:
    role = await get_role_by_code(session, "manager")
    user = User(telegram_id=77, full_name="Test Manager", role_id=role.id)
    session.add(user)
    await session.flush()
    return user


async def test_fetch_rows_includes_client_and_contract_fields(db_session: AsyncSession) -> None:
    manager = await _manager(db_session)
    client = Client(
        full_name="Тестов Тест Тестович",
        iin="010312500019",
        phone="+7 701 234 5678",
        address="г. Талдыкорган",
    )
    db_session.add(client)
    await db_session.flush()

    contract = Contract(
        contract_number=1,
        status="approved",
        client_id=client.id,
        manager_id=manager.id,
        amount=50000,
        currency="KZT",
        payment_type="after_result",
        payment_status="pending",
        service_data={"service_type": "снятие ареста от ЧСИ"},
    )
    db_session.add(contract)
    await db_session.flush()

    rows = await fetch_rows(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == 1  # contract_number
    assert row[2] == "Тестов Тест Тестович"
    assert row[3] == "010312500019"
    assert row[4] == "+7 701 234 5678"
    assert row[6] == "снятие ареста от ЧСИ"
    assert row[7] == 50000.0
    assert row[9] == "после результата"  # payment_type label


async def test_fetch_rows_empty_when_no_contracts(db_session: AsyncSession) -> None:
    rows = await fetch_rows(db_session)
    assert rows == []


def test_write_workbook_produces_readable_xlsx_with_header(tmp_path: Path) -> None:
    output_path = tmp_path / "export.xlsx"
    rows = [(1, "01.01.2026", "Иванов Иван", "010312500019", "+7 700 000 0000", "адрес", "услуга", 10000.0, "KZT", "предоплата", "pending", "approved")]

    write_workbook(rows, output_path)

    workbook = load_workbook(str(output_path))
    sheet = workbook.active
    assert [cell.value for cell in sheet[1]] == HEADERS
    assert [cell.value for cell in sheet[2]] == list(rows[0])
