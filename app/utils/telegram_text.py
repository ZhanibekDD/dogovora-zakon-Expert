from __future__ import annotations

import html


def escape_html(value: str | None) -> str:
    """Escape a value before interpolating it into an HTML parse_mode Telegram message.

    Telegram display names, OCR'd document text, and OpenAI-extracted free text are all
    attacker/user-controlled and frequently contain '<', '>' or '&' (emoji-decorated names,
    "Tom & Jerry"-style monikers, stray angle brackets in scanned text). Under parse_mode=HTML,
    Telegram rejects the *entire* message with a 'can't parse entities' error if any of that
    text isn't escaped - which silently kills the whole handler (and, notably, the main /start
    menu keyboard, since that message never gets sent at all).
    """
    if not value:
        return ""
    return html.escape(str(value), quote=False)
