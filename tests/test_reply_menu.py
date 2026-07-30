from __future__ import annotations

from aiogram.types import KeyboardButton

from app.bot.keyboards import reply_menu


def _all_button_texts(markup) -> set[str]:
    return {button.text for row in markup.keyboard for button in row}


def test_manager_keyboard_has_no_settings_button() -> None:
    markup = reply_menu.main_reply_keyboard("manager")
    texts = _all_button_texts(markup)
    assert reply_menu.NEW_CONTRACT in texts
    assert reply_menu.SETTINGS not in texts


def test_admin_keyboard_includes_settings_button() -> None:
    markup = reply_menu.main_reply_keyboard("admin")
    assert reply_menu.SETTINGS in _all_button_texts(markup)


def test_keyboard_is_persistent_and_resized() -> None:
    markup = reply_menu.main_reply_keyboard("manager")
    assert markup.resize_keyboard is True
    assert markup.is_persistent is True


def test_all_buttons_are_keyboard_buttons() -> None:
    markup = reply_menu.main_reply_keyboard("superadmin")
    for row in markup.keyboard:
        for button in row:
            assert isinstance(button, KeyboardButton)
