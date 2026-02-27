"""
Запуск MAX-бота через библиотеку maxapi (pip install maxapi).
Используется для команды /showracemenu с отправкой файла через InputMedia(path=...).
При установленном maxapi run_max_bot() вызывает этот модуль.
"""
import logging

from adapters.max.showracemenu_maxapi import register_showracemenu

logger = logging.getLogger(__name__)


def _get_max_token() -> str:
    import os
    from config import CONFIG
    return (CONFIG.get("MAX") or {}).get("BOT_TOKEN") or os.getenv("MAX_BOT_TOKEN") or os.getenv("MAX_TOKEN") or ""


def _response_to_attachments(buttons: list) -> list:
    """
    Преобразует кнопки из формата handle_start/handlers (id, label, type)
    в вложения maxapi: InlineKeyboardBuilder + CallbackButton / RequestContactButton.
    По одной кнопке в ряд, как в главном меню MAX.
    """
    if not buttons:
        return []
    from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
    from maxapi.types.attachments.buttons import CallbackButton, RequestContactButton

    builder = InlineKeyboardBuilder()
    first = True
    for b in buttons:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "request_contact":
            btn = RequestContactButton(text=b.get("label", "📱 Поделиться контактом"))
        else:
            btn = CallbackButton(text=b.get("label", b.get("id", "")), payload=b.get("id", ""))
        if first:
            builder.add(btn)
            first = False
        else:
            builder.row(btn)
    return [builder.as_markup()]


async def run_max_bot_maxapi() -> None:
    """
    Запуск MAX-бота через maxapi: Bot, Dispatcher, polling.
    Обрабатываются /start (с главным меню/кнопками) и /showracemenu (картинка через InputMedia).
    Остальная логика (заявки WMS/Lupa, callback после нажатий) при использовании maxapi
    не подключена — для полного функционала используйте MaxBotAPI без maxapi.
    """
    token = _get_max_token().strip()
    if not token:
        logger.info("MAX: MAX_BOT_TOKEN не задан, бот в MAX не запускается")
        return

    from maxapi import Bot, Dispatcher
    from maxapi.types import Command, MessageCreated
    from maxapi.enums.parse_mode import ParseMode
    from adapters.max.handlers import handle_start

    bot = Bot(token=token)
    dp = Dispatcher()

    register_showracemenu(dp)

    @dp.message_created(Command("start"))
    async def on_start(event: MessageCreated):
        user_id = event.message.sender.user_id if event.message.sender else None
        if user_id is None:
            await event.message.answer("Ошибка: не удалось определить пользователя.")
            return
        response = handle_start(user_id)
        text = response.get("text") or ""
        parse_mode = ParseMode.HTML if (response.get("parse_mode") or "").lower() == "html" else None
        attachments = _response_to_attachments(response.get("buttons") or [])
        await event.message.answer(text=text, attachments=attachments, parse_mode=parse_mode)

    logger.info("MAX: бот запущен (maxapi, polling)")
    await dp.start_polling(bot)
