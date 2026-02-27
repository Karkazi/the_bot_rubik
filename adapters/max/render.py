"""
Рендер ответов Core (DTO) в формат MAX (текст + кнопки).
Структуры готовы для передачи в MAX Bot API (кнопки как список dict).
"""
from core.support.models import Text, Menu, MenuButton, Error


def menu_to_max(menu: Menu) -> dict:
    """Возвращает dict: text, parse_mode, buttons (список {id, label})."""
    return {
        "text": menu.text,
        "parse_mode": menu.parse_mode or "HTML",
        "buttons": [{"id": b.id, "label": b.label} for b in menu.buttons],
    }


def text_to_max(text: Text) -> dict:
    return {"text": text.content, "parse_mode": text.parse_mode or "HTML"}


def error_to_max(err: Error) -> dict:
    return {"text": f"❌ {err.message}", "parse_mode": "HTML"}
