"""
Проставляет тип запроса «Смена пароля» у уже созданной задачи.

Использование (из корня проекта):
  python scripts/set_request_type.py AA-78686 --from AA-78683   # скопировать тип из AA-78683
  python scripts/set_request_type.py AA-78686                   # попробовать стандартные форматы
  python scripts/set_request_type.py AA-78686 "Смена пароля"
  python scripts/set_request_type.py AA-78686 --editmeta        # показать, какие поля доступны для редактирования

Берёт JIRA_LOGIN_URL и JIRA_TOKEN из .env.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from config import load_config
from core.jira_aa import get_issue_editmeta, get_issue_request_type_value, update_issue_request_type


async def main() -> None:
    parser = argparse.ArgumentParser(description="Установить тип запроса у задачи Jira AA")
    parser.add_argument("issue_key", help="Ключ задачи (например AA-78686)")
    parser.add_argument("value", nargs="?", help="Значение типа (например «Смена пароля»)")
    parser.add_argument("--from", dest="from_issue", metavar="KEY", help="Скопировать значение типа из другой задачи (например AA-78683)")
    parser.add_argument("--editmeta", action="store_true", help="Показать editmeta (поля, доступные для редактирования)")
    args = parser.parse_args()

    issue_key = args.issue_key.strip()

    if args.editmeta:
        meta = await get_issue_editmeta(issue_key)
        fields = meta.get("fields") or {}
        rt_field = "customfield_10500"
        if rt_field in fields:
            print(f"Поле {rt_field} в editmeta: да")
            print(json.dumps(fields[rt_field], indent=2, ensure_ascii=False))
        else:
            print(f"Поле {rt_field} в editmeta: нет (не доступно для редактирования через REST)")
        print("Все поля editmeta:", list(fields.keys()))
        return

    value = args.value.strip() if args.value else None
    ok = await update_issue_request_type(
        issue_key,
        value=value,
        source_issue_key=args.from_issue.strip() if args.from_issue else None,
    )
    print("OK" if ok else "Ошибка: тип запроса не установлен")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    load_config()
    asyncio.run(main())
