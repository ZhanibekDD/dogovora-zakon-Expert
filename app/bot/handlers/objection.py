from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from app.bot.keyboards.main_menu import cancel_keyboard
from app.bot.states.objection_states import ObjectionStates
from app.core.config import get_settings
from app.database.models.user import User
from app.database.session import session_scope
from app.schemas.objection import NotarialWritExtraction
from app.services import message_link_service, objection_service, pdf_service
from app.services.audit_service import log_action
from app.services.openai_service import OpenAIService
from app.services.storage_service import UploadRejected, save_upload
from app.utils.masking import mask_iin

router = Router(name="objection")
openai_service = OpenAIService()

OBJECTION_PENDING_NAMESPACE = "objection"

INSTRUCTION_TEXT = (
    "Отправьте фото или PDF исполнительной надписи нотариуса, и в подписи к файлу укажите "
    "телефон клиента (и, если нужно, email), например:\n"
    '"+7 701 987 6543"'
)


def _is_allowed(telegram_id: int | None) -> bool:
    if telegram_id is None:
        return False
    return telegram_id in get_settings().objection_allowed_ids


def _extract_file_info(message: Message) -> tuple[str, str, str]:
    if message.photo:
        return message.photo[-1].file_id, "writ_photo.jpg", "image/jpeg"
    document = message.document
    return (
        document.file_id,
        document.file_name or "writ_document",
        document.mime_type or "application/octet-stream",
    )


@router.message(Command("objection"))
@router.message(F.text == "📝 Сформировать возражение")
async def cmd_objection_start(message: Message, state: FSMContext) -> None:
    if not _is_allowed(message.from_user.id if message.from_user else None):
        await message.answer("⛔ Эта функция недоступна для вашего аккаунта.")
        return
    await state.clear()
    await state.set_state(ObjectionStates.waiting_for_document)
    await message.answer(INSTRUCTION_TEXT, reply_markup=cancel_keyboard(), parse_mode=None)


async def _send_objection_files(
    message: Message, writ: NotarialWritExtraction, client_phone: str, docx_path: str, pdf_path: str
) -> None:
    base_name = objection_service.build_display_filename(
        debtor_last_name=writ.debtor_last_name or "", client_phone=client_phone
    )
    try:
        await message.answer_document(FSInputFile(docx_path, filename=f"{base_name}.docx"))
        await message.answer_document(FSInputFile(pdf_path, filename=f"{base_name}.pdf"))
    except Exception as exc:  # noqa: BLE001
        await message.answer(
            f"⚠️ Возражение сформировано, но не удалось отправить файлы: {exc}",
            parse_mode=None,
        )
        raise


def _summary_text(writ: NotarialWritExtraction, client_phone: str) -> str:
    return (
        "✅ Возражение сформировано.\n\n"
        f"Должник: {writ.debtor_full_name}\n"
        f"ИИН: {mask_iin(writ.debtor_iin)}\n"
        f"Взыскатель: {writ.creditor_name_nominative or '—'}\n"
        f"Сумма: {objection_service.format_amount_tenge(writ.total_amount)}\n"
        f"Телефон: {client_phone}\n\n"
        "Файлы приложены ниже."
    )


@router.message(StateFilter(ObjectionStates.waiting_for_document), F.photo | F.document)
async def handle_objection_document(message: Message, state: FSMContext, db_user: User) -> None:
    if not _is_allowed(message.from_user.id if message.from_user else None):
        await message.answer("⛔ Эта функция недоступна для вашего аккаунта.")
        await state.clear()
        return

    file_id, filename, mime_type = _extract_file_info(message)
    file = await message.bot.get_file(file_id)
    buffer = await message.bot.download_file(file.file_path)
    data = buffer.read()

    try:
        save_upload(data=data, mime_type=mime_type, filename=filename)
    except UploadRejected as exc:
        await message.answer(f"⛔ {exc}. Попробуйте загрузить другой файл.")
        return

    if mime_type == "application/pdf":
        pages_png = pdf_service.rasterize_pdf_pages(data, max_pages=2)
        if not pages_png:
            await message.answer("⛔ Не удалось прочитать PDF-файл исполнительной надписи.")
            return
        primary_bytes, primary_mime = pages_png[0], "image/png"
        extra_images = [(png, "image/png") for png in pages_png[1:]]
    else:
        primary_bytes, primary_mime = data, mime_type
        extra_images = None

    status = await message.answer("⏳ Формирую возражение...")
    caption = message.caption or ""

    outcome = await objection_service.process_objection_message(
        openai_service,
        image_bytes=primary_bytes,
        mime_type=primary_mime,
        caption=caption,
        extra_images=extra_images,
    )

    if outcome.missing_fields:
        await message_link_service.save_pending_clarification(
            message.chat.id, outcome.pending_payload, namespace=OBJECTION_PENDING_NAMESPACE
        )
        await state.set_state(ObjectionStates.waiting_for_clarification)
        await status.edit_text(
            objection_service.build_clarification_message(outcome.missing_fields), parse_mode=None
        )
        return

    await state.clear()
    assert outcome.writ is not None and outcome.docx_path is not None and outcome.pdf_path is not None
    client_phone = outcome.client_phone or ""
    await status.edit_text(_summary_text(outcome.writ, client_phone), parse_mode=None)
    await _send_objection_files(message, outcome.writ, client_phone, outcome.docx_path, outcome.pdf_path)

    async with session_scope() as session:
        await log_action(
            session,
            action="objection_generated",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            details={"debtor_iin": mask_iin(outcome.writ.debtor_iin)},
        )


@router.message(StateFilter(ObjectionStates.waiting_for_clarification), F.text)
async def handle_objection_clarification(message: Message, state: FSMContext, db_user: User) -> None:
    if not _is_allowed(message.from_user.id if message.from_user else None):
        await message.answer("⛔ Эта функция недоступна для вашего аккаунта.")
        await state.clear()
        return

    pending = await message_link_service.load_pending_clarification(
        message.chat.id, namespace=OBJECTION_PENDING_NAMESPACE
    )
    if pending is None:
        await state.clear()
        await message.answer("Время ожидания ответа истекло. Начните заново: /objection")
        return

    status = await message.answer("⏳ Обрабатываю ответ...")
    outcome = await objection_service.merge_objection_clarification(
        openai_service, pending=pending, answer_text=message.text
    )

    if outcome.missing_fields:
        await message_link_service.save_pending_clarification(
            message.chat.id, outcome.pending_payload, namespace=OBJECTION_PENDING_NAMESPACE
        )
        await status.edit_text(
            objection_service.build_clarification_message(outcome.missing_fields), parse_mode=None
        )
        return

    await message_link_service.clear_pending_clarification(
        message.chat.id, namespace=OBJECTION_PENDING_NAMESPACE
    )
    await state.clear()
    assert outcome.writ is not None and outcome.docx_path is not None and outcome.pdf_path is not None
    client_phone = outcome.client_phone or ""

    await status.edit_text(_summary_text(outcome.writ, client_phone), parse_mode=None)
    await _send_objection_files(message, outcome.writ, client_phone, outcome.docx_path, outcome.pdf_path)

    async with session_scope() as session:
        await log_action(
            session,
            action="objection_generated",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            details={"debtor_iin": mask_iin(outcome.writ.debtor_iin)},
        )
