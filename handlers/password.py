"""
Поменять пароль: запрос нового пароля → создание задачи в Jira AA (core).
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import ChangePasswordStates
from keyboards import get_main_menu_keyboard, get_cancel_keyboard
from user_storage import is_user_registered
from core.password import request_password_change

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(lambda c: c.data == "change_password")
async def change_password_start(callback: CallbackQuery, state: FSMContext):
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    await state.set_state(ChangePasswordStates.WAITING_FOR_NEW_PASSWORD)
    await callback.message.edit_text(
        "🔑 <b>Смена пароля</b>\n\nРубик поможет! Введите новый пароль:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(ChangePasswordStates.WAITING_FOR_NEW_PASSWORD, F.text)
async def process_new_password(message: Message, state: FSMContext):
    new_password = (message.text or "").strip()
    if not new_password:
        await message.reply("Введите непустой пароль или нажмите Отмена.", reply_markup=get_cancel_keyboard())
        return
    success, msg = await request_password_change(message.from_user.id, new_password)
    await state.clear()
    if success:
        await message.reply(
            f"✅ {msg}",
            reply_markup=get_main_menu_keyboard(message.from_user.id),
        )
    else:
        await message.reply(
            f"❌ {msg}",
            reply_markup=get_main_menu_keyboard(message.from_user.id),
        )
