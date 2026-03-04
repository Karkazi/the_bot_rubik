"""
Создание заявки: «Создать заявку в ТП» → выбор раздела (Сайт | WMS | Смена пароля),
проверки department_wms / employee_id, пошаговые формы WMS и Lupa.
Смена пароля перенаправляется в handlers.password.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from user_storage import is_user_registered, get_user_profile, save_user_profile, check_employee_id_taken

from core.support.api import support_api
from core.support.models import Menu, Error
from adapters.telegram.render import render_menu_to_kwargs
from states import WmsTicketStates, WmsSettingsStates, PsiUserStates, LupaTicketStates, TpSectionStates
from keyboards import (
    get_main_menu_keyboard,
    get_cancel_keyboard,
    get_wms_department_keyboard,
    get_wms_subtype_keyboard,
    get_wms_process_keyboard,
    get_wms_service_type_keyboard,
    get_lupa_service_keyboard,
    get_lupa_request_type_keyboard,
    get_lupa_city_keyboard,
    get_lupa_skip_comment_keyboard,
    LUPA_SERVICE_VALUES,
    LUPA_REQUEST_TYPE_VALUES,
)

logger = logging.getLogger(__name__)
router = Router()
CHANNEL_ID = "telegram"

# --- «Создать заявку в ТП»: выбор раздела ---

@router.callback_query(lambda c: c.data == "create_ticket_tp")
async def create_ticket_tp(callback: CallbackQuery, state: FSMContext):
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "📋 <b>Создать заявку в ТП</b>\n\nВ каком разделе создаём заявку?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Сайт", callback_data="tp_section_site")],
            [InlineKeyboardButton(text="📦 WMS", callback_data="tp_section_wms")],
            [InlineKeyboardButton(text="🔑 Смена пароля", callback_data="tp_section_password")],
            [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
        ]),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "tp_section_password")
async def tp_section_password(callback: CallbackQuery, state: FSMContext):
    """Смена пароля — переход в сценарий смены пароля."""
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    await state.clear()
    from states import ChangePasswordStates
    await state.set_state(ChangePasswordStates.WAITING_FOR_NEW_PASSWORD)
    await callback.message.edit_text(
        "🔑 <b>Смена пароля</b>\n\nРубик поможет! Введите новый пароль:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.in_({"tp_section_wms", "ticket_wms_issue"}))
async def tp_section_wms(callback: CallbackQuery, state: FSMContext):
    """WMS: меню из 4 кнопок (проблема / настройки / пользователь PSIwms / назад).
    Срабатывает и на кнопку из раздела (tp_section_wms), и на кнопку из каталога типов (ticket_wms_issue)."""
    await callback.answer()
    if not is_user_registered(callback.from_user.id):
        await callback.message.answer("Сначала пройдите регистрацию.")
        return
    await state.clear()
    await state.set_state(WmsTicketStates.WAITING_WMS_SUBTYPE)
    await state.update_data(wms_entry_point="section" if callback.data == "tp_section_wms" else "catalog")
    await callback.message.edit_text(
        "📦 <b>WMS</b>\n\nГена на связи! Выберите тип заявки:",
        parse_mode="HTML",
        reply_markup=get_wms_subtype_keyboard(),
    )


@router.callback_query(TpSectionStates.WAITING_WMS_DEPARTMENT, F.data.startswith("wms_dept_page_"))
async def tp_wms_department_page(callback: CallbackQuery, state: FSMContext):
    try:
        page = int(callback.data.replace("wms_dept_page_", ""))
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    depts = data.get("tp_wms_departments_list") or []
    await callback.message.edit_reply_markup(reply_markup=get_wms_department_keyboard(depts, page=page))
    await callback.answer()


@router.callback_query(TpSectionStates.WAITING_WMS_DEPARTMENT, F.data.regexp(r"^wms_dept_\d+$"))
async def tp_wms_department_select(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    depts = data.get("tp_wms_departments_list") or []
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
    profile["department_wms"] = value
    save_user_profile(callback.from_user.id, profile)
    await state.clear()
    await state.set_state(WmsTicketStates.WAITING_FOR_PROCESS)
    await state.update_data(ticket_type_id="wms_issue")
    await callback.message.edit_text(
        "🚨 <b>Проблема в работе WMS</b>\n\nВыберите <b>сбойный процесс</b>:",
        parse_mode="HTML",
        reply_markup=get_wms_process_keyboard(),
    )
    await callback.answer()


async def _lupa_start_or_ask_department(callback_or_message, state: FSMContext, is_callback: bool):
    """Если в профиле нет подразделения — показать выбор из Jira и сохранить; иначе — шаг 1 Lupa (сервис)."""
    user_id = callback_or_message.from_user.id
    profile = get_user_profile(user_id) or {}
    department = (profile.get("department") or "").strip()
    if department:
        await state.clear()
        await state.set_state(LupaTicketStates.SELECT_PROBLEMATIC_SERVICE)
        await state.update_data(ticket_type_id="lupa_search")
        text = "🔍 <b>Создание заявки о поиске</b>\n\nШаг 1/5: Выберите проблемный сервис:"
        if is_callback:
            await callback_or_message.message.edit_text(text, parse_mode="HTML", reply_markup=get_lupa_service_keyboard())
            await callback_or_message.answer()
        else:
            await callback_or_message.reply(text, parse_mode="HTML", reply_markup=get_lupa_service_keyboard())
        return
    from core.jira_departments import get_departments_async
    from keyboards import get_department_keyboard
    depts = await get_departments_async()
    await state.clear()
    await state.set_state(LupaTicketStates.WAITING_FOR_DEPARTMENT)
    await state.update_data(ticket_type_id="lupa_search", tp_lupa_departments_list=depts)
    if not depts:
        if is_callback:
            await callback_or_message.message.edit_text(
                "Список подразделений недоступен. Попробуйте позже или укажите подразделение в Личном кабинете.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
                ]),
            )
            await callback_or_message.answer()
        else:
            await callback_or_message.reply(
                "Список подразделений недоступен. Попробуйте позже или укажите подразделение в Личном кабинете.",
                reply_markup=get_main_menu_keyboard(user_id),
            )
        return
    msg_text = "🔍 <b>Создание заявки о поиске (Lupa)</b>\n\nВыберите ваше подразделение (оно будет сохранено в профиль):"
    if is_callback:
        await callback_or_message.message.edit_text(msg_text, parse_mode="HTML", reply_markup=get_department_keyboard(departments=depts))
        await callback_or_message.answer()
    else:
        await callback_or_message.reply(msg_text, parse_mode="HTML", reply_markup=get_department_keyboard(departments=depts))


@router.callback_query(lambda c: c.data == "tp_section_site")
async def tp_section_site(callback: CallbackQuery, state: FSMContext):
    """Сайт (Lupa): если нет employee_id — запросить табельный; иначе подразделение (если нет) → выбор сервиса."""
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    profile = get_user_profile(callback.from_user.id) or {}
    employee_id = (profile.get("employee_id") or "").strip()
    if not employee_id:
        hint = (
            "💡 <i>Табельный номер можно найти в расчётном листке. "
            "Он нужен для идентификации в заявке.</i>"
        )
        await state.clear()
        await state.set_state(TpSectionStates.WAITING_EMPLOYEE_ID)
        await callback.message.edit_text(
            f"🌐 <b>Сайт (Lupa)</b>\n\nУкажите ваш <b>табельный номер</b> (например: 0000000311):\n\n{hint}",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
        await callback.answer()
        return
    await _lupa_start_or_ask_department(callback, state, is_callback=True)


EMPLOYEE_ID_HINT = (
    "💡 Табельный номер можно найти в расчётном листке. Он нужен для идентификации в заявке."
)


# --- Lupa: выбор по кнопкам (как the_bot_lupa) ---

@router.callback_query(LupaTicketStates.SELECT_PROBLEMATIC_SERVICE, F.data.in_(list(LUPA_SERVICE_VALUES)))
async def lupa_select_service(callback: CallbackQuery, state: FSMContext):
    """Шаг 1 → 2: сохранение сервиса, показ типа запроса."""
    service = LUPA_SERVICE_VALUES.get(callback.data)
    await state.update_data(problematic_service=service)
    await state.set_state(LupaTicketStates.SELECT_REQUEST_TYPE)
    await callback.message.edit_text(
        f"🔍 <b>Создание заявки о поиске</b>\n\n✅ Сервис: {service}\n\nШаг 2/5: Выберите тип запроса:",
        parse_mode="HTML",
        reply_markup=get_lupa_request_type_keyboard(),
    )
    await callback.answer()


@router.callback_query(LupaTicketStates.SELECT_REQUEST_TYPE, F.data.in_(list(LUPA_REQUEST_TYPE_VALUES)))
async def lupa_select_request_type(callback: CallbackQuery, state: FSMContext):
    """Шаг 2 → 3: сохранение типа запроса, подразделение из профиля, показ городов."""
    request_type = LUPA_REQUEST_TYPE_VALUES.get(callback.data)
    await state.update_data(request_type=request_type)
    profile = get_user_profile(callback.from_user.id) or {}
    subdivision = (profile.get("department") or "").strip()
    await state.update_data(subdivision=subdivision)
    from config import CONFIG
    cities = CONFIG.get("JIRA_LUPA", {}).get("CITIES", [])[:4]
    await state.set_state(LupaTicketStates.ENTER_CITY)
    await callback.message.edit_text(
        "🔍 <b>Создание заявки о поиске</b>\n\n"
        f"✅ Тип запроса: {request_type}\n"
        f"✅ Подразделение: {subdivision or 'не указано'}\n\n"
        "Шаг 3/5: Укажите город:",
        parse_mode="HTML",
        reply_markup=get_lupa_city_keyboard(cities),
    )
    await callback.answer()


@router.callback_query(LupaTicketStates.ENTER_CITY, F.data.startswith("lupa_city_"))
async def lupa_city_callback(callback: CallbackQuery, state: FSMContext):
    """Шаг 3: выбор города кнопкой или «Ввести вручную»."""
    if callback.data == "lupa_city_manual":
        await state.set_state(LupaTicketStates.ENTER_CITY_MANUAL)
        await callback.message.edit_text(
            "🔍 <b>Создание заявки о поиске</b>\n\nШаг 3/5: Введите название города:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
        await callback.answer()
        return
    city = callback.data.replace("lupa_city_", "", 1).replace("_", " ")
    await state.update_data(city=city)
    await state.set_state(LupaTicketStates.WAITING_FOR_DESCRIPTION)
    await callback.message.edit_text(
        f"🔍 <b>Создание заявки о поиске</b>\n\n✅ Город: {city}\n\n"
        "Шаг 4/5: Введите комментарий (описание проблемы):\n\nМожно пропустить, нажав кнопку ниже.",
        parse_mode="HTML",
        reply_markup=get_lupa_skip_comment_keyboard(),
    )
    await callback.answer()


@router.message(LupaTicketStates.ENTER_CITY_MANUAL, F.text)
async def lupa_city_manual(message: Message, state: FSMContext):
    """Ввод города вручную."""
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    city = (message.text or "").strip()
    if not city:
        await message.reply("Введите название города или /cancel.", reply_markup=get_cancel_keyboard())
        return
    await state.update_data(city=city)
    await state.set_state(LupaTicketStates.WAITING_FOR_DESCRIPTION)
    await message.reply(
        f"✅ Город: {city}\n\n"
        "Шаг 4/5: Введите комментарий (описание проблемы):\n\nМожно пропустить, нажав кнопку ниже.",
        parse_mode="HTML",
        reply_markup=get_lupa_skip_comment_keyboard(),
    )


@router.callback_query(LupaTicketStates.WAITING_FOR_DESCRIPTION, F.data == "lupa_skip_comment")
async def lupa_skip_comment(callback: CallbackQuery, state: FSMContext):
    """Пропуск комментария → создание заявки."""
    await state.update_data(description="")
    data = await state.get_data()
    await state.clear()
    profile = get_user_profile(callback.from_user.id) or {}
    subdivision = (data.get("subdivision") or profile.get("department") or "").strip()
    form_data = {
        "description": data.get("description", ""),
        "problematic_service": data.get("problematic_service", ""),
        "request_type": data.get("request_type", ""),
        "subdivision": subdivision,
        "city": data.get("city", ""),
    }
    success, issue_key, msg = await support_api.create_ticket(CHANNEL_ID, callback.from_user.id, "lupa_search", form_data)
    display_text = msg or issue_key
    if success:
        await callback.message.edit_text(f"✅ {display_text}", parse_mode="HTML")
        await callback.message.answer("Выберите действие:", reply_markup=get_main_menu_keyboard(callback.from_user.id))
    else:
        await callback.message.edit_text(f"❌ {display_text}", parse_mode="HTML")
        await callback.message.answer("Выберите действие:", reply_markup=get_main_menu_keyboard(callback.from_user.id))
    await callback.answer()


@router.message(TpSectionStates.WAITING_EMPLOYEE_ID, F.text)
async def tp_employee_id_enter(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    from validators import validate_employee_id
    value = (message.text or "").strip()
    ok, err = validate_employee_id(value)
    if not ok:
        await message.reply(f"❗ {err}\n\n{EMPLOYEE_ID_HINT}", reply_markup=get_cancel_keyboard())
        return
    taken, _ = check_employee_id_taken(value, exclude_user_id=message.from_user.id)
    if taken:
        await message.reply(
            "❗ Этот табельный номер уже привязан к другому пользователю. Введите другой номер или /cancel.",
            reply_markup=get_cancel_keyboard(),
        )
        return
    from user_storage import save_user_profile
    profile = get_user_profile(message.from_user.id) or {}
    profile["employee_id"] = value
    save_user_profile(message.from_user.id, profile)
    await _lupa_start_or_ask_department(message, state, is_callback=False)


@router.callback_query(LupaTicketStates.WAITING_FOR_DEPARTMENT, F.data.startswith("department_page_"))
async def lupa_department_page(callback: CallbackQuery, state: FSMContext):
    """Пагинация списка подразделений для Lupa."""
    try:
        page = int(callback.data.replace("department_page_", ""))
    except ValueError:
        await callback.answer()
        return
    from keyboards import get_department_keyboard
    data = await state.get_data()
    depts = data.get("tp_lupa_departments_list") or []
    await callback.message.edit_reply_markup(reply_markup=get_department_keyboard(departments=depts, page=page))
    await callback.answer()


@router.callback_query(LupaTicketStates.WAITING_FOR_DEPARTMENT, F.data.startswith("department_"))
async def lupa_department_select(callback: CallbackQuery, state: FSMContext):
    """Выбор подразделения для Lupa: сохраняем в профиль и переходим к выбору сервиса."""
    if "department_page_" in callback.data:
        await callback.answer()
        return
    data = await state.get_data()
    depts = data.get("tp_lupa_departments_list") or []
    raw = callback.data.replace("department_", "")
    if not raw.isdigit():
        await callback.answer()
        return
    idx = int(raw)
    if idx < 0 or idx >= len(depts):
        await callback.answer("Неверный выбор.", show_alert=True)
        return
    value = depts[idx]
    profile = get_user_profile(callback.from_user.id) or {}
    profile["department"] = value
    save_user_profile(callback.from_user.id, profile)
    await state.set_state(LupaTicketStates.SELECT_PROBLEMATIC_SERVICE)
    await state.update_data(ticket_type_id="lupa_search")
    await callback.message.edit_text(
        "🔍 <b>Создание заявки о поиске</b>\n\nШаг 1/5: Выберите проблемный сервис:",
        parse_mode="HTML",
        reply_markup=get_lupa_service_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "create_ticket")
async def show_ticket_types(callback: CallbackQuery, state: FSMContext):
    """Старое меню типов из каталога (если где-то осталась кнопка)."""
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    await state.clear()
    response = support_api.get_ticket_types_menu(CHANNEL_ID, callback.from_user.id)
    if isinstance(response, Error):
        await callback.message.edit_text(f"❌ {response.message}")
        await callback.answer()
        return
    kwargs = render_menu_to_kwargs(response)
    await callback.message.edit_text(**kwargs)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data == "ticket_rubik_password_change")
async def ticket_rubik_selected(callback: CallbackQuery, state: FSMContext):
    """Смена пароля — перенаправляем в сценарий «Поменять пароль»."""
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    await state.clear()
    from states import ChangePasswordStates
    await state.set_state(ChangePasswordStates.WAITING_FOR_NEW_PASSWORD)
    await callback.message.edit_text(
        "🔑 <b>Смена пароля</b>\n\nРубик поможет! Введите новый пароль:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


# ---------- WMS ----------
@router.callback_query(lambda c: c.data == "wms_type_back", WmsTicketStates.WAITING_WMS_SUBTYPE)
async def wms_type_back(callback: CallbackQuery, state: FSMContext):
    """Назад из меню WMS: в раздел (Сайт | WMS | Смена пароля) или в каталог типов заявок."""
    data = await state.get_data()
    entry = data.get("wms_entry_point") or "section"
    await state.clear()
    if entry == "catalog":
        response = support_api.get_ticket_types_menu(CHANNEL_ID, callback.from_user.id)
        if isinstance(response, Error):
            await callback.message.edit_text(f"❌ {response.message}")
        else:
            kwargs = render_menu_to_kwargs(response)
            await callback.message.edit_text(**kwargs)
    else:
        await callback.message.edit_text(
            "📋 <b>Создать заявку в ТП</b>\n\nВ каком разделе создаём заявку?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🌐 Сайт", callback_data="tp_section_site")],
                [InlineKeyboardButton(text="📦 WMS", callback_data="tp_section_wms")],
                [InlineKeyboardButton(text="🔑 Смена пароля", callback_data="tp_section_password")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")],
            ]),
        )
    await callback.answer()


@router.callback_query(lambda c: c.data == "wms_show_subtype_menu", WmsTicketStates.WAITING_WMS_SUBTYPE)
async def wms_show_subtype_menu(callback: CallbackQuery, state: FSMContext):
    """Вернуть меню выбора типа заявки WMS (из заглушки «настройки» / «пользователь»)."""
    await callback.message.edit_text(
        "Выберите тип заявки:",
        parse_mode="HTML",
        reply_markup=get_wms_subtype_keyboard(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "wms_type_issue", WmsTicketStates.WAITING_WMS_SUBTYPE)
async def wms_type_issue(callback: CallbackQuery, state: FSMContext):
    """Проблема в работе WMS (как the_bot_wms): подразделение → процесс → тема → описание (пропустить) → вложения."""
    profile = get_user_profile(callback.from_user.id) or {}
    dept_wms = (profile.get("department_wms") or "").strip()
    await state.update_data(ticket_type_id="wms_issue")
    if dept_wms:
        await state.set_state(WmsTicketStates.WAITING_FOR_PROCESS)
        await callback.message.edit_text(
            "🚨 <b>Проблема в работе WMS</b>\n\nВыберите <b>сбойный процесс</b>:",
            parse_mode="HTML",
            reply_markup=get_wms_process_keyboard(),
        )
    else:
        from core.jira_wms_departments import get_wms_departments_async
        depts = await get_wms_departments_async()
        await state.set_state(TpSectionStates.WAITING_WMS_DEPARTMENT)
        await state.update_data(tp_wms_departments_list=depts)
        if not depts:
            await callback.message.edit_text(
                "Список подразделений WMS недоступен. Попробуйте позже или обратитесь в поддержку.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")],
                ]),
            )
        else:
            await callback.message.edit_text(
                "🚨 <b>Проблема в работе WMS</b>\n\nВыберите ваше подразделение (оно будет сохранено в профиль):",
                parse_mode="HTML",
                reply_markup=get_wms_department_keyboard(depts),
            )
    await callback.answer()


@router.callback_query(lambda c: c.data == "wms_type_settings", WmsTicketStates.WAITING_WMS_SUBTYPE)
async def wms_type_settings(callback: CallbackQuery, state: FSMContext):
    """Изменение настроек системы WMS: подразделение → тип услуги → описание → вложения (обязательно) → завершить."""
    await callback.answer()
    profile = get_user_profile(callback.from_user.id) or {}
    dept_wms = (profile.get("department_wms") or "").strip()
    await state.update_data(ticket_type_id="wms_settings")
    if dept_wms:
        await state.set_state(WmsSettingsStates.WAITING_SERVICE_TYPE)
        await callback.message.edit_text(
            "⚙️ <b>Изменение настроек системы WMS</b>\n\nВыберите тип услуги:",
            parse_mode="HTML",
            reply_markup=get_wms_service_type_keyboard(),
        )
    else:
        from core.jira_wms_departments import get_wms_departments_async
        depts = await get_wms_departments_async()
        await state.set_state(WmsSettingsStates.WAITING_DEPARTMENT)
        await state.update_data(tp_wms_departments_list=depts)
        if not depts:
            await callback.message.edit_text(
                "Список подразделений WMS недоступен. Попробуйте позже или обратитесь в поддержку.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="wms_show_subtype_menu")],
                ]),
            )
        else:
            await callback.message.edit_text(
                "⚙️ <b>Изменение настроек системы WMS</b>\n\nВыберите ваше подразделение:",
                parse_mode="HTML",
                reply_markup=get_wms_department_keyboard(depts),
            )


@router.callback_query(WmsSettingsStates.WAITING_DEPARTMENT, F.data.startswith("wms_dept_page_"))
async def wms_settings_department_page(callback: CallbackQuery, state: FSMContext):
    try:
        page = int(callback.data.replace("wms_dept_page_", ""))
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    depts = data.get("tp_wms_departments_list") or []
    await callback.message.edit_reply_markup(reply_markup=get_wms_department_keyboard(depts, page=page))
    await callback.answer()


@router.callback_query(WmsSettingsStates.WAITING_DEPARTMENT, F.data.regexp(r"^wms_dept_\d+$"))
async def wms_settings_department_select(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    depts = data.get("tp_wms_departments_list") or []
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
    profile["department_wms"] = value
    save_user_profile(callback.from_user.id, profile)
    await state.update_data(department=value)
    await state.set_state(WmsSettingsStates.WAITING_SERVICE_TYPE)
    await callback.message.edit_text(
        "⚙️ <b>Изменение настроек системы WMS</b>\n\nВыберите тип услуги:",
        parse_mode="HTML",
        reply_markup=get_wms_service_type_keyboard(),
    )
    await callback.answer()


@router.callback_query(WmsSettingsStates.WAITING_SERVICE_TYPE, F.data.in_({"wms_service_topology", "wms_service_other"}))
async def wms_settings_service_type(callback: CallbackQuery, state: FSMContext):
    """Тип услуги: Изменение топологии / Другие настройки."""
    from core.wms_constants import WMS_SERVICE_TYPES
    key = callback.data
    service_type = WMS_SERVICE_TYPES.get(key)
    if not service_type:
        await callback.answer("Неверный выбор.", show_alert=True)
        return
    await callback.answer()
    await state.update_data(service_type=service_type)
    await state.set_state(WmsSettingsStates.WAITING_DESCRIPTION)
    await callback.message.edit_text(
        "⚙️ <b>Изменение настроек системы WMS</b>\n\n📝 Введите описание изменений (или «-» для пропуска):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.callback_query(WmsSettingsStates.WAITING_SERVICE_TYPE, F.data == "wms_show_subtype_menu")
async def wms_settings_back_to_subtype(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    entry = data.get("wms_entry_point", "section")
    await state.clear()
    await state.set_state(WmsTicketStates.WAITING_WMS_SUBTYPE)
    await state.update_data(wms_entry_point=entry)
    await callback.message.edit_text(
        "📦 <b>WMS</b>\n\nГена на связи! Выберите тип заявки:",
        parse_mode="HTML",
        reply_markup=get_wms_subtype_keyboard(),
    )
    await callback.answer()


@router.message(WmsSettingsStates.WAITING_DESCRIPTION, F.text)
async def wms_settings_description(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    desc = (message.text or "").strip()
    if desc == "—":
        desc = ""
    await state.update_data(description=desc, wms_settings_attachment_file_ids=[])
    await state.set_state(WmsSettingsStates.WAITING_ATTACHMENTS)
    await message.reply(
        "⚙️ <b>Изменение настроек системы WMS</b>\n\n📎 Загрузите вложения (обязательно). Добавлено: 0. Затем нажмите «✅ Завершить создание задачи».",
        parse_mode="HTML",
        reply_markup=_wms_settings_attachments_keyboard(),
    )


@router.message(WmsSettingsStates.WAITING_ATTACHMENTS, F.photo | F.document | F.video)
async def wms_settings_attachment_add(message: Message, state: FSMContext):
    data = await state.get_data()
    file_ids = list(data.get("wms_settings_attachment_file_ids") or [])
    if len(file_ids) >= 10:
        await message.reply("Достигнут лимит 10 файлов. Нажмите «✅ Завершить создание задачи».", reply_markup=_wms_settings_attachments_keyboard())
        return
    file_id = None
    if message.photo:
        photo = message.photo[-1]
        if getattr(photo, "file_size", 0) and photo.file_size > 10 * 1024 * 1024:
            await message.reply("Файл не должен превышать 10 МБ.", reply_markup=_wms_settings_attachments_keyboard())
            return
        file_id = photo.file_id
    elif message.document:
        if message.document.file_size and message.document.file_size > 10 * 1024 * 1024:
            await message.reply("Файл не должен превышать 10 МБ.", reply_markup=_wms_settings_attachments_keyboard())
            return
        file_id = message.document.file_id
    elif message.video:
        if message.video.file_size and message.video.file_size > 10 * 1024 * 1024:
            await message.reply("Видео не должно превышать 10 МБ.", reply_markup=_wms_settings_attachments_keyboard())
            return
        file_id = message.video.file_id
    if file_id:
        file_ids.append(file_id)
        await state.update_data(wms_settings_attachment_file_ids=file_ids)
        await message.reply(f"📎 Добавлено {len(file_ids)} из 10. Приложите файлы и нажмите «✅ Завершить создание задачи».", reply_markup=_wms_settings_attachments_keyboard())


@router.callback_query(WmsSettingsStates.WAITING_ATTACHMENTS, F.data == "finish_wms_settings")
async def finish_wms_settings(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    file_ids = data.get("wms_settings_attachment_file_ids") or []
    if not file_ids:
        await callback.answer("Вложения обязательны. Загрузите хотя бы один файл.", show_alert=True)
        return
    profile = get_user_profile(callback.from_user.id) or {}
    department = (profile.get("department_wms") or profile.get("department") or data.get("department") or "").strip()
    if not department:
        await callback.message.edit_text("Укажите подразделение.", reply_markup=get_main_menu_keyboard(callback.from_user.id))
        await state.clear()
        await callback.answer()
        return
    form_data = {
        "department": department,
        "service_type": (data.get("service_type") or "").strip(),
        "description": (data.get("description") or "").strip() or "-",
    }
    if not form_data["service_type"]:
        await callback.message.edit_text("Ошибка: не выбран тип услуги.", reply_markup=get_main_menu_keyboard(callback.from_user.id))
        await state.clear()
        await callback.answer()
        return
    import tempfile
    import os
    bot = callback.bot
    attachment_paths = []
    try:
        for fid in file_ids[:10]:
            try:
                f = await bot.get_file(fid)
                safe_name = (f.file_path or fid).replace("/", "_").replace("\\", "_")
                path = os.path.join(tempfile.gettempdir(), f"wms_settings_{safe_name}")
                await bot.download_file(f.file_path, path)
                if os.path.isfile(path) and os.path.getsize(path) <= 10 * 1024 * 1024:
                    attachment_paths.append(path)
            except Exception as e:
                logger.warning("Скачивание вложения TG wms_settings %s: %s", fid[:20] if isinstance(fid, str) else fid, e)
        success, issue_key, msg = await support_api.create_ticket(
            CHANNEL_ID, callback.from_user.id, "wms_settings", form_data, attachment_paths=attachment_paths
        )
        display_text = msg or issue_key
        if success and attachment_paths:
            display_text += f"\n\n📎 Приложено файлов: {len(attachment_paths)}."
    except Exception as e:
        logger.exception("TG wms_settings: %s", e)
        success, issue_key, msg = False, None, "Ошибка при создании заявки."
        display_text = msg
    finally:
        for p in attachment_paths:
            try:
                os.remove(p)
            except Exception:
                pass
    await state.clear()
    await callback.message.edit_text(
        f"✅ {display_text}" if success else f"❌ {display_text}",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(callback.from_user.id),
    )
    await callback.answer()


# --- Пользователь PSIwms ---
@router.callback_query(lambda c: c.data == "wms_type_psi_user", WmsTicketStates.WAITING_WMS_SUBTYPE)
async def wms_type_psi_user(callback: CallbackQuery, state: FSMContext):
    """Создать/изменить/удалить пользователя PSIwms: тема → ФИО+должность → подразделение → комментарий → вложения (опционально)."""
    await callback.answer()
    await state.update_data(ticket_type_id="wms_psi_user")
    await state.set_state(PsiUserStates.WAITING_TITLE)
    await callback.message.edit_text(
        "👤 <b>Создать/изменить/удалить пользователя PSIwms</b>\n\nВведите тему задачи (не менее 3 символов):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(PsiUserStates.WAITING_TITLE, F.text)
async def psi_user_title(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    title = (message.text or "").strip()
    if len(title) < 3:
        await message.reply("Тема должна быть не менее 3 символов. Введите тему задачи:", reply_markup=get_cancel_keyboard())
        return
    await state.update_data(summary=title)
    await state.set_state(PsiUserStates.WAITING_FULL_NAME)
    await message.reply(
        "👤 Введите ФИО полностью + должность пользователя PSIwms:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(PsiUserStates.WAITING_FULL_NAME, F.text)
async def psi_user_full_name(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    await state.update_data(full_name=(message.text or "").strip())
    profile = get_user_profile(message.from_user.id) or {}
    dept_wms = (profile.get("department_wms") or "").strip()
    if dept_wms:
        await state.update_data(department=dept_wms)
        await state.set_state(PsiUserStates.WAITING_COMMENT)
        await message.reply(
            "👤 Введите комментарий (или «-» для пропуска):",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard(),
        )
    else:
        from core.jira_wms_departments import get_wms_departments_async
        depts = await get_wms_departments_async()
        await state.set_state(PsiUserStates.WAITING_DEPARTMENT)
        await state.update_data(psi_departments_list=depts)
        if not depts:
            await message.reply("Список подразделений недоступен. Введите подразделение текстом или /cancel.", reply_markup=get_cancel_keyboard())
        else:
            await message.reply(
                "👤 Выберите подразделение:",
                parse_mode="HTML",
                reply_markup=get_wms_department_keyboard(depts),
            )


@router.callback_query(PsiUserStates.WAITING_DEPARTMENT, F.data.startswith("wms_dept_page_"))
async def psi_user_department_page(callback: CallbackQuery, state: FSMContext):
    try:
        page = int(callback.data.replace("wms_dept_page_", ""))
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    depts = data.get("psi_departments_list") or []
    await callback.message.edit_reply_markup(reply_markup=get_wms_department_keyboard(depts, page=page))
    await callback.answer()


@router.callback_query(PsiUserStates.WAITING_DEPARTMENT, F.data.regexp(r"^wms_dept_\d+$"))
async def psi_user_department_select(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    depts = data.get("psi_departments_list") or []
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
    profile["department_wms"] = value
    save_user_profile(callback.from_user.id, profile)
    await state.update_data(department=value)
    await state.set_state(PsiUserStates.WAITING_COMMENT)
    await callback.message.edit_text(
        "👤 <b>Создать/изменить/удалить пользователя PSIwms</b>\n\nВведите комментарий (или «-» для пропуска):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(PsiUserStates.WAITING_COMMENT, F.text)
async def psi_user_comment(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    comment = (message.text or "").strip()
    if comment == "—":
        comment = ""
    await state.update_data(comment=comment, psi_attachment_file_ids=[])
    await state.set_state(PsiUserStates.WAITING_ATTACHMENTS)
    await message.reply(
        "👤 <b>Создать/изменить/удалить пользователя PSIwms</b>\n\n📎 Вложения (опционально). Добавлено: 0. Нажмите «✅ Завершить создание задачи» или «⏭ Пропустить вложения».",
        parse_mode="HTML",
        reply_markup=_psi_user_attachments_keyboard(),
    )


@router.message(PsiUserStates.WAITING_ATTACHMENTS, F.photo | F.document | F.video)
async def psi_user_attachment_add(message: Message, state: FSMContext):
    data = await state.get_data()
    file_ids = list(data.get("psi_attachment_file_ids") or [])
    if len(file_ids) >= 10:
        await message.reply("Достигнут лимит 10 файлов. Нажмите «✅ Завершить создание задачи».", reply_markup=_psi_user_attachments_keyboard())
        return
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
        if getattr(message.photo[-1], "file_size", 0) and message.photo[-1].file_size > 10 * 1024 * 1024:
            await message.reply("Файл не должен превышать 10 МБ.", reply_markup=_psi_user_attachments_keyboard())
            return
    elif message.document:
        file_id = message.document.file_id
        if message.document.file_size and message.document.file_size > 10 * 1024 * 1024:
            await message.reply("Файл не должен превышать 10 МБ.", reply_markup=_psi_user_attachments_keyboard())
            return
    elif message.video:
        file_id = message.video.file_id
        if message.video.file_size and message.video.file_size > 10 * 1024 * 1024:
            await message.reply("Видео не должно превышать 10 МБ.", reply_markup=_psi_user_attachments_keyboard())
            return
    if file_id:
        file_ids.append(file_id)
        await state.update_data(psi_attachment_file_ids=file_ids)
        await message.reply(f"📎 Добавлено {len(file_ids)} из 10. «✅ Завершить создание задачи» или «⏭ Пропустить вложения».", reply_markup=_psi_user_attachments_keyboard())


async def _finish_psi_user_common(callback: CallbackQuery, state: FSMContext, file_ids: list):
    """Общая логика завершения заявки PSI user: создание тикета и вложения."""
    data = await state.get_data()
    profile = get_user_profile(callback.from_user.id) or {}
    department = (profile.get("department_wms") or profile.get("department") or data.get("department") or "").strip()
    if not department:
        await callback.message.edit_text("Укажите подразделение.", reply_markup=get_main_menu_keyboard(callback.from_user.id))
        await state.clear()
        return
    form_data = {
        "summary": (data.get("summary") or "").strip(),
        "full_name": (data.get("full_name") or "").strip(),
        "department": department,
        "comment": (data.get("comment") or "").strip(),
    }
    if not form_data["full_name"]:
        await callback.message.edit_text("Ошибка: не указаны ФИО и должность.", reply_markup=get_main_menu_keyboard(callback.from_user.id))
        await state.clear()
        return
    success, issue_key, msg = await support_api.create_ticket(CHANNEL_ID, callback.from_user.id, "wms_psi_user", form_data)
    display_text = msg or issue_key
    attachment_paths = []
    if success and issue_key and file_ids:
        import tempfile
        import os
        bot = callback.bot
        try:
            for fid in file_ids[:10]:
                try:
                    f = await bot.get_file(fid)
                    safe_name = (f.file_path or fid).replace("/", "_").replace("\\", "_")
                    path = os.path.join(tempfile.gettempdir(), f"psi_user_{safe_name}")
                    await bot.download_file(f.file_path, path)
                    if os.path.isfile(path) and os.path.getsize(path) <= 10 * 1024 * 1024:
                        attachment_paths.append(path)
                except Exception as e:
                    logger.warning("Скачивание вложения TG psi_user %s: %s", fid[:20] if isinstance(fid, str) else fid, e)
            if attachment_paths:
                from core.jira_wms import add_attachments_to_issue
                added, _ = await add_attachments_to_issue(issue_key, attachment_paths)
                if added:
                    display_text += f"\n\n📎 Приложено файлов: {added}."
            for p in attachment_paths:
                try:
                    os.remove(p)
                except Exception:
                    pass
        except Exception as e:
            logger.exception("TG psi_user attachments: %s", e)
    await state.clear()
    await callback.message.edit_text(
        f"✅ {display_text}" if success else f"❌ {display_text}",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(callback.from_user.id),
    )


@router.callback_query(PsiUserStates.WAITING_ATTACHMENTS, F.data == "finish_psi_user")
async def finish_psi_user(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    file_ids = data.get("psi_attachment_file_ids") or []
    await _finish_psi_user_common(callback, state, file_ids)


@router.callback_query(PsiUserStates.WAITING_ATTACHMENTS, F.data == "skip_psi_attachment")
async def skip_psi_attachment(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _finish_psi_user_common(callback, state, [])


@router.callback_query(WmsTicketStates.WAITING_FOR_PROCESS, F.data.startswith("wms_process_"))
async def wms_process_callback(callback: CallbackQuery, state: FSMContext):
    """Шаг 2: выбор сбойного процесса (как the_bot_wms)."""
    from core.wms_constants import WMS_PROCESSES
    key = (callback.data or "").replace("wms_process_", "", 1)
    process_value = WMS_PROCESSES.get(key)
    if not process_value:
        await callback.answer("Неверный выбор.", show_alert=True)
        return
    await callback.answer()
    await state.update_data(process=process_value)
    await state.set_state(WmsTicketStates.WAITING_FOR_SUMMARY)
    await callback.message.edit_text(
        "🚨 <b>Проблема в работе WMS</b>\n\nВведите <b>тему</b> проблемы (кратко):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )


@router.message(WmsTicketStates.WAITING_FOR_PROCESS, F.text)
async def wms_process_message(message: Message, state: FSMContext):
    """Процесс выбирается только кнопкой."""
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    await message.reply(
        "Выберите процесс кнопкой ниже:",
        parse_mode="HTML",
        reply_markup=get_wms_process_keyboard(),
    )


@router.message(WmsTicketStates.WAITING_FOR_SUMMARY, F.text)
async def wms_summary(message: Message, state: FSMContext):
    """Шаг 3: тема заявки."""
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    await state.update_data(summary=(message.text or "").strip())
    await state.set_state(WmsTicketStates.WAITING_FOR_DESCRIPTION)
    skip_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="wms_skip_description")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])
    await message.reply(
        "Введите <b>подробное описание</b> проблемы или нажмите «Пропустить»:",
        parse_mode="HTML",
        reply_markup=skip_btn,
    )


@router.callback_query(WmsTicketStates.WAITING_FOR_DESCRIPTION, F.data == "wms_skip_description")
async def wms_skip_description(callback: CallbackQuery, state: FSMContext):
    """Пропуск описания → шаг вложений."""
    await callback.answer()
    await state.update_data(description="", wms_attachment_file_ids=[])
    await state.set_state(WmsTicketStates.WAITING_FOR_ATTACHMENTS)
    text = (
        "📎 Приложите фото, видео или документы (до 10 файлов, до 10 МБ каждый).\n\n"
        "Добавлено: 0 из 10.\n\nИли нажмите «Завершить создание тикета»."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_wms_attachments_keyboard())


def _wms_attachments_keyboard():
    """Вложения WMS (проблема): завершить или отмена. Текст кнопки как в the_bot_wms."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Завершить создание задачи", callback_data="wms_finish_ticket")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def _wms_settings_attachments_keyboard():
    """Настройки WMS: вложения обязательны — только завершить."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Завершить создание задачи", callback_data="finish_wms_settings")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def _psi_user_attachments_keyboard():
    """Пользователь PSIwms: вложения опциональны — завершить или пропустить."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Завершить создание задачи", callback_data="finish_psi_user")],
        [InlineKeyboardButton(text="⏭ Пропустить вложения", callback_data="skip_psi_attachment")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


@router.message(WmsTicketStates.WAITING_FOR_DESCRIPTION, F.text)
async def wms_description(message: Message, state: FSMContext):
    """Шаг 4: описание (или пропустить)."""
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    await state.update_data(description=(message.text or "").strip())
    await state.set_state(WmsTicketStates.WAITING_FOR_ATTACHMENTS)
    await state.update_data(wms_attachment_file_ids=[])
    await message.reply(
        "📎 Приложите фото, видео или документы (до 10 файлов, до 10 МБ каждый). Или нажмите «Завершить создание тикета».",
        parse_mode="HTML",
        reply_markup=_wms_attachments_keyboard(),
    )


@router.message(WmsTicketStates.WAITING_FOR_ATTACHMENTS, F.photo | F.document | F.video)
async def wms_attachment_add(message: Message, state: FSMContext):
    """Добавление вложения (до 10, до 10 МБ)."""
    data = await state.get_data()
    file_ids = list(data.get("wms_attachment_file_ids") or [])
    if len(file_ids) >= 10:
        await message.reply("Достигнут лимит 10 файлов. Нажмите «Завершить создание тикета».", reply_markup=_wms_attachments_keyboard())
        return
    file_id = None
    if message.photo:
        photo = message.photo[-1]
        if getattr(photo, "file_size", 0) and photo.file_size > 10 * 1024 * 1024:
            await message.reply("Фото не должно превышать 10 МБ.", reply_markup=_wms_attachments_keyboard())
            return
        file_id = photo.file_id
    elif message.document:
        if message.document.file_size and message.document.file_size > 10 * 1024 * 1024:
            await message.reply("Файл не должен превышать 10 МБ.", reply_markup=_wms_attachments_keyboard())
            return
        file_id = message.document.file_id
    elif message.video:
        if message.video.file_size and message.video.file_size > 10 * 1024 * 1024:
            await message.reply("Видео не должно превышать 10 МБ.", reply_markup=_wms_attachments_keyboard())
            return
        file_id = message.video.file_id
    if file_id:
        file_ids.append(file_id)
        await state.update_data(wms_attachment_file_ids=file_ids)
        await message.reply(f"📎 Добавлено {len(file_ids)} из 10. Можно приложить ещё или нажмите «Завершить создание тикета».", reply_markup=_wms_attachments_keyboard())


@router.callback_query(WmsTicketStates.WAITING_FOR_ATTACHMENTS, F.data == "wms_finish_ticket")
async def wms_finish_ticket(callback: CallbackQuery, state: FSMContext):
    """Завершение: создание тикета и загрузка вложений в Jira."""
    await callback.answer()
    data = await state.get_data()
    profile = get_user_profile(callback.from_user.id) or {}
    department = (profile.get("department_wms") or profile.get("department") or "").strip()
    if not department:
        await callback.message.edit_text(
            "Укажите подразделение в профиле или начните заявку заново и выберите подразделение.",
            reply_markup=get_main_menu_keyboard(callback.from_user.id),
        )
        await state.clear()
        return
    form_data = {
        "summary": (data.get("summary") or "").strip() or "Заявка по настройке WMS",
        "description": (data.get("description") or "").strip(),
        "process": (data.get("process") or "").strip(),
        "department": department,
    }
    if not form_data["process"]:
        await callback.message.edit_text("Ошибка: не выбран процесс.", reply_markup=get_main_menu_keyboard(callback.from_user.id))
        await state.clear()
        return
    file_ids = data.get("wms_attachment_file_ids") or []
    # API возвращает (success, issue_key, msg); msg — текст с ссылкой на заявку
    success, issue_key, msg = await support_api.create_ticket(CHANNEL_ID, callback.from_user.id, "wms_issue", form_data)
    display_text = msg or issue_key
    attachment_paths = []
    if success and issue_key and file_ids:
        import tempfile
        import os
        bot = callback.bot
        try:
            for fid in file_ids[:10]:
                try:
                    f = await bot.get_file(fid)
                    # destination: путь к файлу (aiogram 3: download_file(file_path, destination))
                    safe_name = f.file_path.replace("/", "_").replace("\\", "_") if f.file_path else fid
                    path = os.path.join(tempfile.gettempdir(), f"wms_attach_{safe_name}")
                    await bot.download_file(f.file_path, path)
                    if os.path.isfile(path) and os.path.getsize(path) <= 10 * 1024 * 1024:
                        attachment_paths.append(path)
                except Exception as e:
                    logger.warning("Скачивание вложения TG %s: %s", fid[:20] if isinstance(fid, str) else fid, e)
            if attachment_paths:
                from core.jira_wms import add_attachments_to_issue
                added, _ = await add_attachments_to_issue(issue_key, attachment_paths)
                if added:
                    display_text += f"\n\n📎 Приложено файлов: {added}."
                else:
                    logger.warning("TG WMS: add_attachments_to_issue не добавил файлы к %s", issue_key)
            elif file_ids:
                logger.warning("TG WMS: вложений было %s, скачано 0", len(file_ids))
        finally:
            for p in attachment_paths:
                try:
                    os.remove(p)
                except Exception:
                    pass
    await state.clear()
    await callback.message.edit_text(
        f"✅ {display_text}" if success else f"❌ {display_text}",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(callback.from_user.id),
    )


@router.message(WmsTicketStates.WAITING_FOR_DEPARTMENT, F.text)
async def wms_department(message: Message, state: FSMContext):
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    await state.update_data(department=(message.text or "").strip())
    data = await state.get_data()
    await state.clear()
    form_data = {
        "summary": data.get("summary", ""),
        "description": data.get("description", ""),
        "process": data.get("process", ""),
        "department": data.get("department", ""),
    }
    success, issue_key, msg = await support_api.create_ticket(CHANNEL_ID, message.from_user.id, "wms_issue", form_data)
    display_text = msg or issue_key
    if success:
        await message.reply(f"✅ {display_text}", parse_mode="HTML", reply_markup=get_main_menu_keyboard(message.from_user.id))
    else:
        await message.reply(f"❌ {display_text}", parse_mode="HTML", reply_markup=get_main_menu_keyboard(message.from_user.id))


# ---------- Lupa ----------
@router.callback_query(lambda c: c.data == "ticket_lupa_search")
async def ticket_lupa_start(callback: CallbackQuery, state: FSMContext):
    if not is_user_registered(callback.from_user.id):
        await callback.answer("Сначала пройдите регистрацию.", show_alert=True)
        return
    await state.clear()
    await state.set_state(LupaTicketStates.WAITING_FOR_DESCRIPTION)
    await state.update_data(ticket_type_id="lupa_search")
    await callback.message.edit_text(
        "🔍 <b>Поиск / сайт (Lupa)</b>\n\nОпишите проблему с поиском на petrovich.ru:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


@router.message(LupaTicketStates.WAITING_FOR_DESCRIPTION, F.text)
async def lupa_description(message: Message, state: FSMContext):
    """Шаг 4/5: ввод комментария (описание) → создание заявки."""
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.reply("Отменено.", reply_markup=get_main_menu_keyboard(message.from_user.id))
        return
    await state.update_data(description=(message.text or "").strip())
    data = await state.get_data()
    await state.clear()
    profile = get_user_profile(message.from_user.id) or {}
    subdivision = (data.get("subdivision") or profile.get("department") or "").strip()
    form_data = {
        "description": data.get("description", ""),
        "problematic_service": data.get("problematic_service", ""),
        "request_type": data.get("request_type", ""),
        "subdivision": subdivision,
        "city": data.get("city", ""),
    }
    success, issue_key, msg = await support_api.create_ticket(CHANNEL_ID, message.from_user.id, "lupa_search", form_data)
    display_text = msg or issue_key
    if success:
        await message.reply(f"✅ {display_text}", parse_mode="HTML", reply_markup=get_main_menu_keyboard(message.from_user.id))
    else:
        await message.reply(f"❌ {display_text}", parse_mode="HTML", reply_markup=get_main_menu_keyboard(message.from_user.id))
