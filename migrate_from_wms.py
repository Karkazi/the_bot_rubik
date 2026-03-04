import json
from pathlib import Path

from user_storage import load_user_db, save_user_db


def migrate_from_wms(wms_path: Path) -> None:
    """
    Импорт одобренных заявок регистрации из the_bot_wms в базу Rubik.
    - Берём только status == "approved"
    - Для каждого user_id оставляем последнюю по порядку запись
    - Для всех помечаем phone_needs_verification = True
    """
    if not wms_path.is_file():
        raise SystemExit(f"Файл WMS не найден: {wms_path}")

    with wms_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    requests = payload.get("requests") or []
    latest_by_user: dict[str, dict] = {}

    for req in requests:
        if not isinstance(req, dict):
            continue
        status = (req.get("status") or "").strip().lower()
        if status != "approved":
            # Пропускаем заявки без подтверждения регистрации
            continue
        uid_raw = req.get("user_id")
        if uid_raw is None:
            continue
        uid = str(uid_raw).strip()
        if not uid:
            continue
        # Последняя по файлу заявка для user_id считается актуальной
        latest_by_user[uid] = req

    rubik_db = load_user_db()
    added = 0
    updated = 0

    for uid, req in latest_by_user.items():
        full_name = req.get("full_name") or ""
        phone = req.get("phone") or ""
        email = (req.get("email") or "").strip()
        department_wms = req.get("department") or ""

        login = ""
        if "@" in email:
            login = email.split("@", 1)[0].strip().lower()

        profile = rubik_db.get(uid) or {}
        is_new = not bool(profile)

        if is_new:
            profile = {
                "full_name": full_name,
                "login": login,
                "email": email,
                "phone": phone,
                # Для новых пользователей дублируем подразделение в оба поля
                "department": department_wms,
                "department_wms": department_wms,
                "employee_id": "",
            }
            added += 1
        else:
            # Аккуратное обновление существующего профиля
            if full_name and not profile.get("full_name"):
                profile["full_name"] = full_name
            if email and not profile.get("email"):
                profile["email"] = email
            if login and not profile.get("login"):
                profile["login"] = login
            if department_wms:
                # WMS-подразделение считаем более точным для department_wms
                profile["department_wms"] = department_wms
            updated += 1

        # Во всех случаях просим пользователя подтвердить актуальный номер телефона
        profile["phone_needs_verification"] = True
        rubik_db[uid] = profile

    save_user_db(rubik_db)
    print(f"Добавлено профилей из WMS: {added}")
    print(f"Обновлено существующих профилей из WMS: {updated}")
    print(f"Итого профилей в Rubik: {len(rubik_db)}")


if __name__ == "__main__":
    default_path = Path("/root/the_bot_wms/data/registration_requests.json")
    migrate_from_wms(default_path)

