"""
Получить ID опций поля «WMS failed process» (customfield_13803) из Jira для JIRA_WMS_PROCESS_OPTION_IDS.

Использование:
  python scripts/get_wms_process_option_ids.py
  python scripts/get_wms_process_option_ids.py --project PW --field customfield_13803

Требует JIRA_LOGIN_URL и JIRA_TOKEN в .env.
Выводит список опций (id и название) и готовую строку для .env.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

# Ключи процессов в боте (core/wms_constants.WMS_PROCESSES)
WMS_PROCESSES = {
    "proc_placement": "Размещение",
    "proc_reserve": "Резерв",
    "proc_receiving": "Приемка",
    "proc_pick": "Отбор",
    "proc_control": "Контроль",
    "proc_shipment": "Отгрузка",
    "proc_replenishment": "Пополнение",
    "proc_inventory": "Инвентаризация",
    "proc_app": "Приложение WMS",
    "proc_report": "Проблемы с отчетом WMS",
    "proc_assembly": "Сборка",
    "proc_other": "Другое",
}


def _normalize(s: str) -> str:
    """Приведение к одному регистру и пробелам для сравнения названий (ё -> е для сопоставления Приёмка/Приемка)."""
    s = (s or "").strip().lower().replace("  ", " ")
    return s.replace("ё", "е")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Get option IDs for WMS process field (customfield_13803) from Jira createmeta"
    )
    parser.add_argument("--project", default="PW", help="Project key (default: PW)")
    parser.add_argument("--field", default="customfield_13803", help="Field id (default: customfield_13803)")
    parser.add_argument("--issuetype", default="", help="Issue type name filter (e.g. Ошибка). If empty, first issuetype with field is used.")
    args = parser.parse_args()

    base_url = (__import__("os").getenv("JIRA_LOGIN_URL") or "").strip().rstrip("/")
    token = (__import__("os").getenv("JIRA_TOKEN") or "").strip()
    if not base_url or not token:
        print("Задайте JIRA_LOGIN_URL и JIRA_TOKEN в .env")
        return 1

    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    url = f"{base_url}/rest/api/2/issue/createmeta"
    params = {"projectKeys": args.project, "expand": "projects.issuetypes.fields"}

    print(f"\n--- Опции поля {args.field} (проект {args.project}) ---\n")
    r = requests.get(url, headers=headers, params=params, timeout=30)
    if r.status_code != 200:
        print(f"Ошибка {r.status_code}: {r.text[:500]}")
        return 1

    data = r.json()
    options_by_id: dict[str, str] = {}
    options_by_name: dict[str, str] = {}
    field_name = args.field

    for project in data.get("projects", []):
        if (project.get("key") or "").strip() != args.project:
            continue
        for it in project.get("issuetypes", []):
            it_name = (it.get("name") or "").strip()
            if args.issuetype and _normalize(it_name) != _normalize(args.issuetype):
                continue
            fields = it.get("fields", {})
            if args.field not in fields:
                continue
            field_info = fields[args.field]
            field_name = field_info.get("name") or args.field
            allowed = field_info.get("allowedValues", [])
            for v in allowed:
                if not isinstance(v, dict):
                    continue
                opt_id = v.get("id")
                opt_value = (v.get("value") or v.get("name") or "").strip()
                if opt_id is not None and opt_value:
                    options_by_id[str(opt_id)] = opt_value
                    options_by_name[_normalize(opt_value)] = str(opt_id)
            if options_by_id:
                break
        if options_by_id:
            break

    if not options_by_id:
        print(f"Поле {args.field} не найдено в createmeta или у него нет allowedValues.")
        print("Проверьте проект и тип задачи (--project PW --issuetype Ошибка).")
        return 1

    print(f"Поле: {field_name}\n")
    print("ID опции -> Название:")
    for oid, name in sorted(options_by_id.items(), key=lambda x: x[1]):
        print(f"  {oid} -> {name}")

    # Сопоставление с WMS_PROCESSES: по названию подбираем id
    mapping = {}
    for key, bot_name in WMS_PROCESSES.items():
        bn = _normalize(bot_name)
        if bn in options_by_name:
            mapping[key] = options_by_name[bn]
        else:
            # Попытка частичного совпадения
            for jira_name_norm, oid in options_by_name.items():
                if bn in jira_name_norm or jira_name_norm in bn:
                    mapping[key] = oid
                    break

    print("\n--- Сопоставление с ключами бота (WMS_PROCESSES) ---\n")
    for key in WMS_PROCESSES:
        name = WMS_PROCESSES[key]
        oid = mapping.get(key)
        status = f"  -> id={oid}" if oid else "  (не найдено в Jira)"
        print(f"  {key} ({name}){status}")

    if mapping:
        env_json = json.dumps(mapping, ensure_ascii=False)
        print("\n--- Строка для .env ---\n")
        print(f"JIRA_WMS_PROCESS_OPTION_IDS={env_json}")
    else:
        print("\nНе удалось сопоставить ни одну опцию. Проверьте названия в Jira и в core/wms_constants.WMS_PROCESSES.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
