"""
Регистрация и обновление учётных данных.
Вся логика в core для возможности вызова из Telegram и MAX.
"""
import logging
from typing import Tuple, Optional, Dict, Any

from user_storage import (
    get_user_profile,
    save_user_profile,
    check_login_or_email_taken,
    is_user_registered,
)
from validators import (
    validate_full_name,
    validate_work_login,
    validate_corporate_email,
    validate_phone,
    normalize_phone_display,
)

logger = logging.getLogger(__name__)


def register_user(
    user_id: int,
    full_name: str,
    login: str,
    email: str,
    phone: str,
    department: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Регистрирует пользователя. Проверяет дубликаты по логину и почте.
    department — подразделение из Jira (для заявки «Смена пароля» по JSM).
    Возвращает (успех, сообщение).
    """
    ok, msg = validate_full_name(full_name)
    if not ok:
        return False, msg
    ok, msg = validate_work_login(login)
    if not ok:
        return False, msg
    ok, msg = validate_corporate_email(email)
    if not ok:
        return False, msg
    ok, msg = validate_phone(phone)
    if not ok:
        return False, msg

    taken, taken_msg = check_login_or_email_taken(login, email, exclude_user_id=None)
    if taken:
        return False, taken_msg

    phone_norm = normalize_phone_display(phone)
    profile = {
        "full_name": full_name.strip(),
        "login": login.strip().lower(),
        "email": email.strip().lower(),
        "phone": phone_norm,
    }
    if department and department.strip():
        profile["department"] = department.strip()
    save_user_profile(user_id, profile)
    logger.info("Пользователь %s зарегистрирован: %s", user_id, login)
    return True, "Регистрация завершена."


def update_credentials(
    user_id: int,
    full_name: str,
    login: str,
    email: str,
    phone: str,
    department: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Обновляет учётные данные пользователя. Дубликаты по логину/почте не допускаются
    (кроме текущего user_id). department — подразделение для заявок JSM.
    """
    ok, msg = validate_full_name(full_name)
    if not ok:
        return False, msg
    ok, msg = validate_work_login(login)
    if not ok:
        return False, msg
    ok, msg = validate_corporate_email(email)
    if not ok:
        return False, msg
    ok, msg = validate_phone(phone)
    if not ok:
        return False, msg

    taken, taken_msg = check_login_or_email_taken(login, email, exclude_user_id=user_id)
    if taken:
        return False, taken_msg

    phone_norm = normalize_phone_display(phone)
    profile = {
        "full_name": full_name.strip(),
        "login": login.strip().lower(),
        "email": email.strip().lower(),
        "phone": phone_norm,
    }
    if department is not None:
        profile["department"] = department.strip() if department and department.strip() else ""
    else:
        old = get_user_profile(user_id)
        if old and "department" in old:
            profile["department"] = old.get("department", "")
    save_user_profile(user_id, profile)
    logger.info("Учётные данные обновлены для user_id=%s", user_id)
    return True, "Данные обновлены."


def get_profile_for_edit(user_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает профиль для отображения/редактирования или None."""
    return get_user_profile(user_id)
