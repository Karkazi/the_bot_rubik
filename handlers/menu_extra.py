"""
Помощь и Личный кабинет: вывод информации, изменение учётных данных по полям.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from user_storage import is_user_registered, get_user_profile, save_user_profile, check_login_or_email_taken, check_employee_id_taken
from core.support.api import support_api
from adapters.telegram.render import render_menu_to_kwargs
from keyboards import get_main_menu_keyboard, get_cancel_keyboard, get_contact_request_keyboard, remove_reply_keyboard, get_department_keyboard
from validators import (
    validate_full_name,
    validate_work_login,
    validate_corporate_email,
    validate_phone,
    normalize_phone_display,
)
from core.registration import update_credentials

logger = logging.getLogger(__name__)
router = Router()
CHANNEL_ID = "telegram"

# --- Помощь ---
HELP_TEXT = (
    "❓ <b>Помощь</b>\n\n"
    "Этот бот позволяет создавать заявки в техническую поддержку:\n"
    "• <b>Сайт</b> — проблемы с поиском на petrovich.ru\n"
    "• <b>WMS</b> — заявки по настройке и работе складской системы\n"
    "• <b>Смена пароля</b> — запрос смены пароля учётной записи\n\n"
    "В разделе «Личный кабинет» можно просмотреть и изменить свои учётные данные. "
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


# --- Личный кабинет ---
@router.callback_query(lambda c: c.data == "personal_cabinet")
async def personal_cabinet(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    profile = get_user_profile(callback.from_user.id) or {}
    lines = [
        "👤 <b>Личный кабинет</b>",
        "",
        f"ФИО: {profile.get('full_name') or '—'}",
        f"Логин: {profile.get('login') or '—'}",
        f"Почта: {profile.get('email') or '—'}",
        f"Телефон: {profile.get('phone') or '—'}",
        f"Подразделение: {profile.get('department') or '—'}",
        f"Подразделение WMS: {profile.get('department_wms') or '—'}",
        f"Табельный номер: {profile.get('employee_id') or '—'}",
    ]
    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить учётную информацию", callback_data="cabinet_edit_choice")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda c: c.data == "cabinet_edit_choice")
async def cabinet_edit_choice(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ФИО", callback_data="cabinet_edit:full_name")],
        [InlineKeyboardButton(text="Логин", callback_data="cabinet_edit:login")],
        [InlineKeyboardButton(text="Почта", callback_data="cabinet_edit:email")],
        [InlineKeyboardButton(text="Подразделение", callback_data="cabinet_edit:department")],
        [InlineKeyboardButton(text="Телефон", callback_data="cabinet_edit:phone")],
        [InlineKeyboardButton(text="Подразделение WMS", callback_data="cabinet_edit:department_wms")],
        [InlineKeyboardButton(text="Табельный номер", callback_data="cabinet_edit:employee_id")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="personal_cabinet")],
    ])
    await callback.message.edit_text(
        "Что хотите изменить?",
        reply_markup=keyboard,
    )
    await callback.answer()


# Состояние редактирования одного поля
from states import CabinetEditStates


@router.callback_query(lambda c: c.data and c.data.startswith("cabinet_edit:"))
async def cabinet_edit_field_start(callback: CallbackQuery, state: FSMContext):
    field = (callback.data or "").split(":", 1)[-1].strip()
    if field not in ("full_name", "login", "email", "department", "phone", "department_wms", "employee_id"):
        await callback.answer()
        return
    profile = get_user_profile(callback.from_user.id) or {}
    current = profile.get(field) or "—"
    prompts = {
        "full_name": ("ФИО (только кириллица)", "text"),
        "login": ("Рабочий логин (i.ivanov)", "text"),
        "email": ("Корпоративная почта (@petrovich.ru / @petrovich.tech)", "text"),
        "department": ("Подразделение — выберите из списка", "department"),
        "phone": ("Телефон — нажмите «Поделиться контактом»", "contact"),
        "department_wms": ("Подразделение WMS — выберите из списка", "department_wms"),
        "employee_id": ("Табельный номер (например: 0000000311)", "text"),
    }
    label, kind = prompts.get(field, ("Значение", "text"))
    await state.set_state(CabinetEditStates.WAITING_VALUE)
    await state.update_data(edit_field=field, edit_kind=kind)
    if kind == "contact":
        await callback.message.edit_text(
            f"Текущее значение: {current}\n\nУкажите новый телефон — нажмите кнопку ниже:",
            reply_markup=get_contact_request_keyboard(),
        )
    elif kind == "department":
        from core.jira_departments import get_departments_async
        depts = await get_departments_async()
        await state.update_data(edit_departments_list=depts)
        await callback.message.edit_text(
            f"Текущее подразделение: {current}\n\nВыберите новое подразделение:",
            reply_markup=get_department_keyboard(departments=depts),
        )
    elif kind == "department_wms":
        from core.jira_wms_departments import get_wms_departments_async
        from keyboards import get_wms_department_keyboard
        depts = await get_wms_departments_async()
        await state.update_data(edit_wms_departments_list=depts)
        if not depts:
            await callback.message.edit_text(
                "Список подразделений WMS недоступен. Введите название вручную или нажмите Отмена.",
                reply_markup=get_cancel_keyboard(),
            )
        else:
            await callback.message.edit_text(
                f"Текущее подразделение WMS: {current}\n\nВыберите новое:",
                reply_markup=get_wms_department_keyboard(depts),
            )
    else:
        await callback.message.edit_text(
            f"Текущее значение: {current}\n\nВведите новое значение для поля «{label}»:",
            reply_markup=get_cancel_keyboard(),
        )
    await callback.answer()


def _apply_edit(profile: dict, field: str, value: str) -> dict:
    out = dict(profile)
    if field == "phone":
        from validators import normalize_phone_display
        out["phone"] = normalize_phone_display(value)
    else:
        out[field] = value.strip() if isinstance(value, str) else value
    return out


@router.message(CabinetEditStates.WAITING_VALUE, F.text)
async def cabinet_edit_text_value(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    data = await state.get_data()
    field = data.get("edit_field")
    kind = data.get("edit_kind")
    if kind == "contact":
        await message.reply("Пожалуйста, нажмите кнопку «Поделиться контактом».", reply_markup=get_contact_request_keyboard())
        return
    value = (message.text or "").strip()
    user_id = message.from_user.id
    profile = get_user_profile(user_id) or {}
    err = None
    if field == "full_name":
        ok, err = validate_full_name(value)
        if not ok:
            await message.reply(f"❗ {err}", reply_markup=get_cancel_keyboard())
            return
    elif field == "login":
        ok, err = validate_work_login(value)
        if not ok:
            await message.reply(f"❗ {err}", reply_markup=get_cancel_keyboard())
            return
        taken, msg = check_login_or_email_taken(value.lower(), "", exclude_user_id=user_id)
        if taken:
            await message.reply(f"❌ {msg}", reply_markup=get_cancel_keyboard())
            return
        value = value.lower()
    elif field == "email":
        ok, err = validate_corporate_email(value)
        if not ok:
            await message.reply(f"❗ {err}", reply_markup=get_cancel_keyboard())
            return
        taken, msg = check_login_or_email_taken("", value.lower(), exclude_user_id=user_id)
        if taken:
            await message.reply(f"❌ {msg}", reply_markup=get_cancel_keyboard())
            return
        value = value.lower()
    elif field == "employee_id":
        from validators import validate_employee_id
        ok, err = validate_employee_id(value)
        if not ok:
            await message.reply(f"❗ {err}", reply_markup=get_cancel_keyboard())
            return
        taken, _ = check_employee_id_taken(value, exclude_user_id=user_id)
        if taken:
            await message.reply("❌ Этот табельный номер уже используется другим пользователем.", reply_markup=get_cancel_keyboard())
            return
    elif field == "phone":
        ok, err = validate_phone(value)
        if not ok:
            await message.reply(f"❗ {err}", reply_markup=get_cancel_keyboard())
            return
        from validators import normalize_phone_display
        value = normalize_phone_display(value)
    new_profile = _apply_edit(profile, field, value)
    save_user_profile(user_id, new_profile)
    await state.clear()
    await message.reply("✅ Данные сохранены.", reply_markup=get_main_menu_keyboard(user_id))
    # Вернуть в кабинет
    await message.answer("Личный кабинет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить учётную информацию", callback_data="cabinet_edit_choice")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
    ]))


@router.message(CabinetEditStates.WAITING_VALUE, F.contact)
async def cabinet_edit_contact_value(message: Message, state: FSMContext):
    if not message.contact or message.contact.user_id != message.from_user.id:
        await message.reply("Поделитесь своим контактом.", reply_markup=get_contact_request_keyboard())
        return
    phone = (message.contact.phone_number or "").strip()
    ok, err = validate_phone(phone)
    if not ok:
        await message.reply(f"❗ {err}", reply_markup=get_contact_request_keyboard())
        return
    data = await state.get_data()
    field = data.get("edit_field")
    profile = get_user_profile(message.from_user.id) or {}
    from validators import normalize_phone_display
    value = normalize_phone_display(phone)
    new_profile = _apply_edit(profile, field, value)
    save_user_profile(message.from_user.id, new_profile)
    await state.clear()
    await message.reply("✅ Телефон сохранён.", reply_markup=remove_reply_keyboard())
    await message.answer("Личный кабинет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить учётную информацию", callback_data="cabinet_edit_choice")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
    ]))


@router.callback_query(CabinetEditStates.WAITING_VALUE, F.data.startswith("department_page_"))
async def cabinet_edit_department_page(callback: CallbackQuery, state: FSMContext):
    try:
        page = int(callback.data.replace("department_page_", ""))
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    depts = data.get("edit_departments_list") or []
    await callback.message.edit_reply_markup(reply_markup=get_department_keyboard(departments=depts, page=page))
    await callback.answer()


@router.callback_query(CabinetEditStates.WAITING_VALUE, F.data.regexp(r"^department_\d+$"))
async def cabinet_edit_department_select(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") != "department":
        await callback.answer()
        return
    depts = data.get("edit_departments_list") or []
    try:
        idx = int(callback.data.replace("department_", ""))
    except ValueError:
        await callback.answer()
        return
    if idx < 0 or idx >= len(depts):
        await callback.answer("Неверный выбор.", show_alert=True)
        return
    value = depts[idx]
    profile = get_user_profile(callback.from_user.id) or {}
    new_profile = _apply_edit(profile, "department", value)
    save_user_profile(callback.from_user.id, new_profile)
    await state.clear()
    await callback.message.edit_text(f"✅ Подразделение сохранено: {value}")
    await callback.message.answer("Личный кабинет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить учётную информацию", callback_data="cabinet_edit_choice")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
    ]))
    await callback.answer()


@router.callback_query(CabinetEditStates.WAITING_VALUE, F.data.startswith("wms_dept_page_"))
async def cabinet_edit_wms_department_page(callback: CallbackQuery, state: FSMContext):
    try:
        page = int(callback.data.replace("wms_dept_page_", ""))
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    depts = data.get("edit_wms_departments_list") or []
    from keyboards import get_wms_department_keyboard
    await callback.message.edit_reply_markup(reply_markup=get_wms_department_keyboard(depts, page=page))
    await callback.answer()


@router.callback_query(CabinetEditStates.WAITING_VALUE, F.data.regexp(r"^wms_dept_\d+$"))
async def cabinet_edit_wms_department_select(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("edit_field") != "department_wms":
        await callback.answer()
        return
    depts = data.get("edit_wms_departments_list") or []
    try:
        idx = int(callback.data.replace("wms_dept_", ""))
    except ValueError:
        await callback.answer()
        return
    if idx < 0 or idx >= len(depts):
        await callback.answer("Неверный выбор.", show_alert=True)
        return
    value = depts[idx]
    profile = get_user_profile(callback.from_user.id) or {}
    new_profile = _apply_edit(profile, "department_wms", value)
    save_user_profile(callback.from_user.id, new_profile)
    await state.clear()
    await callback.message.edit_text(f"✅ Подразделение WMS сохранено: {value}")
    await callback.message.answer("Личный кабинет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить учётную информацию", callback_data="cabinet_edit_choice")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
    ]))
    await callback.answer()