"""
DTO ответов Core: нейтральные структуры для адаптеров (Telegram, MAX).
Адаптер преобразует их в сообщения/кнопки/формы канала.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Any
from enum import Enum


class ResponseKind(str, Enum):
    TEXT = "text"
    MENU = "menu"
    FORM = "form"
    ERROR = "error"


@dataclass
class MenuButton:
    """Одна кнопка меню (inline или reply)."""
    id: str          # callback_data или action id
    label: str       # текст кнопки


@dataclass
class Text:
    """Простой текст (без кнопок или с кнопками через Menu)."""
    content: str
    parse_mode: Optional[str] = "HTML"


@dataclass
class Menu:
    """Меню из набора кнопок (главное меню, выбор типа заявки и т.д.)."""
    text: str
    buttons: List[MenuButton]
    parse_mode: Optional[str] = "HTML"


@dataclass
class FormField:
    """Поле формы: запрос ввода от пользователя."""
    name: str
    field_type: str   # "text" | "select" | "contact" | "file"
    label: str
    options: Optional[List[tuple]] = None  # для select: [(value, label), ...]


@dataclass
class Form:
    """Форма заявки или шаг регистрации: список полей и подсказка."""
    title: str
    fields: List[FormField]
    hint: Optional[str] = None
    parse_mode: Optional[str] = "HTML"


@dataclass
class Error:
    """Ошибка валидации или бизнес-логики."""
    message: str
    code: Optional[str] = None


# Union-тип ответа Core
Response = Text | Menu | Form | Error
