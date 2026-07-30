from __future__ import annotations

from app.utils.telegram_text import escape_html

MALICIOUS_NAME = "Аскар <script>&Co"


def test_escape_html_escapes_angle_brackets_and_ampersand() -> None:
    escaped = escape_html(MALICIOUS_NAME)
    assert "<" not in escaped
    assert ">" not in escaped
    assert "&" not in escaped.replace("&lt;", "").replace("&gt;", "").replace("&amp;", "")


def test_escape_html_handles_none_and_empty() -> None:
    assert escape_html(None) == ""
    assert escape_html("") == ""


def test_start_greeting_survives_malicious_telegram_display_name() -> None:
    """Regression test for the bug that broke /start entirely: a Telegram display name is
    fully user-controlled and commonly contains '<'/'&'. Building the HTML parse_mode
    greeting the same way app/bot/handlers/start.py does must never leave those characters
    unescaped, or Telegram rejects the whole message (and its keyboard) outright."""
    label = "Менеджер"
    text = (
        f"Здравствуйте, {escape_html(MALICIOUS_NAME)}!\n"
        f"Ваша роль: <b>{escape_html(label)}</b>\n\nВыберите действие в меню внизу экрана."
    )
    assert "<script>" not in text
    assert "&Co" not in text
    # the one intentional structural tag must survive
    assert "<b>Менеджер</b>" in text


def test_employee_list_line_escapes_full_name() -> None:
    """Same pattern as app/bot/handlers/employees.py's employee listing line."""
    line = f"{escape_html(MALICIOUS_NAME)} (ID 12345) — manager — ✅ активен"
    assert "<script>" not in line
    assert "&Co" not in line
