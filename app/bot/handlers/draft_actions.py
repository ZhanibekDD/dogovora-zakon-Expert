from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.database.models.contract import Contract
from app.database.models.user import User
from app.database.session import session_scope
from app.services import signing_service
from app.services.audit_service import log_action

router = Router(name="draft_actions")

APPROVER_ROLES = {"admin", "superadmin"}


@router.callback_query(F.data.startswith("contract:send_signing:"))
async def send_signing_link(callback: CallbackQuery, role: str | None, db_user: User) -> None:
    if role not in APPROVER_ROLES:
        await callback.answer(
            "⛔ Отправлять договор на подписание могут только администраторы.", show_alert=True
        )
        return

    contract_id = int(callback.data.split(":")[-1])
    async with session_scope() as session:
        contract = await session.get(Contract, contract_id)
        if contract is None or contract.status != "approved":
            await callback.answer("Договор должен быть утверждён перед отправкой клиенту.", show_alert=True)
            return
        raw_token = await signing_service.create_signing_token(session, contract, created_by_id=db_user.id)
        url = signing_service.build_signing_url(contract_id, raw_token)
        await log_action(
            session,
            action="signing_link_created",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            entity_type="contract",
            entity_id=contract_id,
        )

    await callback.message.answer(
        "🔗 Одноразовая ссылка для подписания клиентом (действительна 24 часа):\n"
        f"{url}\n\nПерешлите её клиенту в WhatsApp или Telegram.",
        parse_mode=None,
    )
    await callback.answer()
