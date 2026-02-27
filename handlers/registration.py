"""
Обработчики регистрации: пошаговый ввод ФИО, логина, почты, телефона.
При дубликате логина/почты — сообщение «такой пользователь уже существует, обратитесь на первую линию».
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states import RegistrationStates
from keyboards import (
    get_main_menu_keyboard,
    get_start_keyboard,
    get_cancel_keyboard,
    get_department_keyboard,
    get_contact_request_keyboard,
    remove_reply_keyboard,
)
from validators import (
    validate_full_name,
    validate_work_login,
    validate_corporate_email,
    validate_phone,
    normalize_phone_display,
)
from core.registration import register_user
from user_storage import check_login_or_email_taken

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(lambda c: c.data == "start_registration")
async def start_registration(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "📝 <b>Регистрация</b>\n\n"
        "Шаг 1/5: Введите ваше <b>ФИО</b> только кириллицей (русские буквы, пробелы и дефис):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await state.set_state(RegistrationStates.WAITING_FOR_FULL_NAME)
    await callback.answer()


@router.message(RegistrationStates.WAITING_FOR_FULL_NAME, F.text)
async def process_full_name(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    ok, err = validate_full_name(text)
    if not ok:
        await message.reply(f"❗ {err}\n\nПопробуйте снова или нажмите Отмена.", reply_markup=get_cancel_keyboard())
        return
    await state.update_data(full_name=text)
    await state.set_state(RegistrationStates.WAITING_FOR_LOGIN)
    await message.reply(
        "✅ ФИО сохранено.\n\n"
        "Шаг 2/5: Введите <b>рабочий логин</b> (например: i.ivanov):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(RegistrationStates.WAITING_FOR_LOGIN, F.text)
async def process_login(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    ok, err = validate_work_login(text)
    if not ok:
        await message.reply(f"❗ {err}\n\nПопробуйте снова или нажмите Отмена.", reply_markup=get_cancel_keyboard())
        return
    login_lower = text.lower()
    taken, taken_msg = check_login_or_email_taken(login_lower, "", exclude_user_id=None)
    if taken:
        await message.reply(
            "❌ Пользователь с таким рабочим логином уже зарегистрирован. Обратитесь на первую линию поддержки.",
            reply_markup=get_cancel_keyboard(),
        )
        return
    await state.update_data(login=login_lower)
    await state.set_state(RegistrationStates.WAITING_FOR_EMAIL)
    await message.reply(
        "✅ Логин сохранён.\n\n"
        "Шаг 3/5: Введите <b>корпоративную почту</b> (@petrovich.ru или @petrovich.tech):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(RegistrationStates.WAITING_FOR_EMAIL, F.text)
async def process_email(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    ok, err = validate_corporate_email(text)
    if not ok:
        await message.reply(f"❗ {err}\n\nПопробуйте снова или нажмите Отмена.", reply_markup=get_cancel_keyboard())
        return
    email_lower = text.lower()
    data = await state.get_data()
    login = data.get("login", "")
    taken, _ = check_login_or_email_taken(login, email_lower, exclude_user_id=None)
    if taken:
        await message.reply(
            "❌ Пользователь с такой корпоративной почтой уже зарегистрирован. Обратитесь на первую линию поддержки.",
            reply_markup=get_cancel_keyboard(),
        )
        return
    await state.update_data(email=email_lower)
    await state.set_state(RegistrationStates.WAITING_FOR_DEPARTMENT)
    from core.jira_departments import get_departments_async
    departments = await get_departments_async()
    await message.reply(
        "✅ Почта сохранена.\n\n"
        "Шаг 4/5: Выберите ваше <b>подразделение</b> (Department):",
        parse_mode="HTML",
        reply_markup=get_department_keyboard(departments=departments),
    )


@router.callback_query(RegistrationStates.WAITING_FOR_DEPARTMENT, F.data.startswith("department_page_"))
async def process_department_page(callback: CallbackQuery, state: FSMContext):
    try:
        page = int(callback.data.replace("department_page_", ""))
    except ValueError:
        await callback.answer()
        return
    from core.jira_departments import get_departments_async
    departments = await get_departments_async()
    await callback.message.edit_reply_markup(reply_markup=get_department_keyboard(departments=departments, page=page))
    await callback.answer()


@router.callback_query(RegistrationStates.WAITING_FOR_DEPARTMENT, F.data.startswith("department_"))
async def process_department_select(callback: CallbackQuery, state: FSMContext):
    from core.jira_departments import get_departments_async
    departments = await get_departments_async()
    raw = callback.data.replace("department_", "")
    if raw.isdigit():
        idx = int(raw)
        if 0 <= idx < len(departments):
            selected = departments[idx]
            await state.update_data(department=selected)
            await state.set_state(RegistrationStates.WAITING_FOR_PHONE)
            await callback.message.edit_text(
                "✅ Подразделение сохранено.",
                parse_mode="HTML",
                reply_markup=get_cancel_keyboard(),
            )
            await callback.message.answer(
                "Шаг 5/5: Поделитесь номером телефона — нажмите кнопку ниже (так мы получим ваш настоящий номер):",
                reply_markup=get_contact_request_keyboard(),
            )
    await callback.answer()


@router.message(RegistrationStates.WAITING_FOR_PHONE, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    """Принимаем только контакт (поделиться номером) — так получаем настоящий номер телефона."""
    contact = message.contact
    if not contact or contact.user_id != message.from_user.id:
        await message.reply(
            "❌ Пожалуйста, поделитесь именно своим контактом (кнопка «Поделиться контактом»).",
            reply_markup=get_contact_request_keyboard(),
        )
        return
    raw_phone = (contact.phone_number or "").strip()
    if not raw_phone:
        await message.reply(
            "❌ Не удалось получить номер из контакта. Попробуйте ещё раз.",
            reply_markup=get_contact_request_keyboard(),
        )
        return
    ok, err = validate_phone(raw_phone)
    if not ok:
        await message.reply(
            f"❗ {err}\n\nПоделитесь контактом снова или нажмите Отмена.",
            reply_markup=get_contact_request_keyboard(),
        )
        return
    phone_norm = normalize_phone_display(raw_phone)
    data = await state.get_data()
    full_name = data.get("full_name")
    login = data.get("login")
    email = data.get("email")
    department = data.get("department", "").strip()
    if not all([full_name, login, email]):
        await message.reply("❌ Ошибка: данные регистрации потеряны. Начните с /start.", reply_markup=remove_reply_keyboard())
        await state.clear()
        return

    success, msg = await register_user(
        user_id=message.from_user.id,
        full_name=full_name,
        login=login,
        email=email,
        phone=phone_norm,
        department=department or None,
    )
    await state.clear()
    if success:
        lines = [f"• ФИО: {full_name}", f"• Логин: {login}", f"• Почта: {email}"]
        if department:
            lines.append(f"• Подразделение: {department}")
        lines.append(f"• Телефон: {phone_norm}")
        await message.reply(
            "✅ <b>Регистрация завершена</b>\n\n"
            + "\n".join(lines)
            + "\n\nТеперь вам доступны кнопки «Поменять пароль» и «Поменять учётные данные».",
            parse_mode="HTML",
            reply_markup=remove_reply_keyboard(),
        )
        await message.reply("Выберите действие:", reply_markup=get_main_menu_keyboard(message.from_user.id))
    else:
        await message.reply(f"❌ {msg}", reply_markup=remove_reply_keyboard())
        await message.reply("Начните заново:", reply_markup=get_start_keyboard(message.from_user.id))
