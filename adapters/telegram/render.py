"""
Рендер ответов Core (DTO) в формат Telegram (InlineKeyboard, сообщения).
Тонкий слой: Core возвращает Menu/Text/Error — здесь преобразуем в aiogram.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.support.models import Text, Menu, MenuButton, Error


def menu_to_inline_keyboard(menu: Menu) -> InlineKeyboardMarkup:
    """Преобразует Menu (список кнопок) в InlineKeyboardMarkup."""
    rows = [[InlineKeyboardButton(text=b.label, callback_data=b.id)] for b in menu.buttons]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_menu_to_kwargs(menu: Menu) -> dict:
    """Возвращает kwargs для message.answer(..., **kwargs)."""
    return {
        "text": menu.text,
        "parse_mode": menu.parse_mode or "HTML",
        "reply_markup": menu_to_inline_keyboard(menu),
    }


def render_text_to_kwargs(text: Text) -> dict:
    """Возвращает kwargs для message.answer(..., **kwargs)."""
    return {
        "text": text.content,
        "parse_mode": text.parse_mode or "HTML",
    }


def render_error_to_kwargs(err: Error) -> dict:
    """Возвращает kwargs для message.answer(..., **kwargs)."""
    return {
        "text": f"❌ {err.message}",
        "parse_mode": "HTML",
    }
