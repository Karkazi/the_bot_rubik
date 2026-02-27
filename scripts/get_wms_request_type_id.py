"""
Получить JIRA_WMS_REQUEST_TYPE_ID для типа «Проблема в работе WMS» (Type: Ошибка).

Анализ задачи PW-25774 и список типов запросов Service Desk 31 (PW).
Использование:
  python scripts/get_wms_request_type_id.py
  python scripts/get_wms_request_type_id.py --issue PW-25774

Требует JIRA_LOGIN_URL и JIRA_TOKEN в .env.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# корень проекта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Get JIRA_WMS_REQUEST_TYPE_ID from Jira (PW-25774 and servicedesk 31)")
    parser.add_argument("--issue", default="PW-25774", help="Issue key to inspect (default: PW-25774)")
    parser.add_argument("--servicedesk", default="31", help="Service desk ID (default: 31)")
    args = parser.parse_args()

    base_url = (__import__("os").getenv("JIRA_LOGIN_URL") or "").strip().rstrip("/")
    token = (__import__("os").getenv("JIRA_TOKEN") or "").strip()
    if not base_url or not token:
        print("Задайте JIRA_LOGIN_URL и JIRA_TOKEN в .env")
        return 1

    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}

    # 1) Задача PW-25774: issuetype и поле Request type (customfield_10500)
    print(f"\n--- Задача {args.issue} ---")
    issue_url = f"{base_url}/rest/api/2/issue/{args.issue}"
    r = requests.get(
        issue_url,
        headers=headers,
        params={"fields": "summary,issuetype,customfield_10500"},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"Ошибка {r.status_code}: {r.text[:400]}")
    else:
        data = r.json()
        fields = data.get("fields") or {}
        summary = (fields.get("summary") or "").strip()
        it = fields.get("issuetype") or {}
        issue_type_name = (it.get("name") or "").strip()
        issue_type_id = it.get("id") or ""
        rt = fields.get("customfield_10500")
        rt_id = rt_id_from_field(rt)
        rt_name = name_from_request_type_field(rt)
        print(f"  Summary: {summary}")
        print(f"  Type (issuetype): {issue_type_name} (id={issue_type_id})")
        print(f"  Request type (customfield_10500): {rt_name or '—'} (id={rt_id or '—'})")
        if rt_id:
            print(f"\n  -> JIRA_WMS_REQUEST_TYPE_ID={rt_id}")

    # 2) Список типов запросов Service Desk
    print(f"\n--- Типы запросов Service Desk (servicedeskId={args.servicedesk}) ---")
    sd_url = f"{base_url}/rest/servicedeskapi/servicedesk/{args.servicedesk}/requesttype"
    r2 = requests.get(sd_url, headers=headers, timeout=15)
    if r2.status_code != 200:
        print(f"Ошибка {r2.status_code}: {r2.text[:400]}")
        return 1

    data2 = r2.json()
    values = data2.get("values") or []
    # Получить имена типов задач по issueTypeId (из проекта PW)
    issue_type_id_to_name = fetch_issue_type_names(base_url, token, "PW")

    found_issue = None
    found_psi = None
    for v in values:
        rt_id = str(v.get("id") or "")
        name = (v.get("name") or "").strip()
        issue_type_id_rt = str(v.get("issueTypeId") or "")
        issue_type_name_rt = issue_type_id_to_name.get(issue_type_id_rt) or f"id={issue_type_id_rt}"
        print(f"  id={rt_id}: name={name!r}, issueType={issue_type_name_rt}")
        if name == "Проблема в работе WMS" or (
            "проблема" in name.lower() and "wms" in name.lower()
        ):
            found_issue = rt_id
        if issue_type_name_rt == "Ошибка" and not found_issue and "wms" in name.lower():
            found_issue = rt_id
        if "пользователь" in name.lower() and "psi" in name.lower():
            found_psi = rt_id
        if not found_psi and ("psi" in name.lower() and "wms" in name.lower()):
            found_psi = rt_id

    print("\n--- Рекомендуемые переменные для .env ---")
    if found_issue:
        print(f"  JIRA_WMS_REQUEST_TYPE_ID={found_issue}   # Проблема в работе WMS (Type: Ошибка)")
    if found_psi:
        print(f"  JIRA_WMS_REQUEST_TYPE_ID_PSI_USER={found_psi}   # Создать/изменить/удалить пользователя PSIwms (Type: Поддержка)")
    if found_issue or found_psi:
        print("\nДобавьте нужные строки в .env")
    if not found_psi:
        print("  Тип «Пользователь PSIwms» не найден автоматически; найдите в списке выше id типа с именем вроде «Создать/изменить/удалить пользователя PSIwms» и задайте JIRA_WMS_REQUEST_TYPE_ID_PSI_USER=<id>.")
    return 0


def rt_id_from_field(rt: object) -> str | None:
    if rt is None:
        return None
    if isinstance(rt, dict):
        return str(rt.get("id") or rt.get("requestTypeId") or "")
    return str(rt) if rt else None


def name_from_request_type_field(rt: object) -> str:
    if rt is None or not isinstance(rt, dict):
        return ""
    return (rt.get("name") or rt.get("value") or "").strip()


def fetch_issue_type_names(base_url: str, token: str, project_key: str) -> dict[str, str]:
    """Возвращает {issue_type_id: name} для проекта."""
    url = f"{base_url}/rest/api/2/issue/createmeta"
    r = requests.get(
        url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        params={"projectKeys": project_key, "expand": "projects.issuetypes"},
        timeout=15,
    )
    out = {}
    if r.status_code != 200:
        return out
    data = r.json()
    for proj in data.get("projects") or []:
        for it in proj.get("issuetypes") or []:
            iid = str(it.get("id") or "")
            name = (it.get("name") or "").strip()
            if iid:
                out[iid] = name
    return out


if __name__ == "__main__":
    sys.exit(main())
