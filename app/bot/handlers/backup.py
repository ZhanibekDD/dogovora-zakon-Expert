from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from app.database.models.user import User
from app.database.session import session_scope
from app.services.audit_service import log_action
from app.services.backup_service import create_encrypted_backup

router = Router(name="backup")


@router.message(Command("backup"))
async def run_backup(message: Message, role: str | None, db_user: User) -> None:
    if role != "superadmin":
        await message.answer("⛔ Доступно только супер-администратору.")
        return

    status = await message.answer("⏳ Создаю резервную копию базы данных...")
    try:
        backup_path = await create_encrypted_backup()
    except Exception as exc:  # noqa: BLE001
        await status.edit_text(f"⛔ Не удалось создать резервную копию: {exc}")
        return

    async with session_scope() as session:
        await log_action(
            session,
            action="backup_created",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            details={"path": str(backup_path)},
        )

    await status.edit_text("✅ Резервная копия создана и зашифрована.")
    await message.answer_document(FSInputFile(backup_path), caption="Зашифрованная резервная копия БД")
