"""
Пошаговое создание заявки Lupa (Сайт / поиск petrovich.ru) в MAX.
Кнопки и логика — как в the_bot_lupa и TG: сервис → тип запроса → город → комментарий (подразделение из профиля).
"""
import logging
from typing import Optional

from user_storage import (
    is_user_registered,
    get_user_profile,
    save_user_profile,
    resolve_channel_user_id,
    check_employee_id_taken,
)

logger = logging.getLogger(__name__)
CHANNEL_ID = "max"

# user_id (MAX) -> { step, data }
_flow: dict[int, dict] = {}

CANCEL_BTN = [{"id": "cancel", "label": "❌ Отмена"}]

# Значения для Jira (как в the_bot_lupa и keyboards.LUPA_*)
LUPA_SERVICE_VALUES = {"lupa_service_app": "Приложение", "lupa_service_site": "Сайт (petrovich.ru)"}
LUPA_REQUEST_TYPE_VALUES = {
    "lupa_request_search_issue": "проблемы с поиском",
    "lupa_request_search_question": "вопросы по работе поиска",
    "lupa_request_discount": "валидация сленга",
}

# Кнопки в формате MAX (id, label)
LUPA_SERVICE_BUTTONS = [
    {"id": "lupa_service_app", "label": "📱 Приложение"},
    {"id": "lupa_service_site", "label": "🌐 Сайт (petrovich.ru)"},
]
LUPA_REQUEST_TYPE_BUTTONS = [
    {"id": "lupa_request_search_issue", "label": "🔍 Проблемы с поиском"},
    {"id": "lupa_request_search_question", "label": "❓ Вопросы по работе поиска"},
    {"id": "lupa_request_discount", "label": "✅ Валидация сленга"},
]

EMPLOYEE_ID_HINT = (
    "💡 Табельный номер можно найти в расчётном листке. Он нужен для идентификации в заявке."
)


def _city_buttons() -> list:
    """Кнопки городов (первые 4 из конфига) + «Ввести вручную», как the_bot_lupa."""
    from config import CONFIG
    cities = CONFIG.get("JIRA_LUPA", {}).get("CITIES", [])[:4]
    buttons = []
    for i in range(0, min(4, len(cities)), 2):
        row = []
        for j in range(2):
            if i + j < len(cities):
                city = cities[i + j]
                row.append({"id": f"lupa_city_{city.replace(' ', '_')}", "label": city})
        if row:
            buttons.extend(row)
    buttons.append({"id": "lupa_city_manual", "label": "✏️ Ввести вручную"})
    return buttons


def is_in_lupa_flow(user_id: int) -> bool:
    return user_id in _flow


async def start_lupa(user_id: int) -> Optional[dict]:
    """
    Начало сценария Lupa. Если нет employee_id — запрос табельного; иначе шаг 1 — выбор сервиса (кнопки).
    """
    if not is_user_registered(user_id, CHANNEL_ID):
        return None
    _flow.pop(user_id, None)
    profile = get_user_profile(user_id, CHANNEL_ID) or {}
    employee_id = (profile.get("employee_id") or "").strip()
    if employee_id:
        _flow[user_id] = {"step": "service", "data": {"ticket_type_id": "lupa_search"}}
        return {
            "text": "🔍 <b>Создание заявки о поиске</b>\n\nЛупа начинает! Шаг 1/5: Выберите проблемный сервис:",
            "parse_mode": "HTML",
            "buttons": LUPA_SERVICE_BUTTONS + CANCEL_BTN,
        }
    _flow[user_id] = {"step": "employee_id", "data": {"ticket_type_id": "lupa_search"}}
    return {
        "text": (
            "🌐 <b>Сайт (Lupa)</b>\n\n"
            "Укажите ваш <b>табельный номер</b> (например: 0000000311):\n\n"
            f"{EMPLOYEE_ID_HINT}"
        ),
        "parse_mode": "HTML",
        "buttons": CANCEL_BTN,
    }


def handle_lupa_callback(user_id: int, callback_id: str) -> Optional[dict]:
    """Обработка callback в сценарии Lupa: cancel, lupa_service_*, lupa_request_*, lupa_city_*, lupa_skip_comment."""
    state = _flow.get(user_id)
    if not state:
        return None

    if callback_id == "cancel":
        _flow.pop(user_id, None)
        from adapters.max.handlers import handle_main_menu
        return handle_main_menu(user_id)

    step = state.get("step")
    data = state.get("data", {})

    # Шаг 1: выбор сервиса
    if step == "service" and callback_id in LUPA_SERVICE_VALUES:
        service = LUPA_SERVICE_VALUES[callback_id]
        data["problematic_service"] = service
        state["data"] = data
        state["step"] = "request_type"
        return {
            "text": f"🔍 <b>Создание заявки о поиске</b>\n\n✅ Сервис: {service}\n\nШаг 2/5: Выберите тип запроса:",
            "parse_mode": "HTML",
            "buttons": LUPA_REQUEST_TYPE_BUTTONS + CANCEL_BTN,
        }

    # Шаг 2: выбор типа запроса
    if step == "request_type" and callback_id in LUPA_REQUEST_TYPE_VALUES:
        request_type = LUPA_REQUEST_TYPE_VALUES[callback_id]
        data["request_type"] = request_type
        profile = get_user_profile(user_id, CHANNEL_ID) or {}
        data["subdivision"] = (profile.get("department") or "").strip()
        state["data"] = data
        state["step"] = "city"
        subdiv = data.get("subdivision") or "не указано"
        return {
            "text": (
                "🔍 <b>Создание заявки о поиске</b>\n\n"
                f"✅ Тип запроса: {request_type}\n"
                f"✅ Подразделение: {subdiv}\n\n"
                "Шаг 3/5: Укажите город:"
            ),
            "parse_mode": "HTML",
            "buttons": _city_buttons() + CANCEL_BTN,
        }

    # Шаг 3: выбор города
    if step == "city" and callback_id.startswith("lupa_city_"):
        if callback_id == "lupa_city_manual":
            state["step"] = "city_manual"
            return {
                "text": "🔍 <b>Создание заявки о поиске</b>\n\nШаг 3/5: Введите название города:",
                "parse_mode": "HTML",
                "buttons": CANCEL_BTN,
            }
        city = callback_id.replace("lupa_city_", "", 1).replace("_", " ")
        data["city"] = city
        state["data"] = data
        state["step"] = "description"
        return {
            "text": (
                f"🔍 <b>Создание заявки о поиске</b>\n\n✅ Город: {city}\n\n"
                "Шаг 4/5: Введите комментарий (описание проблемы). Можно пропустить, нажав кнопку ниже."
            ),
            "parse_mode": "HTML",
            "buttons": [{"id": "lupa_skip_comment", "label": "⏭ Пропустить комментарий"}, {"id": "cancel", "label": "❌ Отмена"}],
        }

    # Шаг 4: пропуск комментария → создание
    if step == "description" and callback_id == "lupa_skip_comment":
        data["description"] = ""
        profile = get_user_profile(user_id, CHANNEL_ID) or {}
        subdivision = (data.get("subdivision") or profile.get("department") or "").strip()
        form_data = {
            "description": data.get("description", ""),
            "problematic_service": data.get("problematic_service", ""),
            "request_type": data.get("request_type", ""),
            "subdivision": subdivision,
            "city": data.get("city", ""),
        }
        _flow.pop(user_id, None)
        return {"create_ticket": {"ticket_type_id": "lupa_search", "form_data": form_data}}

    return None


async def handle_lupa_message(user_id: int, text: str) -> Optional[dict]:
    """Обработка текста: employee_id, город (вручную), комментарий → создание."""
    state = _flow.get(user_id)
    if not state:
        return None
    step = state.get("step")
    data = state.get("data", {})

    if (text or "").strip().lower() in ("отмена", "cancel", "/cancel"):
        _flow.pop(user_id, None)
        from adapters.max.handlers import handle_main_menu
        return handle_main_menu(user_id)

    text_val = (text or "").strip()

    if step == "employee_id":
        from validators import validate_employee_id
        ok, err = validate_employee_id(text_val)
        if not ok:
            return {"text": f"❗ {err}\n\n{EMPLOYEE_ID_HINT}", "parse_mode": "HTML", "buttons": CANCEL_BTN}
        primary = resolve_channel_user_id(CHANNEL_ID, user_id)
        taken, _ = check_employee_id_taken(text_val, exclude_user_id=primary)
        if taken:
            return {
                "text": "❗ Этот табельный номер уже привязан к другому пользователю. Введите другой номер или нажмите Отмена.",
                "parse_mode": "HTML",
                "buttons": CANCEL_BTN,
            }
        profile = get_user_profile(user_id, CHANNEL_ID) or {}
        profile["employee_id"] = text_val
        save_user_profile(primary, profile)
        _flow[user_id] = {"step": "service", "data": {**data}}
        return {
            "text": "🔍 <b>Создание заявки о поиске</b>\n\nЛупа начинает! Шаг 1/5: Выберите проблемный сервис:",
            "parse_mode": "HTML",
            "buttons": LUPA_SERVICE_BUTTONS + CANCEL_BTN,
        }

    if step == "city_manual":
        if not text_val:
            return {"text": "Введите название города или нажмите Отмена.", "parse_mode": "HTML", "buttons": CANCEL_BTN}
        data["city"] = text_val
        state["data"] = data
        state["step"] = "description"
        return {
            "text": f"✅ Город: {text_val}\n\nШаг 4/5: Введите комментарий (описание проблемы). Можно пропустить, нажав кнопку ниже.",
            "parse_mode": "HTML",
            "buttons": [{"id": "lupa_skip_comment", "label": "⏭ Пропустить комментарий"}, {"id": "cancel", "label": "❌ Отмена"}],
        }

    if step == "description":
        data["description"] = text_val
        profile = get_user_profile(user_id, CHANNEL_ID) or {}
        subdivision = (data.get("subdivision") or profile.get("department") or "").strip()
        form_data = {
            "description": data.get("description", ""),
            "problematic_service": data.get("problematic_service", ""),
            "request_type": data.get("request_type", ""),
            "subdivision": subdivision,
            "city": data.get("city", ""),
        }
        _flow.pop(user_id, None)
        return {"create_ticket": {"ticket_type_id": "lupa_search", "form_data": form_data}}

    return None
