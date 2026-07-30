from __future__ import annotations

import enum


class Role(enum.StrEnum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    MANAGER = "manager"
    CLIENT = "client"


class ContractStatus(enum.StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    SENT_FOR_SIGNATURE = "sent_for_signature"
    SIGNED = "signed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"


class PaymentType(enum.StrEnum):
    PREPAYMENT = "prepayment"
    AFTER_RESULT = "after_result"
    SPLIT = "split"
    ALREADY_PAID = "already_paid"
    CUSTOM = "custom"


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"


class DocumentKind(enum.StrEnum):
    DRAFT_DOCX = "draft_docx"
    DRAFT_PDF = "draft_pdf"
    FINAL_DOCX = "final_docx"
    FINAL_PDF = "final_pdf"
    SIGNED_PDF = "signed_pdf"
    SOURCE_ID_PHOTO = "source_id_photo"


TEMPLATE_CODES: dict[str, str] = {
    "arrest_lift_chsi": "Снятие ареста или ограничения от ЧСИ",
    "notarial_writ_cancel": "Отмена исполнительной надписи",
    "travel_ban_lift": "Снятие запрета на выезд из Республики Казахстан",
    "debt_schedule": "Составление графика погашения задолженности",
    "arrest_lift_and_schedule": "Снятие ареста и дальнейшее составление графика",
    "court_decision_review": "Отмена или пересмотр судебного решения",
    "mediation_agreement": "Медиативное или мировое соглашение",
    "chsi_appeal_lawsuit": "Обращение к ЧСИ и административный иск при отказе",
    "fine_appeal": "Списание или обжалование штрафов",
    "combined": "Комбинированный договор",
    "custom_approved": "Свободный утверждённый шаблон",
}

DEFAULT_PENALTY_CLAUSE = (
    "При просрочке оплаты Клиент уплачивает Исполнителю пеню в размере 0,1% от суммы "
    "просроченного платежа за каждый календарный день просрочки, но общий размер пени не "
    "может превышать 20% от суммы просроченного обязательства. Уплата пени не освобождает "
    "Клиента от исполнения основного обязательства."
)

DEFAULT_ACCEPTANCE_CLAUSE = (
    "После достижения предусмотренного договором результата Исполнитель направляет Клиенту "
    "итоговый документ или уведомление о результате посредством Telegram, WhatsApp или "
    "электронной почты. Если Клиент в течение 3 календарных дней не направит мотивированные "
    "письменные возражения, услуги считаются оказанными и принятыми в полном объёме."
)

CLIENT_CONSENT_TEXT = (
    "Я ознакомлен(а) с условиями настоящего договора в полном объёме, согласен(на) с ними и "
    "подтверждаю своё намерение заключить договор путём проставления простой электронной "
    "подписи. Я даю согласие на обработку своих персональных данных Исполнителем в объёме, "
    "необходимом для исполнения настоящего договора. Мне известно, что простая электронная "
    "подпись не является усиленной квалифицированной электронной подписью (ЭЦП)."
)
