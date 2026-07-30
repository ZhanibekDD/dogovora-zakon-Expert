from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import or_, select

from app.bot.keyboards import reply_menu
from app.bot.states.contract_states import FindContractStates
from app.core.constants import TEMPLATE_CODES
from app.database.models.client import Client
from app.database.models.contract import Contract
from app.database.models.user import User
from app.database.session import session_scope
from app.utils.masking import mask_iin

router = Router(name="contracts_list")

STATUS_LABELS = {
    "draft": "Черновик",
    "review": "На проверке",
    "approved": "Утверждён",
    "sent_for_signature": "Отправлен на подписание",
    "signed": "Подписан",
    "cancelled": "Отменён",
    "completed": "Завершён",
    "payment_pending": "Ожидает оплаты",
    "paid": "Оплачен",
}


def _format_contract_line(contract: Contract, client: Client) -> str:
    status = STATUS_LABELS.get(contract.status, contract.status)
    return (
        f"№ {contract.contract_number} — {client.full_name} ({mask_iin(client.iin)}) — "
        f"{contract.amount} тенге — {status}"
    )


@router.message(Command("contracts"))
@router.message(F.text == reply_menu.CONTRACTS)
async def list_contracts(message: Message, role: str | None, db_user: User) -> None:
    async with session_scope() as session:
        query = select(Contract).order_by(Contract.contract_number.desc()).limit(20)
        if role == "manager":
            query = query.where(Contract.manager_id == db_user.id)
        result = await session.execute(query)
        contracts = result.scalars().all()

        lines = []
        for contract in contracts:
            client = await session.get(Client, contract.client_id)
            lines.append(_format_contract_line(contract, client))

    text = "\n".join(lines) if lines else "Договоров пока нет."
    await message.answer(text)


@router.message(Command("find_contract"))
@router.message(F.text == reply_menu.FIND_CONTRACT)
async def find_contract_start(message: Message, state: FSMContext) -> None:
    await state.set_state(FindContractStates.waiting_for_query)
    await message.answer("Введите номер договора или ФИО клиента для поиска:")


@router.message(FindContractStates.waiting_for_query)
async def find_contract_query(message: Message, state: FSMContext) -> None:
    query_text = message.text.strip()
    async with session_scope() as session:
        conditions = [Client.full_name.ilike(f"%{query_text}%")]
        if query_text.isdigit():
            conditions.append(Contract.contract_number == int(query_text))

        result = await session.execute(
            select(Contract, Client)
            .join(Client, Contract.client_id == Client.id)
            .where(or_(*conditions))
            .order_by(Contract.contract_number.desc())
            .limit(10)
        )
        rows = result.all()

    if not rows:
        await message.answer("Ничего не найдено.")
    else:
        lines = [_format_contract_line(contract, client) for contract, client in rows]
        await message.answer("\n".join(lines))
    await state.clear()


@router.message(Command("templates"))
@router.message(F.text == reply_menu.TEMPLATES)
async def list_templates(message: Message) -> None:
    lines = ["<b>Утверждённые типы договоров:</b>"]
    lines += [f"• {name}" for name in TEMPLATE_CODES.values()]
    await message.answer("\n".join(lines), parse_mode="HTML")
