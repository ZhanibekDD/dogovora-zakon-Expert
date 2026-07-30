from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.states.contract_states import SignatureUploadStates
from app.core.config import get_settings
from app.core.security import sha256_bytes
from app.database.models.signature import SignatureAsset
from app.database.models.user import User
from app.database.session import session_scope
from app.services.audit_service import log_action
from app.services.signature_asset_service import (
    AssetKind,
    SignatureAssetError,
    bind_executor_asset,
    prepare_signature_asset,
)

router = Router(name="signature_settings")


@router.message(Command("signature_settings"))
async def signature_settings_start(message: Message, role: str | None, state: FSMContext) -> None:
    if role != "superadmin":
        await message.answer("⛔ Доступно только супер-администратору.")
        return
    await state.set_state(SignatureUploadStates.waiting_for_signature_png)
    await message.answer(
        "Отправьте PNG-файл подписи Исполнителя с прозрачным фоном (как документ, не как фото)."
    )


@router.message(SignatureUploadStates.waiting_for_signature_png)
async def receive_signature_png(message: Message, state: FSMContext, db_user: User) -> None:
    await _store_asset(message, state, db_user, kind="signature")


@router.message(SignatureUploadStates.waiting_for_stamp_png)
async def receive_stamp_png(message: Message, state: FSMContext, db_user: User) -> None:
    await _store_asset(message, state, db_user, kind="stamp")


async def _store_asset(
    message: Message,
    state: FSMContext,
    db_user: User,
    *,
    kind: AssetKind,
) -> None:
    if not message.document or message.document.mime_type != "image/png":
        await message.answer("⛔ Нужен именно PNG-файл, отправленный как документ.")
        return

    settings = get_settings()
    file = await message.bot.get_file(message.document.file_id)
    buffer = await message.bot.download_file(file.file_path)
    data = buffer.read()
    try:
        prepared = prepare_signature_asset(data, kind=kind)
    except SignatureAssetError as exc:
        await message.answer(f"⛔ Не удалось подготовить изображение: {exc}.")
        return

    dest = settings.signature_assets_dir / f"executor_{kind}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_suffix(".tmp")
    temporary.write_bytes(prepared.png_bytes)
    temporary.replace(dest)
    digest = sha256_bytes(prepared.png_bytes)
    bind_executor_asset(
        settings.signature_assets_dir,
        kind=kind,
        sha256=digest,
        identifier_label=settings.executor_identifier_label,
        identifier=settings.executor_identifier,
    )

    async with session_scope() as session:
        session.add(
            SignatureAsset(kind=kind, file_path=str(dest), sha256=digest, uploaded_by_id=db_user.id)
        )
        await log_action(
            session,
            action=f"{kind}_asset_uploaded",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            details={
                "sha256": digest,
                "executor_identifier_label": settings.executor_identifier_label,
                "executor_identifier": settings.executor_identifier,
            },
        )

    if kind == "signature":
        await state.set_state(SignatureUploadStates.waiting_for_stamp_png)
        await message.answer(
            f"✅ Подпись сохранена (SHA-256: {digest[:16]}...).\n\n"
            f"Обработанный размер: {prepared.width_px}×{prepared.height_px} px; "
            f"в договоре: {settings.executor_signature_width_mm:g} мм по ширине.\n"
            "Система автоматически совместит её с линией подписанта и печатью.\n\n"
            "Теперь отправьте PNG-файл печати ТОО с прозрачным фоном."
        )
    else:
        await state.clear()
        await message.answer(
            f"✅ Печать сохранена (SHA-256: {digest[:16]}...).\n"
            f"Обработанный размер: {prepared.width_px}×{prepared.height_px} px; "
            f"в договоре: {settings.executor_stamp_diameter_mm:g} мм.\n"
            "Подпись, линия и печать будут собраны в единый блок A4. Настройка завершена."
        )
