import json
from pathlib import Path

from user_storage import load_user_db, save_user_db


def migrate_from_lupa(lupa_path: Path) -> None:
    if not lupa_path.is_file():
        raise SystemExit(f"Файл Лупы не найден: {lupa_path}")

    with lupa_path.open("r", encoding="utf-8") as f:
        lupa_db = json.load(f)

    rubik_db = load_user_db()
    added = 0
    marked_existing = 0

    for uid, profile in lupa_db.items():
        uid = str(uid)
        email = (profile.get("email") or "").strip()
        login = ""
        if "@" in email:
            login = email.split("@", 1)[0].strip().lower()

        if uid in rubik_db:
            # Профиль уже есть в Rubik — только помечаем, что нужен пересбор телефона
            prof = rubik_db.get(uid) or {}
            prof.setdefault("full_name", profile.get("full_name") or prof.get("full_name") or "")
            prof.setdefault("email", email or prof.get("email") or "")
            if login and not prof.get("login"):
                prof["login"] = login
            # Флаг для запроса актуального номера телефона при следующем входе
            prof["phone_needs_verification"] = True
            rubik_db[uid] = prof
            marked_existing += 1
            continue

        rubik_db[uid] = {
            "full_name": profile.get("full_name") or "",
            "login": login,
            "email": email,
            "phone": profile.get("phone") or "",
            "department": profile.get("subdivision") or "",
            "department_wms": "",
            "employee_id": profile.get("employee_id") or "",
            # Новый профиль из Лупы — просим пользователя подтвердить номер телефона
            "phone_needs_verification": True,
        }
        added += 1

    save_user_db(rubik_db)
    print(f"Добавлено профилей из Лупы: {added}")
    print(f"Помечено существующих профилей для проверки телефона: {marked_existing}")
    print(f"Итого профилей в Rubik: {len(rubik_db)}")


if __name__ == "__main__":
    default_path = Path("/root/the_bot_lupa/data/user_data.json")
    migrate_from_lupa(default_path)

