from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from sqlalchemy import select

from app.bot.handlers import (
    backup,
    contracts_list,
    draft_actions,
    employees,
    objection,
    quick_contract,
    signature_settings,
    start,
)
from app.bot.handlers import help as help_handler
from app.bot.handlers import settings as settings_handler
from app.bot.middlewares.audit import AuditMiddleware
from app.bot.middlewares.auth import AuthMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database.models.user import Employee, Role, User
from app.database.session import session_scope
from app.services.crm_pull_worker import run_crm_pull_worker

logger = get_logger(__name__)

BOT_COMMANDS = [
    ("start", "Главное меню"),
    ("new_contract", "Новый договор (удостоверение или ФИО + ИИН)"),
    ("contracts", "Мои договоры"),
    ("find_contract", "Найти договор"),
    ("templates", "Утверждённые шаблоны"),
    ("settings", "Настройки"),
    ("employees", "Управление сотрудниками"),
    ("signature_settings", "Загрузка подписи и печати"),
    ("backup", "Резервное копирование"),
    ("help", "Справка"),
]


async def ensure_roles_seeded(session) -> None:
    result = await session.execute(select(Role))
    if result.scalars().first() is not None:
        return
    for code, name in [
        ("superadmin", "Супер-администратор"),
        ("admin", "Администратор"),
        ("manager", "Менеджер"),
        ("client", "Клиент"),
    ]:
        session.add(Role(code=code, name=name))
    await session.flush()


async def ensure_superadmins() -> None:
    """Auto-provision every Telegram ID in SUPERADMIN_TELEGRAM_IDS as an active superadmin."""
    settings = get_settings()
    async with session_scope() as session:
        await ensure_roles_seeded(session)
        result = await session.execute(select(Role).where(Role.code == "superadmin"))
        superadmin_role = result.scalar_one()

        for telegram_id in settings.superadmin_ids:
            user_result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = user_result.scalar_one_or_none()
            if user is None:
                user = User(
                    telegram_id=telegram_id,
                    full_name=f"Superadmin {telegram_id}",
                    role_id=superadmin_role.id,
                    is_active=True,
                )
                session.add(user)
                await session.flush()
            elif user.role_id != superadmin_role.id:
                user.role_id = superadmin_role.id

            employee_result = await session.execute(select(Employee).where(Employee.user_id == user.id))
            if employee_result.scalar_one_or_none() is None:
                session.add(Employee(user_id=user.id))


def build_dispatcher() -> Dispatcher:
    settings = get_settings()
    storage = RedisStorage.from_url(settings.redis_url)
    dispatcher = Dispatcher(storage=storage)

    dispatcher.message.middleware(AuthMiddleware())
    dispatcher.callback_query.middleware(AuthMiddleware())
    dispatcher.message.middleware(AuditMiddleware())
    dispatcher.callback_query.middleware(AuditMiddleware())

    dispatcher.include_router(start.router)
    dispatcher.include_router(help_handler.router)
    dispatcher.include_router(objection.router)
    dispatcher.include_router(quick_contract.router)
    dispatcher.include_router(draft_actions.router)
    dispatcher.include_router(contracts_list.router)
    dispatcher.include_router(settings_handler.router)
    dispatcher.include_router(employees.router)
    dispatcher.include_router(signature_settings.router)
    dispatcher.include_router(backup.router)
    return dispatcher


async def main() -> None:
    configure_logging()
    settings = get_settings()
    await ensure_superadmins()

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = build_dispatcher()

    from aiogram.types import BotCommand

    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in BOT_COMMANDS])

    # CRM contract creation is independent from Telegram transport. The same long-running
    # process polls the private CRM queue outbound over HTTPS; no public generator port is
    # required. If CRM_SYNC_URL / CRM_INTEGRATION_KEY are not configured, this task exits
    # immediately and Telegram behavior stays unchanged.
    crm_pull_task = asyncio.create_task(run_crm_pull_worker(), name="crm-pull-worker")
    logger.info("bot_starting")
    try:
        await dispatcher.start_polling(bot)
    finally:
        if not crm_pull_task.done():
            crm_pull_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await crm_pull_task


if __name__ == "__main__":
    asyncio.run(main())
