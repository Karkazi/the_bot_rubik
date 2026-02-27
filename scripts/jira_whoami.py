"""
Печатает пользователя Jira (по JIRA_TOKEN) и проверяет право «Назначать исполнителя» в проекте AA.
Запуск: python scripts/jira_whoami.py
"""
import asyncio
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from config import CONFIG

PROJECT_KEY = "AA"
PERMISSION_ASSIGN = "ASSIGN_ISSUE"


async def main():
    jira = CONFIG.get("JIRA", {})
    base_url = (jira.get("LOGIN_URL") or "").strip().rstrip("/")
    token = (jira.get("TOKEN") or "").strip()
    if not base_url or not token:
        print("В .env задайте JIRA_LOGIN_URL и JIRA_TOKEN")
        return 1

    import aiohttp
    from urllib.parse import urljoin

    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    # 1. Текущий пользователь
    url_myself = urljoin(base_url + "/", "rest/api/2/myself")
    async with aiohttp.ClientSession() as session:
        async with session.get(url_myself, headers=headers, timeout=10) as resp:
            if resp.status != 200:
                print(f"Ошибка myself {resp.status}:", (await resp.text())[:500])
                return 1
            data = await resp.json()
    name = data.get("name") or data.get("key")
    display = data.get("displayName") or name
    email = data.get("emailAddress") or ""

    print("Токен принадлежит пользователю Jira:")
    print(f"  name (логин): {name}")
    print(f"  displayName:  {display}")
    if email:
        print(f"  email:       {email}")
    print()

    # 2. Права в проекте AA (Assign issues)
    # Jira Cloud требует параметр permissions; Server/DC поддерживает projectKey
    url_perm = urljoin(
        base_url + "/",
        f"rest/api/2/mypermissions?projectKey={PROJECT_KEY}&permissions={PERMISSION_ASSIGN}",
    )
    have_assign = None
    async with aiohttp.ClientSession() as session:
        async with session.get(url_perm, headers=headers, timeout=10) as resp:
            if resp.status != 200:
                print(f"Проверка прав в проекте {PROJECT_KEY}: запрос вернул {resp.status}")
                print("  (возможно, API mypermissions недоступен или параметры отличаются)")
            else:
                perm_data = await resp.json()
                # Формат: {"permissions": {"ASSIGN_ISSUE": {"havePermission": true, "name": "Assign Issues", ...}}}
                # или:   {"permissions": [{"key": "ASSIGN_ISSUE", "havePermission": true, ...}]}
                perms = perm_data.get("permissions")
                if isinstance(perms, dict) and PERMISSION_ASSIGN in perms:
                    have_assign = perms[PERMISSION_ASSIGN].get("havePermission")
                elif isinstance(perms, list):
                    for p in perms:
                        if p.get("key") == PERMISSION_ASSIGN:
                            have_assign = p.get("havePermission")
                            break

    if have_assign is True:
        print(f"Право «Назначать исполнителя» (Assign issues) в проекте {PROJECT_KEY}: да")
    elif have_assign is False:
        print(f"Право «Назначать исполнителя» (Assign issues) в проекте {PROJECT_KEY}: нет")
        print("Выдайте это право пользователю выше: Проект AA → Настройки → Права / Роли.")
    else:
        print(f"Право в проекте {PROJECT_KEY}: не удалось определить (проверьте mypermissions API).")

    # 3. Может ли целевой исполнитель (Robot_Scripts_PS) быть назначен в проекте AA?
    # Если он не в списке «Assignable Users», Jira вернёт 403 при попытке назначения.
    assignee_username = (CONFIG.get("JIRA_AA", {}) or {}).get("ASSIGNEE_USERNAME", "").strip() or "Robot_Scripts_PS"
    assignable_ok = None
    url_assignable = urljoin(
        base_url + "/",
        f"rest/api/2/user/assignable/search?project={PROJECT_KEY}&username={assignee_username}",
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url_assignable, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                users = await resp.json()
                assignable_ok = isinstance(users, list) and any(
                    (u.get("name") or u.get("key") or "").lower() == assignee_username.lower()
                    for u in users
                )
        if assignable_ok is None:
            url_multi = urljoin(
                base_url + "/",
                f"rest/api/2/user/assignable/multiProjectSearch?projectKeys={PROJECT_KEY}&query={assignee_username}",
            )
            async with session.get(url_multi, headers=headers, timeout=10) as r2:
                if r2.status == 200:
                    data2 = await r2.json()
                    list2 = data2 if isinstance(data2, list) else data2.get("values", data2.get("users", []))
                    assignable_ok = isinstance(list2, list) and any(
                        (u.get("name") or u.get("key") or "").lower() == assignee_username.lower()
                        for u in list2
                    )

    print()
    print(f"Исполнитель по умолчанию (JIRA_AA_ASSIGNEE_USERNAME): {assignee_username}")
    if assignable_ok is True:
        print(f"Пользователь «{assignee_username}» может быть назначен исполнителем в проекте {PROJECT_KEY}: да")
        if have_assign is True:
            print("Назначение через бота должно работать.")
    elif assignable_ok is False:
        print(f"Пользователь «{assignee_username}» может быть назначен исполнителем в проекте {PROJECT_KEY}: нет")
        print("Добавьте этого пользователя в роль с правом «Assignable User» в проекте AA:")
        print("  Проект AA → Настройки → Люди и роли → выберите роль (например Developers) → добавить пользователя.")
    else:
        print(f"Проверка «может ли {assignee_username} быть назначен»: не удалось (API assignable/search).")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
