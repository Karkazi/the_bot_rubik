"""
Интерфейс доставки уведомлений: Core не зависит от aiogram/MAX.
Адаптер регистрирует callback; при уведомлении вызывается deliver(channel_id, channel_user_id, text, reply_markup).
reply_markup: None или список рядов кнопок — List[List[Dict]]; каждый dict: {"text": str, "callback_data": str}.
"""
import logging
from typing import Any, Awaitable, Callable, List, Optional

logger = logging.getLogger(__name__)

# Тип: (channel_id, channel_user_id, text, reply_markup) -> None
DeliveryCallback = Callable[[str, int, str, Any], Awaitable[None]]

_delivery: Optional[DeliveryCallback] = None


def set_delivery(callback: DeliveryCallback) -> None:
    """Регистрирует функцию доставки (вызывается из main/адаптера)."""
    global _delivery
    _delivery = callback


def get_delivery() -> Optional[DeliveryCallback]:
    return _delivery


async def deliver(
    channel_id: str,
    channel_user_id: int,
    text: str,
    reply_markup: Optional[List[List[dict]]] = None,
) -> None:
    """
    Отправить уведомление в канал.
    reply_markup: список рядов кнопок; каждый ряд — список dict с ключами "text", "callback_data".
    """
    if _delivery is None:
        logger.debug("Доставка не зарегистрирована, пропуск: channel_id=%s user_id=%s", channel_id, channel_user_id)
        return
    try:
        await _delivery(channel_id, channel_user_id, text, reply_markup)
    except Exception as e:
        logger.warning("Ошибка доставки (channel_id=%s, user_id=%s): %s", channel_id, channel_user_id, e)
