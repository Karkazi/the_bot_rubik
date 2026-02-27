"""
Подразделения WMS из Jira (проект PW, поле customfield_18215).
Для выбора подразделения при создании заявки WMS.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import aiohttp
from config import CONFIG

logger = logging.getLogger(__name__)

CACHE_TTL = 3600
_cache: Optional[List[str]] = None


def _cache_path() -> Path:
    p = Path(__file__).resolve().parent.parent / "data" / "wms_departments_cache.json"
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
        logger.warning("Ошибка загрузки кэша подразделений WMS: %s", e)
        return None


def _save_file_cache(departments: List[str]) -> None:
    try:
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(
                {"timestamp": datetime.now().isoformat(), "departments": departments},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        logger.warning("Ошибка сохранения кэша подразделений WMS: %s", e)


async def get_wms_departments_from_jira() -> List[str]:
    """Загружает список подразделений WMS из Jira (проект PW, поле customfield_18215)."""
    global _cache
    if _cache:
        return _cache
    cached = _load_file_cache()
    if cached:
        _cache = cached
        return cached

    jira = CONFIG.get("JIRA", {})
    wms = CONFIG.get("JIRA_WMS", {})
    base_url = (jira.get("LOGIN_URL") or "").strip().rstrip("/")
    token = (jira.get("TOKEN") or "").strip()
    if not base_url or not token:
        logger.warning("JIRA не настроен для загрузки подразделений WMS")
        return []

    project_key = (wms.get("PROJECT_KEY") or "PW").strip()
    field_id = (wms.get("FIELD_DEPARTMENT") or "customfield_18215").strip()
    url = urljoin(base_url + "/", "rest/api/2/issue/createmeta")
    params = {
        "projectKeys": project_key,
        "expand": "projects.issuetypes.fields",
    }
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    departments: List[str] = []

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    logger.warning("Jira createmeta PW: %s %s", resp.status, await resp.text())
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
            _cache = departments
            logger.info("Загружено %s подразделений WMS из Jira", len(departments))
    except Exception as e:
        logger.exception("Ошибка загрузки подразделений WMS: %s", e)
    return departments


async def get_wms_departments_async() -> List[str]:
    return await get_wms_departments_from_jira()
