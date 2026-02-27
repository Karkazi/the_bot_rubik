"""
Поменять учётные данные: пошаговое изменение ФИО, логина, почты, телефона (core).
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import ChangeCredentialsStates
from keyboards import get_main_menu_keyboard, get_cancel_keyboard, get_department_keyboard
from user_storage import is_user_registered, check_login_or_email_taken
from validators import (
    validate_full_name,
    validate_work_login,
    validate_corporate_email,
    validate_phone,
    normalize_phone_display,
)
from core.registration import update_credentials, get_profile_for_edit

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(lambda c: c.data == "change_credentials")
async def change_credentials_start(callback: CallbackQuery, state: FSMContext):
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    profile = get_profile_for_edit(callback.from_user.id)
    if not profile:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.clear()
    await state.set_state(ChangeCredentialsStates.WAITING_FOR_FULL_NAME)
    await callback.message.edit_text(
        f"✏️ <b>Изменение учётных данных</b>\n\n"
        f"Текущее ФИО: {profile.get('full_name', '—')}\n\n"
        f"Введите новое ФИО только кириллицей (русские буквы, пробелы и дефис):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(ChangeCredentialsStates.WAITING_FOR_FULL_NAME, F.text)
async def cred_full_name(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    ok, err = validate_full_name(text)
    if not ok:
        await message.reply(f"❗ {err}", reply_markup=get_cancel_keyboard())
        return
    await state.update_data(full_name=text)
    profile = get_profile_for_edit(message.from_user.id) or {}
    await state.set_state(ChangeCredentialsStates.WAITING_FOR_LOGIN)
    await message.reply(
        f"Текущий логин: {profile.get('login', '—')}\n\nВведите новый рабочий логин:",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(ChangeCredentialsStates.WAITING_FOR_LOGIN, F.text)
async def cred_login(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()
    ok, err = validate_work_login(text)
    if not ok:
        await message.reply(f"❗ {err}", reply_markup=get_cancel_keyboard())
        return
    taken, taken_msg = check_login_or_email_taken(text, "", exclude_user_id=message.from_user.id)
    if taken:
        await message.reply(f"❌ {taken_msg}", reply_markup=get_cancel_keyboard())
        return
    await state.update_data(login=text)
    profile = get_profile_for_edit(message.from_user.id) or {}
    await state.set_state(ChangeCredentialsStates.WAITING_FOR_EMAIL)
    await message.reply(
        f"Текущая почта: {profile.get('email', '—')}\n\nВведите новую корпоративную почту:",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(ChangeCredentialsStates.WAITING_FOR_EMAIL, F.text)
async def cred_email(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()
    ok, err = validate_corporate_email(text)
    if not ok:
        await message.reply(f"❗ {err}", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    taken, taken_msg = check_login_or_email_taken(data.get("login", ""), text, exclude_user_id=message.from_user.id)
    if taken:
        await message.reply(f"❌ {taken_msg}", reply_markup=get_cancel_keyboard())
        return
    await state.update_data(email=text)
    profile = get_profile_for_edit(message.from_user.id) or {}
    await state.set_state(ChangeCredentialsStates.WAITING_FOR_DEPARTMENT)
    from core.jira_departments import get_departments_async
    departments = await get_departments_async()
    await message.reply(
        f"Текущее подразделение: {profile.get('department', '—') or '—'}\n\nВыберите подразделение (Department):",
        reply_markup=get_department_keyboard(departments=departments),
    )


@router.callback_query(ChangeCredentialsStates.WAITING_FOR_DEPARTMENT, F.data.startswith("department_page_"))
async def cred_department_page(callback: CallbackQuery, state: FSMContext):
    try:
        page = int(callback.data.replace("department_page_", ""))
    except ValueError:
        await callback.answer()
        return
    from core.jira_departments import get_departments_async
    departments = await get_departments_async()
    await callback.message.edit_reply_markup(reply_markup=get_department_keyboard(departments=departments, page=page))
    await callback.answer()


@router.callback_query(ChangeCredentialsStates.WAITING_FOR_DEPARTMENT, F.data.startswith("department_"))
async def cred_department_select(callback: CallbackQuery, state: FSMContext):
    from core.jira_departments import get_departments_async
    departments = await get_departments_async()
    raw = callback.data.replace("department_", "")
    if raw.isdigit():
        idx = int(raw)
        if 0 <= idx < len(departments):
            await state.update_data(department=departments[idx])
            profile = get_profile_for_edit(callback.from_user.id) or {}
            await state.set_state(ChangeCredentialsStates.WAITING_FOR_PHONE)
            await callback.message.edit_text(
                f"Текущий телефон: {profile.get('phone', '—')}\n\nВведите новый телефон (+7-XXX-XXX-XX-XX):",
                reply_markup=get_cancel_keyboard(),
            )
    await callback.answer()


@router.message(ChangeCredentialsStates.WAITING_FOR_PHONE, F.text)
async def cred_phone(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    ok, err = validate_phone(text)
    if not ok:
        await message.reply(f"❗ {err}", reply_markup=get_cancel_keyboard())
        return
    phone_norm = normalize_phone_display(text)
    data = await state.get_data()
    success, msg = update_credentials(
        user_id=message.from_user.id,
        full_name=data.get("full_name", ""),
        login=data.get("login", ""),
        email=data.get("email", ""),
        phone=phone_norm,
        department=data.get("department"),
    )
    await state.clear()
    if success:
        await message.reply(
            f"✅ {msg}",
            reply_markup=get_main_menu_keyboard(message.from_user.id),
        )
    else:
        await message.reply(f"❌ {msg}", reply_markup=get_main_menu_keyboard(message.from_user.id))
