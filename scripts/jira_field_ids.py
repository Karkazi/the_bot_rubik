"""
Печатает ID полей Jira по их названию.

Использование (PowerShell):
  cd C:\\Users\\m.korolev\\PycharmProjects\\the_bot_rubik
  pip install -r requirements.txt
  python scripts\\jira_field_ids.py --query "AD account" --query "Existing phone number" --query "Password_new"

Берёт авторизацию из .env / переменных окружения:
  JIRA_LOGIN_URL (например https://jira.petrovich.tech)
  JIRA_TOKEN     (Bearer token)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any, Iterable

import requests
from dotenv import load_dotenv


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _iter_fields(base_url: str, token: str) -> list[dict[str, Any]]:
    url = base_url.rstrip("/") + "/rest/api/2/field"
    r = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Jira ответил {r.status_code}: {r.text[:500]}")
    data = r.json()
    if not isinstance(data, list):
        raise RuntimeError("Неожиданный формат ответа /field (ожидали list)")
    return data


def _iter_createmeta_fields(base_url: str, token: str, project_key: str, issuetype_name: str) -> dict[str, dict[str, Any]]:
    """
    Возвращает поля, доступные на экране создания задачи, через createmeta.
    Это часто надёжнее, чем общий список /field, если точное имя поля неизвестно.
    """
    url = base_url.rstrip("/") + "/rest/api/2/issue/createmeta"
    params = {
        "projectKeys": project_key,
        "issuetypeNames": issuetype_name,
        "expand": "projects.issuetypes.fields",
    }
    r = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        params=params,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Jira createmeta ответил {r.status_code}: {r.text[:500]}")
    data = r.json() or {}
    out: dict[str, dict[str, Any]] = {}
    for p in data.get("projects", []) or []:
        for it in p.get("issuetypes", []) or []:
            fields = it.get("fields") or {}
            for fid, f in fields.items():
                if fid and isinstance(f, dict):
                    out[fid] = f
    return out


def _get_project_issue_types(base_url: str, token: str, project_key: str) -> list[dict[str, Any]]:
    """Возвращает список типов задач (issuetypes) для проекта."""
    url = base_url.rstrip("/") + "/rest/api/2/issue/createmeta"
    params = {"projectKeys": project_key, "expand": "projects.issuetypes"}
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params=params,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Jira createmeta ответил {r.status_code}: {r.text[:500]}")
    data = r.json() or {}
    out: list[dict[str, Any]] = []
    for p in data.get("projects", []) or []:
        for it in p.get("issuetypes", []) or []:
            if it.get("id") and it.get("name"):
                out.append({"id": it.get("id"), "name": it.get("name"), "subtask": it.get("subtask")})
    return out


def _get_issue_with_names(base_url: str, token: str, issue_key: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + f"/rest/api/2/issue/{issue_key}"
    params = {"fields": "*all", "expand": "names"}
    r = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        params=params,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Jira issue ответил {r.status_code}: {r.text[:500]}")
    data = r.json() or {}
    if not isinstance(data, dict):
        raise RuntimeError("Неожиданный формат ответа issue (ожидали dict)")
    return data


def _extract_strings(value: Any, max_depth: int = 3) -> list[str]:
    """Достаёт строковые значения из вложенных структур Jira (dict/list)."""
    out: list[str] = []
    if max_depth < 0:
        return out
    if isinstance(value, str):
        out.append(value)
        return out
    if isinstance(value, dict):
        for v in value.values():
            out.extend(_extract_strings(v, max_depth=max_depth - 1))
        return out
    if isinstance(value, list):
        for v in value:
            out.extend(_extract_strings(v, max_depth=max_depth - 1))
        return out
    return out


def _match_queries(fields: Iterable[dict[str, Any]], queries: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {q: [] for q in queries}
    nqueries = [(_norm(q), q) for q in queries]
    for f in fields:
        name = f.get("name") or ""
        fid = f.get("id") or ""
        if not name or not fid:
            continue
        nname = _norm(name)
        for nq, q in nqueries:
            # допускаем частичное совпадение (на случай локализации/префиксов)
            if nq and (nq == nname or nq in nname):
                out[q].append(f)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="append", default=[], help="Название поля (или часть названия)")
    ap.add_argument("--use-createmeta", action="store_true", help="Искать среди полей экрана создания задачи (createmeta)")
    ap.add_argument("--project", default=os.getenv("JIRA_AA_PROJECT_KEY", "AA"), help="Ключ проекта (по умолчанию AA)")
    ap.add_argument("--issuetype", default=os.getenv("JIRA_AA_ISSUE_TYPE", "Task"), help="Тип задачи (по умолчанию Task)")
    ap.add_argument("--limit", type=int, default=30, help="Сколько совпадений показывать на запрос (по умолчанию 30)")
    ap.add_argument(
        "--list-unique-regex",
        action="store_true",
        help="Показать все поля типа unique-regex (часто используются для логинов/телефонов/паролей)",
    )
    ap.add_argument(
        "--issue",
        default="",
        help="Ключ задачи (например AA-78207). Если задан — попробуем определить поле логина (AD account) по значению в задаче.",
    )
    ap.add_argument(
        "--list-issue-types",
        action="store_true",
        help="Показать доступные типы задач (issuetype) для проекта (для JIRA_AA_ISSUE_TYPE).",
    )
    args = ap.parse_args()

    # Подхватываем переменные из .env (если есть)
    load_dotenv()

    queries = args.query or []
    if not queries and not args.list_unique_regex and not args.issue and not args.list_issue_types:
        print("Передайте хотя бы один --query (или --list-unique-regex / --issue / --list-issue-types)", file=sys.stderr)
        return 2

    base_url = (os.getenv("JIRA_LOGIN_URL") or "https://jira.petrovich.tech").strip()
    token = (os.getenv("JIRA_TOKEN") or "").strip()
    if not token:
        print("Не найден JIRA_TOKEN в окружении/.env", file=sys.stderr)
        return 2

    # Список типов задач для проекта AA (для настройки JIRA_AA_ISSUE_TYPE)
    if args.list_issue_types:
        try:
            types_list = _get_project_issue_types(base_url, token, args.project)
        except Exception as e:
            print(f"Ошибка запроса createmeta: {e}", file=sys.stderr)
            return 1
        print(f"Jira: {base_url}")
        print(f"Проект: {args.project}")
        print("Доступные типы задач. Для .env используйте JIRA_AA_ISSUE_TYPE=имя или JIRA_AA_ISSUE_TYPE_ID=id:")
        for t in types_list:
            subtask = " (subtask)" if t.get("subtask") else ""
            print(f"  id={t.get('id')}  name={t.get('name')!r}{subtask}")
        return 0

    # Если задана задача — определяем поле, где лежит AD логин, по форме значения (i.ivanov)
    if args.issue:
        try:
            issue = _get_issue_with_names(base_url, token, args.issue.strip())
        except Exception as e:
            print(f"Ошибка запроса issue {args.issue}: {e}", file=sys.stderr)
            return 1

        names = issue.get("names") or {}
        fields_obj = issue.get("fields") or {}
        strict_login_re = re.compile(r"^[a-z][a-z0-9._-]*\\.[a-z][a-z0-9._-]*$", re.IGNORECASE)
        loose_login_re = re.compile(r"^[A-Za-z0-9._\\\\-]+$")

        candidates: list[tuple[str, str]] = []
        for fid, val in fields_obj.items():
            strings = [s.strip() for s in _extract_strings(val) if isinstance(s, str)]
            strings = [s for s in strings if s]
            def looks_like_login(s: str) -> bool:
                if len(s) < 3 or len(s) > 64:
                    return False
                if "@" in s or "/" in s or " " in s or ":" in s:
                    return False
                if "." not in s:
                    return False
                if s.lower().startswith("http"):
                    return False
                if not loose_login_re.match(s):
                    return False
                return True

            if any(strict_login_re.match(s) or looks_like_login(s) for s in strings):
                fname = names.get(fid) if isinstance(names, dict) else None
                candidates.append((fid, str(fname or "")))

        print(f"Jira: {base_url}")
        print(f"Issue: {args.issue.strip()}")
        if candidates:
            print("Кандидаты на поле AD account (логин) по значению (эвристика логина вида i.ivanov):")
            for fid, fname in candidates[: args.limit]:
                print(f"- id: {fid}\n  name: {fname}")
            print()

        # Дополнительно: поиск по названию полей внутри issue (expand=names)
        if queries and isinstance(names, dict):
            print("Совпадения по названию поля (expand=names):")
            qn = [(_norm(q), q) for q in queries]
            found_any = False
            for fid, fname in names.items():
                if not isinstance(fname, str):
                    continue
                nfname = _norm(fname)
                for nq, q in qn:
                    if nq and (nq == nfname or nq in nfname):
                        found_any = True
                        print(f"- id: {fid}\n  name: {fname}")
                        break
            if not found_any:
                print("Ничего не найдено по заданным --query.")
            print()

        if not candidates and not queries:
            print("Не удалось автоматически найти поле логина по шаблону i.ivanov в этой задаче.")
            print("Попробуйте: python scripts\\\\jira_field_ids.py --issue AA-78207 --query \"AD\" --query \"account\"")
        return 0

    try:
        if args.use_createmeta:
            cm = _iter_createmeta_fields(base_url, token, args.project, args.issuetype)
            fields = [{"id": fid, "name": (f.get("name") or ""), "custom": f.get("custom"), "schema": f.get("schema")} for fid, f in cm.items()]
        else:
            fields = _iter_fields(base_url, token)
    except Exception as e:
        print(f"Ошибка запроса к Jira: {e}", file=sys.stderr)
        return 1

    matches = _match_queries(fields, queries)

    print(f"Jira: {base_url}")
    print(f"Всего полей: {len(fields)}")
    print()

    if args.list_unique_regex:
        uniq = []
        for f in fields:
            schema = f.get("schema") or {}
            custom = ""
            if isinstance(schema, dict):
                custom = str(schema.get("custom") or "")
            if "uniqueregexfield" in custom.lower() or "unique-regex" in custom.lower():
                uniq.append(f)
        print("=== UNIQUE REGEX FIELDS ===")
        if not uniq:
            print("Не найдено полей unique-regex.")
        else:
            print(f"Найдено: {len(uniq)}. Показываю первые {args.limit}.")
            for i, f in enumerate(uniq):
                if i >= args.limit:
                    break
                print(f"- id: {f.get('id')}\n  name: {f.get('name')}\n  schema: {f.get('schema')}")
        print()

    for q in queries:
        found = matches.get(q) or []
        print(f"=== QUERY: {q} ===")
        if not found:
            print("Ничего не найдено. Попробуйте другой кусок имени поля (без регистра).")
            print()
            continue
        if len(found) > args.limit:
            print(f"Совпадений: {len(found)}. Показываю первые {args.limit}.")
        for i, f in enumerate(found):
            if i >= args.limit:
                break
            # Пример элемента: {"id":"customfield_12345","name":"AD account", ...}
            print(f"- id: {f.get('id')}\n  name: {f.get('name')}\n  custom: {f.get('custom')}\n  schema: {f.get('schema')}")
        print()

    # Дополнительно: подсказка по тому, что нужно вставить в .env
    print("Подсказка для .env (подставьте реальные id из вывода):")
    print("  JIRA_AA_FIELD_AD_ACCOUNT=customfield_XXXXX")
    print("  JIRA_AA_FIELD_EXISTING_PHONE=customfield_XXXXX")
    print("  JIRA_AA_FIELD_PASSWORD_NEW=customfield_XXXXX")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

