"""
Support Core: единое ядро для адаптеров Telegram и MAX.
Не зависит от канала доставки; адаптеры преобразуют DTO в формат канала.
"""
from core.support.models import Text, Menu, MenuButton, Form, FormField, Error
from core.support.api import support_api

__all__ = [
    "Text",
    "Menu",
    "MenuButton",
    "Form",
    "FormField",
    "Error",
    "support_api",
]
