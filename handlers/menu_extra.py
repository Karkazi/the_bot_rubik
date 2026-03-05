"""
Помощь (по требованию ИБ: Личный кабинет и изменение учётных данных удалены).
"""
import logging
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from user_storage import is_user_registered

logger = logging.getLogger(__name__)
router = Router()
CHANNEL_ID = "telegram"

HELP_TEXT = (
    "❓ <b>Помощь</b>\n\n"
    "Этот бот позволяет создавать заявки в техническую поддержку:\n"
    "• <b>Сайт</b> — проблемы с поиском на petrovich.ru\n"
    "• <b>WMS</b> — заявки по настройке и работе складской системы\n"
    "• <b>Смена пароля</b> — запрос смены пароля учётной записи\n\n"
    "Заявки можно отслеживать в разделе «Мои заявки» (появляется после создания заявки)."
)


@router.callback_query(lambda c: c.data == "help")
async def help_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    await callback.message.edit_text(
        HELP_TEXT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
        ]),
    )
    await callback.answer()
