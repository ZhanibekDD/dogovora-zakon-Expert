from __future__ import annotations

import base64
import json

import pydantic
from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    RateLimitError,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.conditions import CONDITIONS_JSON_SCHEMA, ContractConditions
from app.schemas.contract_narrative import CONTRACT_NARRATIVE_JSON_SCHEMA, ContractNarrative
from app.schemas.edit_instruction import EDIT_INSTRUCTION_JSON_SCHEMA, ContractEditInstruction
from app.schemas.identity import IDENTITY_JSON_SCHEMA, IdentityExtraction
from app.schemas.objection import (
    NOTARIAL_WRIT_JSON_SCHEMA,
    OBJECTION_SUPPLEMENT_JSON_SCHEMA,
    NotarialWritExtraction,
    ObjectionSupplement,
)

logger = get_logger(__name__)

IDENTITY_SYSTEM_PROMPT = (
    "Извлекай только реквизиты, которые явно видны на документе или прямо указаны "
    "пользователем. Никогда не додумывай отсутствующие сведения. При сомнении возвращай "
    "null и добавляй предупреждение. Сохраняй исходное написание ФИО и казахские символы "
    "(Ә, Ғ, Қ, Ң, Ө, Ұ, Ү, Һ, І). Не описывай внешность человека, одежду или иные визуальные "
    "признаки — извлекаются только текстовые реквизиты документа. ИИН должен содержать ровно "
    "12 цифр. Все даты должны быть в формате DD.MM.YYYY. Возвращай результат строго по "
    "переданной JSON-схеме."
)

EDIT_INSTRUCTION_SYSTEM_PROMPT = (
    "Ты извлекаешь точечное изменение к уже сформированному договору ZakonExpert из одной "
    "короткой реплики сотрудника. Возвращай только те поля, которые сотрудник явно упомянул "
    "в этой реплике — всё остальное оставляй null / false / пустым списком, чтобы не затереть "
    "ранее сохранённые данные договора. Ничего не выдумывай. Суммы — целым числом тенге. "
    "Возвращай результат строго по переданной JSON-схеме."
)

NOTARIAL_WRIT_SYSTEM_PROMPT = (
    "Ты извлекаешь реквизиты из фотографии/скана «Исполнительной надписи» нотариуса "
    "Республики Казахстан (документ портала «Е-Нотариат»). Извлекай только то, что явно "
    "видно на изображении. Никогда не додумывай отсутствующие сведения — при сомнении "
    "возвращай null и добавляй предупреждение. Сохраняй исходное написание ФИО и казахские "
    "символы (Ә, Ғ, Қ, Ң, Ө, Ұ, Ү, Һ, І). ИИН должен содержать ровно 12 цифр, даты — формат "
    "DD.MM.YYYY. ФИО должника обычно указано в порядке Фамилия Имя Отчество — раздели по "
    "словам аккуратно. Суммы указывай числом (с копейками/тиын, если есть, через точку), без "
    "разделителей разрядов и без слова «тенге». "
    "Поле creditor_name_nominative — точное юридическое наименование взыскателя как оно "
    "напечатано (например: Акционерное общество \"Народный Банк Казахстана\"). "
    "Поле creditor_name_genitive — то же наименование в родительном падеже, готовое для "
    "подстановки после слов «в пользу»: склоняется только организационно-правовая форма, "
    "название в кавычках не меняется. Примеры: «Акционерное общество \"X\"» → "
    "«Акционерного общества \"X\"»; «Товарищество с ограниченной ответственностью \"Y\"» → "
    "«Товарищества с ограниченной ответственностью \"Y\"»; «Индивидуальный предприниматель "
    "Иванов И.И.» → «Индивидуального предпринимателя Иванова И.И.». "
    "Поле obligation_basis_clause — короткая фраза об основании взыскания, готовая для "
    "подстановки после слов «взыскание произведено», например «по договору банковского займа "
    "№CPA000016337588 от 22.09.2025» или «по Договору №T0T0PP34834577 от 02.06.2025»; если "
    "период или номер договора не читаются, оставь null. "
    "Возвращай результат строго по переданной JSON-схеме."
)

OBJECTION_SUPPLEMENT_SYSTEM_PROMPT = (
    "Сотрудник отвечает одним коротким сообщением на вопрос о недостающих данных для "
    "возражения на исполнительную надпись — это может быть номер телефона клиента, email, "
    "ИИН, ФИО должника, либо любой другой реквизит исполнительной надписи (уникальный номер, "
    "номер в реестре, дата, наименование взыскателя, суммы), который сотрудник прочитал с "
    "бумажного документа вручную. Извлекай из сообщения только явно упомянутые поля — "
    "остальное оставляй null, чтобы не затереть уже известные данные. Ничего не выдумывай. "
    "Возвращай результат строго по переданной JSON-схеме."
)

CONDITIONS_SYSTEM_PROMPT = (
    "Ты извлекаешь структурированные условия юридического договора из свободного текста "
    "сотрудника юридической компании ZakonExpert (Казахстан). Извлекай только то, что "
    "явно указано в тексте. Ничего не выдумывай: если сведение не упомянуто, возвращай null "
    "или пустой список. Суммы указывай целым числом тенге без разделителей. Если в тексте "
    "не указан явный код шаблона, оставь template_code как null и попробуй определить его "
    "по смыслу (снятие ареста от ЧСИ, отмена исполнительной надписи, снятие запрета на выезд, "
    "график погашения задолженности, отмена судебного решения, медиативное соглашение, "
    "обжалование штрафов, комбинированный договор), иначе null. Возвращай результат строго "
    "по переданной JSON-схеме."
)

CONTRACT_NARRATIVE_SYSTEM_PROMPT = (
    "Ты — юрист ZakonExpert (Казахстан), дорабатываешь два пункта уже утверждённого договора "
    "оказания услуг под конкретный случай клиента: 1.1 «Предмет договора» и 1.2 «В состав "
    "услуг входят» (без вступительных слов «В состав услуг входят:» и без завершающей точки — "
    "их добавляет система). Тебе передают утверждённый базовый текст обоих пунктов и факты по "
    "конкретному делу, которые сотрудник указал в этом обращении (вид услуги, банк, взыскатель, "
    "нотариус, ЧСИ, номер исполнительного производства, дополнительные условия). "
    "Впиши эти факты в базовый текст так, чтобы договор читался как составленный именно под "
    "это дело, а не как обезличенный шаблон — например, вместо «взыскателю, банку» напиши "
    "«взыскателю ТОО «X», АО «Народный Банк Казахстана»», если такие названия даны. Сохраняй "
    "юридический смысл, структуру предложений и все обязательства сторон из базового текста "
    "без изменений — меняются только конкретизирующие детали. НИКОГДА не добавляй ни одного "
    "имени, названия, номера, даты или обстоятельства, которого нет среди переданных фактов. "
    "Если по делу нет ни одного дополнительного факта сверх общих слов из базового текста — "
    "верни базовый текст без изменений по смыслу (допустима только грамматическая шлифовка "
    "падежей при перечислении). Официально-деловой стиль, обычный текст без списков и "
    "разметки, пункт 1.2 — через точку с запятой, как в базовом тексте. Возвращай результат "
    "строго по переданной JSON-схеме."
)


class OpenAIUnavailableError(Exception):
    """Raised when the OpenAI API cannot be reached or exceeded retries; caller should offer manual mode."""


class OpenAIService:
    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = bool(settings.openai_api_key)
        self._model = settings.openai_model
        self._client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=45.0, max_retries=3) if self._enabled else None

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def _run_structured(
        self, *, system_prompt: str, input_content: list[dict], json_schema: dict, schema_name: str
    ) -> dict:
        if self._client is None:
            raise OpenAIUnavailableError("OpenAI API key is not configured; use manual mode")

        try:
            response = await self._client.responses.create(  # type: ignore[call-overload]
                model=self._model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": input_content},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "schema": json_schema,
                        "strict": True,
                    }
                },
            )
        except RateLimitError as exc:
            logger.warning("openai_rate_limited", schema=schema_name)
            raise OpenAIUnavailableError("Превышен лимит запросов OpenAI, попробуйте позже") from exc
        except APIConnectionError as exc:
            logger.warning("openai_connection_error", schema=schema_name)
            raise OpenAIUnavailableError("OpenAI API недоступен") from exc
        except APIStatusError as exc:
            logger.warning("openai_status_error", schema=schema_name, status=exc.status_code)
            raise OpenAIUnavailableError(f"Ошибка OpenAI API: {exc.status_code}") from exc

        try:
            return json.loads(response.output_text)
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.error("openai_bad_response", schema=schema_name)
            raise OpenAIUnavailableError("OpenAI вернул некорректный ответ") from exc

    async def extract_identity_data(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        extra_images: list[tuple[bytes, str]] | None = None,
    ) -> IdentityExtraction:
        """Vision extraction of ID document fields. Never receives or returns anything about
        the person's appearance — only the schema's textual fields are requested.

        `extra_images` lets a multi-page PDF (front + back of the ID card rasterized as two
        separate pages) be sent as additional images in the same request, so the model can
        read both sides when the front alone doesn't carry everything.
        """
        input_content: list[dict] = [
            {
                "type": "input_text",
                "text": (
                    "На изображении — удостоверение личности гражданина Республики Казахстан. "
                    "Если приложено несколько изображений — это разные страницы/стороны одного "
                    "и того же документа. Извлеки реквизиты документа строго по схеме."
                ),
            },
        ]
        for data, mime in [(image_bytes, mime_type), *(extra_images or [])]:
            b64 = base64.b64encode(data).decode("ascii")
            input_content.append({"type": "input_image", "image_url": f"data:{mime};base64,{b64}"})

        raw = await self._run_structured(
            system_prompt=IDENTITY_SYSTEM_PROMPT,
            input_content=input_content,
            json_schema=IDENTITY_JSON_SCHEMA,
            schema_name="identity_extraction",
        )
        return self.validate_identity(raw)

    async def extract_identity_from_text(self, *, employee_text: str) -> IdentityExtraction:
        """Extract only identity fields explicitly typed by an employee.

        This powers the no-photo flow (``ФИО + ИИН``) and also lets a single clarification
        repair an unreadable ID scan without asking the employee to upload it again.
        """

        raw = await self._run_structured(
            system_prompt=IDENTITY_SYSTEM_PROMPT,
            input_content=[
                {
                    "type": "input_text",
                    "text": (
                        "Сотрудник вручную указал реквизиты клиента. Извлеки только явно "
                        f"написанные ФИО, ИИН и даты:\n{employee_text}"
                    ),
                }
            ],
            json_schema=IDENTITY_JSON_SCHEMA,
            schema_name="identity_from_text",
        )
        return self.validate_identity(raw)

    async def extract_contract_conditions(self, *, employee_text: str) -> ContractConditions:
        input_content = [{"type": "input_text", "text": employee_text}]
        raw = await self._run_structured(
            system_prompt=CONDITIONS_SYSTEM_PROMPT,
            input_content=input_content,
            json_schema=CONDITIONS_JSON_SCHEMA,
            schema_name="contract_conditions",
        )
        return self.validate_conditions(raw)

    async def draft_contract_narrative(
        self, *, conditions: ContractConditions, base_subject: str, base_actions: str
    ) -> ContractNarrative:
        """Rewrites the approved base clauses 1.1/1.2 to weave in this case's specific facts
        (bank, ЧСИ, взыскатель, нотариус, номер дела, доп. условия), so the contract reads as
        drafted for this client rather than a generic template. Never invents facts - see
        CONTRACT_NARRATIVE_SYSTEM_PROMPT. Caller (contract_service.draft_narrative_for_conditions)
        falls back to the unmodified base text if this raises."""
        facts = [
            f"Вид услуги (как описал сотрудник): {conditions.service_type or '—'}",
            f"Детали услуги: {'; '.join(conditions.service_details) or '—'}",
            f"Банк: {conditions.bank_name or '—'}",
            f"Взыскатель: {conditions.creditor_name or '—'}",
            f"Нотариус: {conditions.notary_name or '—'}",
            f"ЧСИ: {conditions.chsi_name or '—'}",
            f"Номер исполнительного производства: {conditions.enforcement_case_number or '—'}",
            f"Дополнительные условия: {'; '.join(conditions.additional_conditions) or '—'}",
        ]
        text = (
            f"Базовый текст пункта 1.1 (предмет договора):\n{base_subject}\n\n"
            f"Базовый текст пункта 1.2 (состав услуг, только содержимое перечисления):\n"
            f"{base_actions}\n\n"
            "Факты по делу:\n" + "\n".join(facts)
        )
        raw = await self._run_structured(
            system_prompt=CONTRACT_NARRATIVE_SYSTEM_PROMPT,
            input_content=[{"type": "input_text", "text": text}],
            json_schema=CONTRACT_NARRATIVE_JSON_SCHEMA,
            schema_name="contract_narrative",
        )
        return self.validate_contract_narrative(raw)

    async def extract_edit_instruction(self, *, instruction_text: str) -> ContractEditInstruction:
        input_content = [{"type": "input_text", "text": instruction_text}]
        raw = await self._run_structured(
            system_prompt=EDIT_INSTRUCTION_SYSTEM_PROMPT,
            input_content=input_content,
            json_schema=EDIT_INSTRUCTION_JSON_SCHEMA,
            schema_name="contract_edit_instruction",
        )
        return self.validate_edit_instruction(raw)

    async def extract_notarial_writ_data(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        extra_images: list[tuple[bytes, str]] | None = None,
    ) -> NotarialWritExtraction:
        """Vision extraction of a notarial writ of execution ('Исполнительная надпись')."""
        input_content: list[dict] = [
            {
                "type": "input_text",
                "text": (
                    "На изображении — «Исполнительная надпись» нотариуса Республики "
                    "Казахстан (документ портала «Е-Нотариат»). Если приложено несколько "
                    "изображений — это разные страницы одного документа. Извлеки реквизиты "
                    "строго по схеме."
                ),
            },
        ]
        for data, mime in [(image_bytes, mime_type), *(extra_images or [])]:
            b64 = base64.b64encode(data).decode("ascii")
            input_content.append({"type": "input_image", "image_url": f"data:{mime};base64,{b64}"})

        raw = await self._run_structured(
            system_prompt=NOTARIAL_WRIT_SYSTEM_PROMPT,
            input_content=input_content,
            json_schema=NOTARIAL_WRIT_JSON_SCHEMA,
            schema_name="notarial_writ_extraction",
        )
        return self.validate_notarial_writ(raw)

    async def extract_objection_supplement(self, *, employee_text: str) -> ObjectionSupplement:
        input_content = [{"type": "input_text", "text": employee_text}]
        raw = await self._run_structured(
            system_prompt=OBJECTION_SUPPLEMENT_SYSTEM_PROMPT,
            input_content=input_content,
            json_schema=OBJECTION_SUPPLEMENT_JSON_SCHEMA,
            schema_name="objection_supplement",
        )
        return self.validate_objection_supplement(raw)

    @staticmethod
    def validate_notarial_writ(raw: dict) -> NotarialWritExtraction:
        try:
            return NotarialWritExtraction.model_validate(raw)
        except pydantic.ValidationError as exc:
            logger.warning("notarial_writ_validation_failed", errors=exc.errors())
            raise

    @staticmethod
    def validate_objection_supplement(raw: dict) -> ObjectionSupplement:
        try:
            return ObjectionSupplement.model_validate(raw)
        except pydantic.ValidationError as exc:
            logger.warning("objection_supplement_validation_failed", errors=exc.errors())
            raise

    @staticmethod
    def validate_identity(raw: dict) -> IdentityExtraction:
        """Never trust a raw OpenAI response without Pydantic validation."""
        try:
            return IdentityExtraction.model_validate(raw)
        except pydantic.ValidationError as exc:
            logger.warning("identity_validation_failed", errors=exc.errors())
            raise

    @staticmethod
    def validate_conditions(raw: dict) -> ContractConditions:
        try:
            return ContractConditions.model_validate(raw)
        except pydantic.ValidationError as exc:
            logger.warning("conditions_validation_failed", errors=exc.errors())
            raise

    @staticmethod
    def validate_contract_narrative(raw: dict) -> ContractNarrative:
        try:
            return ContractNarrative.model_validate(raw)
        except pydantic.ValidationError as exc:
            logger.warning("contract_narrative_validation_failed", errors=exc.errors())
            raise

    @staticmethod
    def validate_edit_instruction(raw: dict) -> ContractEditInstruction:
        try:
            return ContractEditInstruction.model_validate(raw)
        except pydantic.ValidationError as exc:
            logger.warning("edit_instruction_validation_failed", errors=exc.errors())
            raise

    @staticmethod
    def suggest_template(conditions: ContractConditions) -> str:
        # "custom_approved" is a generic model fallback, not a stronger signal than the
        # employee's explicit service text. Reclassify it locally when the text is clear.
        if conditions.template_code and conditions.template_code != "custom_approved":
            return conditions.template_code
        text = (conditions.service_type + " " + " ".join(conditions.service_details)).lower()
        if "выезд" in text:
            return "travel_ban_lift"
        if "график" in text and ("арест" in text or "снят" in text):
            return "arrest_lift_and_schedule"
        if "график" in text:
            return "debt_schedule"
        if "надпис" in text and "арест" in text:
            return "combined"
        if "надпис" in text:
            return "notarial_writ_cancel"
        if "чси" in text or "арест" in text or "ограничен" in text:
            return "arrest_lift_chsi"
        if "медиатив" in text or "мировое" in text:
            return "mediation_agreement"
        if "штраф" in text:
            return "fine_appeal"
        if "судебн" in text and ("отмен" in text or "пересмотр" in text):
            return "court_decision_review"
        if "иск" in text:
            return "chsi_appeal_lawsuit"
        return conditions.template_code or "custom_approved"

    @staticmethod
    def suggest_result_definition(conditions: ContractConditions) -> str:
        if conditions.result_definition:
            return conditions.result_definition
        template_code = OpenAIService.suggest_template(conditions)
        presets = {
            "arrest_lift_chsi": (
                "снятие либо фактическое отсутствие активного ареста, ограничения, запрета или "
                "иного обременения в АИС ОИП, реестре должников, банковском приложении, "
                "информационной системе, либо получение постановления, уведомления или иного "
                "документа, подтверждающего снятие/прекращение соответствующей меры"
            ),
            "notarial_writ_cancel": (
                "получение постановления нотариуса об отмене исполнительной надписи либо "
                "вступившего в законную силу судебного акта об её отмене или признании не "
                "подлежащей исполнению"
            ),
            "travel_ban_lift": "снятие запрета на выезд из Республики Казахстан",
            "debt_schedule": "получение согласованного и подписанного графика погашения задолженности",
            "arrest_lift_and_schedule": (
                "снятие ареста/ограничения и получение согласованного графика погашения "
                "задолженности"
            ),
            "court_decision_review": "вынесение судебного акта в пользу Клиента",
            "mediation_agreement": "подписание медиативного или мирового соглашения",
            "chsi_appeal_lawsuit": (
                "получение ответа ЧСИ либо вступившего в законную силу судебного акта по "
                "административному иску"
            ),
            "fine_appeal": "списание, отмена либо снижение суммы штрафа",
            "combined": (
                "достижение одного из согласованных результатов, предусмотренных настоящим "
                "договором, подтверждённого официальным документом"
            ),
            "custom_approved": "результат, согласованный Сторонами и зафиксированный в договоре",
        }
        return presets.get(template_code, presets["custom_approved"])
