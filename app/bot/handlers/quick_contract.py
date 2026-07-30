from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.bot.keyboards import reply_menu
from app.bot.keyboards.main_menu import cancel_keyboard
from app.bot.keyboards.quick_draft import quick_draft_keyboard
from app.bot.states.contract_states import QuickContractStates
from app.core.config import get_settings
from app.database.models.client import Client
from app.database.models.contract import Contract
from app.database.models.user import User
from app.database.repositories.counter_repo import release_last_number_if_matches
from app.database.session import session_scope
from app.schemas.conditions import ContractConditions
from app.services import message_link_service, pdf_service, quick_contract_service
from app.services.audit_service import log_action
from app.services.contract_service import (
    approve_contract_documents,
    get_or_create_active_template,
)
from app.services.openai_service import OpenAIService
from app.services.storage_service import UploadRejected, save_upload

router = Router(name="quick_contract")
openai_service = OpenAIService()

EMPLOYEE_ROLES = {"manager", "admin", "superadmin"}

QUICK_MODE_KEYWORDS = [
    "договор", "арест", "чси", "нотариус", "исполнительн", "судебн", "график",
    "запрет на выезд", "штраф", "оплата сразу", "оплата после", "предоплата",
    "мировое", "медиатив",
]
_PRICE_LIKE_RE = re.compile(r"\d{4,}|\d+\s*[кk]\b", re.IGNORECASE)

QUICK_INSTRUCTION_TEXT = (
    "Отправьте удостоверение личности клиента и в подписи к фотографии укажите:\n"
    "— услугу;\n"
    "— стоимость;\n"
    "— порядок оплаты;\n"
    "— телефон.\n\n"
    'Пример: "Снятие ареста от ЧСИ, 50 000 тенге, оплата после, +7 700 000 0000"'
)


def _looks_like_quick_contract_request(caption: str | None) -> bool:
    if not caption:
        return False
    lowered = caption.lower()
    if any(keyword in lowered for keyword in QUICK_MODE_KEYWORDS):
        return True
    return bool(_PRICE_LIKE_RE.search(caption))


def _extract_file_info(message: Message) -> tuple[str, str, str]:
    if message.photo:
        return message.photo[-1].file_id, "id_photo.jpg", "image/jpeg"
    document = message.document
    return (
        document.file_id,
        document.file_name or "id_document",
        document.mime_type or "application/octet-stream",
    )


@router.message(Command("new_contract"))
@router.message(F.text == reply_menu.NEW_CONTRACT)
async def cmd_new_contract_quick(message: Message, state: FSMContext, role: str | None) -> None:
    if role not in EMPLOYEE_ROLES:
        await message.answer("⛔ Создавать договоры могут только менеджеры и администраторы.")
        return
    await state.clear()
    await state.set_state(QuickContractStates.waiting_for_document)
    await message.answer(QUICK_INSTRUCTION_TEXT, reply_markup=cancel_keyboard())


async def _send_draft_files(
    message: Message, contract: Contract, client: Client, docx_path: str, pdf_path: str
) -> None:
    """Send the DOCX + PDF with the compact review keyboard attached to the PDF message.

    Files are sent under a human-readable display name ("Договор оказания услуг № 9
    Турсынбаев Досжан 20000 тенге.docx") built from the contract - the file's actual path on
    disk (final_v{version}.docx/pdf) is untouched, only what Telegram shows the employee.

    Deliberately wrapped: if file delivery fails for any reason (bad file, Telegram API
    hiccup), the employee gets an explicit error instead of the handler silently dying after
    the status message was already edited to a 'success' text - which would look exactly like
    "the contract was created but the buttons never showed up".
    """
    conditions = ContractConditions.model_validate(contract.service_data)
    base_name = quick_contract_service.build_display_filename(
        contract_number=contract.contract_number,
        client_full_name=client.full_name,
        amount_kzt=int(conditions.amount_kzt or contract.amount or 0),
    )
    try:
        sent_docx = await message.answer_document(
            FSInputFile(docx_path, filename=f"{base_name}.docx")
        )
        sent_pdf = await message.answer_document(
            FSInputFile(pdf_path, filename=f"{base_name}.pdf"),
            reply_markup=quick_draft_keyboard(contract.id),
        )
    except Exception as exc:  # noqa: BLE001
        await message.answer(
            f"⚠️ Договор создан (№ см. выше), но не удалось отправить файлы: {exc}\n"
            "Проверьте /contracts или обратитесь к администратору.",
            parse_mode=None,
        )
        raise
    await message_link_service.link_message_to_contract(message.chat.id, sent_pdf.message_id, contract.id)
    await message_link_service.link_message_to_contract(message.chat.id, sent_docx.message_id, contract.id)


async def _process_document_message(message: Message, state: FSMContext, db_user: User) -> None:
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
            await message.answer("⛔ Не удалось прочитать PDF-файл удостоверения.")
            return
        primary_bytes, primary_mime = pages_png[0], "image/png"
        extra_images = [(png, "image/png") for png in pages_png[1:]]
    else:
        primary_bytes, primary_mime = data, mime_type
        extra_images = None

    status = await message.answer("⏳ Формирую договор...")
    caption = message.caption or ""

    async with session_scope() as session:
        outcome = await quick_contract_service.process_quick_contract_message(
            session,
            openai_service=openai_service,
            image_bytes=primary_bytes,
            mime_type=primary_mime,
            caption=caption,
            manager_id=db_user.id,
            extra_images=extra_images,
        )

        if outcome.missing_fields:
            await message_link_service.save_pending_clarification(
                message.chat.id, outcome.pending_payload
            )
            await state.set_state(QuickContractStates.waiting_for_clarification)
            await status.edit_text(
                quick_contract_service.build_clarification_message(outcome.missing_fields)
            )
            return

        assert outcome.contract is not None and outcome.client is not None
        await log_action(
            session,
            action="quick_draft_created",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            entity_type="contract",
            entity_id=outcome.contract.id,
        )
        contract, client = outcome.contract, outcome.client
        text = quick_contract_service.build_success_message(
            contract=contract,
            client=client,
            conditions=ContractConditions.model_validate(contract.service_data),
            requires_manual_review=outcome.requires_manual_review,
        )
        docx_path, pdf_path = outcome.docx_path, outcome.pdf_path

    await state.clear()
    await status.edit_text(text, parse_mode=None)
    assert docx_path is not None and pdf_path is not None
    await _send_draft_files(message, contract, client, docx_path, pdf_path)


@router.message(StateFilter(QuickContractStates.waiting_for_document), F.photo | F.document)
async def handle_quick_document_explicit(message: Message, state: FSMContext, db_user: User) -> None:
    await _process_document_message(message, state, db_user)


@router.message(StateFilter(None), F.photo | F.document)
async def handle_quick_document_auto(
    message: Message, state: FSMContext, db_user: User, role: str | None
) -> None:
    if role not in EMPLOYEE_ROLES:
        return
    if not _looks_like_quick_contract_request(message.caption):
        return
    await _process_document_message(message, state, db_user)


@router.message(StateFilter(QuickContractStates.waiting_for_clarification), F.text)
async def handle_clarification_answer(message: Message, state: FSMContext, db_user: User) -> None:
    pending = await message_link_service.load_pending_clarification(message.chat.id)
    if pending is None:
        await state.clear()
        await message.answer("Время ожидания ответа истекло. Начните заново: /new_contract")
        return

    status = await message.answer("⏳ Обрабатываю ответ...")

    async with session_scope() as session:
        outcome = await quick_contract_service.merge_clarification_answer(
            session, openai_service=openai_service, pending=pending, answer_text=message.text
        )

        if outcome.missing_fields:
            await message_link_service.save_pending_clarification(
                message.chat.id, outcome.pending_payload
            )
            await status.edit_text(
                quick_contract_service.build_clarification_message(outcome.missing_fields)
            )
            return

        assert outcome.contract is not None and outcome.client is not None
        await message_link_service.clear_pending_clarification(message.chat.id)
        await log_action(
            session,
            action="quick_draft_created",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            entity_type="contract",
            entity_id=outcome.contract.id,
        )
        contract, client = outcome.contract, outcome.client
        text = quick_contract_service.build_success_message(
            contract=contract,
            client=client,
            conditions=ContractConditions.model_validate(contract.service_data),
            requires_manual_review=outcome.requires_manual_review,
        )
        docx_path, pdf_path = outcome.docx_path, outcome.pdf_path

    await state.clear()
    await status.edit_text(text, parse_mode=None)
    assert docx_path is not None and pdf_path is not None
    await _send_draft_files(message, contract, client, docx_path, pdf_path)


@router.message(StateFilter(None), F.reply_to_message, F.text)
async def handle_contract_edit_reply(message: Message, db_user: User) -> None:
    contract_id = await message_link_service.resolve_contract_id(
        message.chat.id, message.reply_to_message.message_id
    )
    if contract_id is None:
        return

    status = await message.answer("⏳ Вношу правки...")

    async with session_scope() as session:
        contract = await session.get(Contract, contract_id)
        if contract is None:
            await status.edit_text("Договор не найден.")
            return
        client = await session.get(Client, contract.client_id)
        try:
            docx_path, pdf_path = await quick_contract_service.revise_contract_from_reply(
                session,
                openai_service=openai_service,
                contract=contract,
                client=client,
                edit_text=message.text,
                edited_by_id=db_user.id,
            )
        except quick_contract_service.ContractAlreadySignedError as exc:
            await status.edit_text(f"⛔ {exc}", parse_mode=None)
            return

        await log_action(
            session,
            action="quick_draft_revised",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            entity_type="contract",
            entity_id=contract.id,
            details={"edit_text": message.text},
        )
        contract_number = contract.contract_number
        version = contract.version

    await status.edit_text(f"✅ Договор № {contract_number} обновлён (версия {version}).")
    await _send_draft_files(message, contract, client, docx_path, pdf_path)


@router.callback_query(F.data.startswith("quick:hint_edit:"))
async def hint_edit(callback: CallbackQuery) -> None:
    await callback.message.answer(
        "Ответьте на сообщение с договором обычным текстом с правкой, например:\n"
        '"Поменяй стоимость на 30000", "Оплата не сразу, а после результата", '
        '"Убери адрес", "Номер клиента +7 777 000 0000".'
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quick:redo:"))
async def redo_conditions_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    contract_id = int(callback.data.split(":")[-1])
    await state.set_state(QuickContractStates.waiting_for_redo_conditions)
    await state.update_data(redo_contract_id=contract_id)
    await callback.message.answer("Опишите условия договора заново одним сообщением:")
    await callback.answer()


@router.message(StateFilter(QuickContractStates.waiting_for_redo_conditions), F.text)
async def redo_conditions_apply(message: Message, state: FSMContext, db_user: User) -> None:
    data = await state.get_data()
    contract_id = data.get("redo_contract_id")
    if contract_id is None:
        await state.clear()
        await message.answer("Не удалось определить договор. Начните заново: /new_contract")
        return

    status = await message.answer("⏳ Переделываю условия...")

    async with session_scope() as session:
        contract = await session.get(Contract, contract_id)
        if contract is None:
            await status.edit_text("Договор не найден.")
            await state.clear()
            return
        if contract.status in ("signed", "sent_for_signature"):
            await status.edit_text(
                "⛔ Договор уже отправлен клиенту на подписание или подписан; изменения невозможны."
            )
            await state.clear()
            return
        client = await session.get(Client, contract.client_id)

        if openai_service.is_enabled:
            conditions = await openai_service.extract_contract_conditions(employee_text=message.text)
        else:
            conditions = ContractConditions(service_type=message.text[:255])

        if not conditions.template_code:
            conditions.template_code = OpenAIService.suggest_template(conditions)
        if not conditions.result_definition:
            conditions.result_definition = OpenAIService.suggest_result_definition(conditions)

        template = await get_or_create_active_template(session, conditions.template_code)
        contract.template_id = template.id
        contract.service_data = conditions.model_dump()
        contract.amount = conditions.amount_kzt or 0
        contract.payment_type = conditions.payment_type
        contract.version += 1

        docx_path, pdf_path = await approve_contract_documents(
            session, contract, client, approved_by_id=db_user.id
        )
        contract_number = contract.contract_number

        await log_action(
            session,
            action="quick_draft_redone",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            entity_type="contract",
            entity_id=contract.id,
        )

    await state.clear()
    await status.edit_text(f"✅ Условия договора № {contract_number} обновлены.")
    await _send_draft_files(message, contract, client, docx_path, pdf_path)


@router.callback_query(F.data.startswith("quick:delete:"))
async def delete_draft(callback: CallbackQuery, db_user: User) -> None:
    contract_id = int(callback.data.split(":")[-1])
    async with session_scope() as session:
        contract = await session.get(Contract, contract_id)
        if contract is None:
            await callback.answer("Договор не найден.", show_alert=True)
            return
        if contract.status == "signed":
            await callback.answer("⛔ Подписанный договор нельзя удалить.", show_alert=True)
            return

        contract.status = "cancelled"
        released = False
        settings = get_settings()
        if settings.release_contract_number_on_delete:
            released = await release_last_number_if_matches(session, contract.contract_number)

        await log_action(
            session,
            action="quick_draft_deleted",
            user_id=db_user.id,
            telegram_id=db_user.telegram_id,
            entity_type="contract",
            entity_id=contract_id,
            details={"number_released": released},
        )
        contract_number = contract.contract_number

    suffix = " Номер освобождён." if released else ""
    await callback.message.edit_text(f"🗑 Договор № {contract_number} отменён.{suffix}", parse_mode=None)
    await callback.answer()
