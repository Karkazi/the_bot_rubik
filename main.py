"""
Бот Rubik: регистрация, смена пароля (задача в Jira AA), смена учётных данных, админ (удаление пользователей).
Вся логика в core для последующего подключения из MAX (идентификация по номеру телефона).
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import CONFIG
from handlers.start import router as start_router
from handlers.registration import router as registration_router
from handlers.password import router as password_router
from handlers.admin import router as admin_router
from handlers.comments import router as comments_router
from handlers.my_tickets import router as my_tickets_router
from handlers.create_ticket import router as create_ticket_router
from handlers.menu_extra import router as menu_extra_router
from middlewares.antispam import AntispamMiddleware
from core.support.delivery import set_delivery
from core.notifications import run_registry_status_loop, run_registry_comments_loop

os.makedirs("data", exist_ok=True)
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("data/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def main():
    token = CONFIG.get("TELEGRAM", {}).get("TOKEN", "").strip()
    if not token:
        logger.critical("TELEGRAM_TOKEN не задан в .env")
        return

    os.makedirs("data", exist_ok=True)

    # Запуск MAX-бота в фоне, если задан MAX_BOT_TOKEN
    max_token = (CONFIG.get("MAX") or {}).get("BOT_TOKEN", "").strip()
    max_task = None
    if max_token:
        try:
            from adapters.max.main_max import run_max_bot
            max_task = asyncio.create_task(run_max_bot())
            logger.info("MAX-бот добавлен в запуск")
        except Exception as e:
            logger.warning("MAX-бот не запущен: %s", e)

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    async def deliver_to_channel(channel_id: str, channel_user_id: int, text: str, reply_markup=None):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        if channel_id == "telegram":
            markup = None
            if reply_markup:
                rows = [
                    [InlineKeyboardButton(text=b["text"], callback_data=b["callback_data"]) for b in row]
                    for row in reply_markup
                ]
                markup = InlineKeyboardMarkup(inline_keyboard=rows)
            await bot.send_message(channel_user_id, text, reply_markup=markup)
        elif channel_id == "max":
            try:
                from adapters.max.main_max import send_notification_to_max_user
                await send_notification_to_max_user(channel_user_id, text, reply_markup)
            except Exception as e:
                logger.warning("Доставка в MAX user_id=%s: %s", channel_user_id, e)
    set_delivery(deliver_to_channel)

    cooldown = float(os.getenv("ANTISPAM_COOLDOWN", "1.5"))
    dp.update.outer_middleware(AntispamMiddleware(cooldown=cooldown))

    dp.include_router(start_router)
    dp.include_router(registration_router)
    dp.include_router(password_router)
    dp.include_router(admin_router)
    dp.include_router(comments_router)
    dp.include_router(my_tickets_router)
    dp.include_router(create_ticket_router)
    dp.include_router(menu_extra_router)

    logger.info("Бот Rubik запущен")
    status_interval = int(os.getenv("PASSWORD_STATUS_CHECK_INTERVAL", "90"))
    comments_interval = int(os.getenv("COMMENTS_CHECK_INTERVAL", "30"))
    status_task = asyncio.create_task(run_registry_status_loop(interval_seconds=status_interval))
    comments_task = asyncio.create_task(run_registry_comments_loop(interval_seconds=comments_interval))
    try:
        await dp.start_polling(bot)
    finally:
        if max_task is not None:
            max_task.cancel()
            try:
                await max_task
            except asyncio.CancelledError:
                pass
        status_task.cancel()
        comments_task.cancel()
        for t in (status_task, comments_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
