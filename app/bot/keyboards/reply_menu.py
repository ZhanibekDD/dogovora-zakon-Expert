from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.core.config import get_settings

# Labels are the single source of truth: both this keyboard and the handlers that react to
# button taps (registered as `F.text == LABEL` alongside the equivalent command) import from
# here, so the two can never drift out of sync.
NEW_CONTRACT = "📄 Новый договор"
CONTRACTS = "📁 Мои договоры"
FIND_CONTRACT = "🔍 Найти договор"
TEMPLATES = "🧾 Шаблоны"
SETTINGS = "⚙️ Настройки"
HELP = "❓ Помощь"
OBJECTION = "📝 Сформировать возражение"


def main_reply_keyboard(role: str, telegram_id: int | None = None) -> ReplyKeyboardMarkup:
    """Persistent keyboard docked at the bottom of the chat (replaces the standard input
    row), as opposed to the inline keyboards attached to individual messages elsewhere in
    the bot. Telegram only allows one or the other per message, so this is sent once (after
    /start) and then stays put across the whole conversation until explicitly replaced."""
    rows = [
        [KeyboardButton(text=NEW_CONTRACT), KeyboardButton(text=CONTRACTS)],
        [KeyboardButton(text=FIND_CONTRACT), KeyboardButton(text=TEMPLATES)],
        [KeyboardButton(text=HELP)],
    ]
    if role in ("admin", "superadmin"):
        rows.append([KeyboardButton(text=SETTINGS)])
    if telegram_id is not None and telegram_id in get_settings().objection_allowed_ids:
        rows.append([KeyboardButton(text=OBJECTION)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)
