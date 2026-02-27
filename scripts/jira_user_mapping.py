"""
Сопоставление пользователей бота с пользователями Jira по email и запись jira_username в базу.

Запуск:
  python scripts/jira_user_mapping.py

Результат:
  - В data/user_data.json для пользователей с найденным соответствием в Jira добавляется поле "jira_username".
  - В консоль выводится краткая статистика.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional, Dict, Any

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from config import CONFIG  # noqa: E402
from user_storage import load_user_db, save_user_db  # noqa: E402


async def _search_jira_user_by_email(session, base_url: str, headers: Dict[str, str], email: str) -> Optional[Dict[str, Any]]:
    """
    Ищет пользователя Jira по email.
    Сначала пробуем /user/search?query=..., затем (для совместимости) /user/search?username=...
    """
    from urllib.parse import urljoin, quote

    if not email:
        return None

    # Jira DC/Server часто ищет по email через username/ query в /user/search
    search_paths = [
        f"rest/api/2/user/search?query={quote(email)}",
        f"rest/api/2/user/search?username={quote(email)}",
    ]
    for rel in search_paths:
        url = urljoin(base_url + "/", rel)
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                if isinstance(data, list) and data:
                    # Берём первого кандидата, дополнительно сверим emailAddress
                    for u in data:
                        jira_email = (u.get("emailAddress") or "").strip().lower()
                        if jira_email == email.lower():
                            return u
                    # Если точного совпадения по email нет, вернём первого (для ручной проверки)
                    return data[0]
        except Exception:
            continue
    return None


async def main() -> int:
    jira = CONFIG.get("JIRA", {})
    base_url = (jira.get("LOGIN_URL") or "").strip().rstrip("/")
    token = (jira.get("TOKEN") or "").strip()
    if not base_url or not token:
        print("В .env задайте JIRA_LOGIN_URL и JIRA_TOKEN")
        return 1

    import aiohttp

    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    db = load_user_db()
    if not db:
        print("База пользователей (data/user_data.json) пуста или не найдена.")
        return 0

    updated = 0
    not_found = 0
    skipped_no_email = 0

    async with aiohttp.ClientSession() as session:
        for uid, profile in sorted(db.items(), key=lambda kv: int(kv[0])):
            email = (profile.get("email") or "").strip()
            if not email:
                skipped_no_email += 1
                continue

            jira_user = await _search_jira_user_by_email(session, base_url, headers, email)
            if not jira_user:
                not_found += 1
                continue

            jira_name = (jira_user.get("name") or jira_user.get("key") or "").strip()
            if not jira_name:
                not_found += 1
                continue

            # Запоминаем логин Jira в профиле
            profile["jira_username"] = jira_name
            db[uid] = profile
            updated += 1

    if updated:
        save_user_db(db)

    print(f"Профилей с установленным jira_username: {updated}")
    print(f"Пользователей без email (пропущено): {skipped_no_email}")
    print(f"Пользователей, не найденных в Jira по email: {not_found}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

