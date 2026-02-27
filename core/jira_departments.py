"""
Список подразделений (Department) из Jira для выбора при регистрации.
Как в the_bot_lupa: createmeta по проекту AA и типу «Задача», поле customfield_11406 (allowedValues).
Кэш в памяти и в файле, TTL 1 час.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from urllib.parse import urljoin

from config import CONFIG

logger = logging.getLogger(__name__)

CACHE_TTL = 3600
_cache: Optional[Dict[str, Any]] = None


def _cache_path() -> Path:
    p = Path(__file__).resolve().parent.parent / "data" / "departments_cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_file_cache() -> Optional[List[str]]:
    path = _cache_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("timestamp", "")
        if ts and datetime.now() - datetime.fromisoformat(ts) > timedelta(seconds=CACHE_TTL):
            return None
        return data.get("departments", [])
    except Exception as e:
        logger.warning("Ошибка загрузки кэша подразделений: %s", e)
        return None


def _save_file_cache(departments: List[str]) -> None:
    try:
        path = _cache_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"timestamp": datetime.now().isoformat(), "departments": departments},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        logger.warning("Ошибка сохранения кэша подразделений: %s", e)


async def get_departments_from_jira() -> List[str]:
    """
    Получает список подразделений из Jira createmeta (проект AA, тип «Задача», поле Department).
    """
    global _cache
    if _cache:
        ts = _cache.get("timestamp", "")
        if ts and datetime.now() - datetime.fromisoformat(ts) < timedelta(seconds=CACHE_TTL):
            return _cache.get("departments", [])

    cached = _load_file_cache()
    if cached:
        _cache = {"timestamp": datetime.now().isoformat(), "departments": cached}
        return cached

    jira = CONFIG.get("JIRA", {})
    base_url = (jira.get("LOGIN_URL") or "").strip().rstrip("/")
    token = (jira.get("TOKEN") or "").strip()
    if not base_url or not token:
        logger.warning("JIRA LOGIN_URL или TOKEN не заданы для загрузки подразделений")
        return []

    jira_aa = CONFIG.get("JIRA_AA", {})
    project_key = (jira_aa.get("PROJECT_KEY") or "AA").strip()
    issue_type = (jira_aa.get("ISSUE_TYPE") or "Задача").strip()
    field_id = (jira_aa.get("FIELD_DEPARTMENT") or jira_aa.get("FIELDS", {}).get("DEPARTMENT") or "customfield_11406").strip()

    url = urljoin(base_url + "/", "rest/api/2/issue/createmeta")
    params = {
        "projectKeys": project_key,
        "issuetypeNames": issue_type,
        "expand": "projects.issuetypes.fields",
    }
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    departments: List[str] = []

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    logger.warning("Jira createmeta: %s %s", resp.status, await resp.text())
                    return []
                data = await resp.json()
        for project in data.get("projects", []):
            for it in project.get("issuetypes", []):
                fields = it.get("fields", {})
                if field_id not in fields:
                    continue
                field_info = fields[field_id]
                for val in field_info.get("allowedValues", []):
                    if isinstance(val, dict):
                        name = val.get("value") or val.get("name") or str(val)
                    else:
                        name = str(val)
                    if name and name.strip() and name not in departments:
                        departments.append(name.strip())
        if departments:
            departments.sort()
            _save_file_cache(departments)
            _cache = {"timestamp": datetime.now().isoformat(), "departments": departments}
            logger.info("Загружено %s подразделений из Jira", len(departments))
    except asyncio.TimeoutError:
        logger.warning("Timeout при загрузке подразделений из Jira")
    except Exception as e:
        logger.exception("Ошибка загрузки подразделений из Jira: %s", e)

    return departments


def get_departments() -> List[str]:
    """
    Синхронная обёртка: запускает get_departments_from_jira в loop.
    Используется в клавиатурах (keyboards вызываются синхронно).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Если уже внутри async — кэш или дефолт
            cached = _load_file_cache()
            if cached:
                return cached
            return []
        return loop.run_until_complete(get_departments_from_jira())
    except RuntimeError:
        return asyncio.run(get_departments_from_jira())
    except Exception as e:
        logger.warning("get_departments: %s", e)
        return []


async def get_departments_async() -> List[str]:
    """Асинхронно возвращает список подразделений (для хендлеров)."""
    return await get_departments_from_jira()
