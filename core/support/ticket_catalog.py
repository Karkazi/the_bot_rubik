"""
Каталог типов заявок: загрузка из config/ticket_catalog.yaml.
По типу заявки Core определяет проект Jira, поля и сценарий создания.
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_CATALOG: Optional[Dict[str, Any]] = None
_CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "ticket_catalog.yaml"


def load_catalog() -> Dict[str, Any]:
    """Загружает каталог из YAML. Кэширует результат."""
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    if not _CATALOG_PATH.exists():
        logger.warning("Каталог заявок не найден: %s", _CATALOG_PATH)
        _CATALOG = _default_catalog()
        return _CATALOG
    try:
        import yaml
        with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
            _CATALOG = yaml.safe_load(f) or {}
    except Exception as e:
        logger.exception("Ошибка загрузки каталога заявок: %s", e)
        _CATALOG = _default_catalog()
    return _CATALOG


def _default_catalog() -> Dict[str, Any]:
    """Каталог по умолчанию: один тип — смена пароля Rubik."""
    return {
        "rubik_password_change": {
            "label": "🔑 Смена пароля",
            "project_key": "AA",
            "issue_type": "Задача",
            "request_type_id": "964",
            "service_desk_id": "23",
            "visible": True,
            "form_fields": [
                {"name": "password_new", "type": "text", "label": "Новый пароль"},
            ],
        },
    }


def get_catalog() -> Dict[str, Any]:
    """Возвращает каталог типов заявок (загружает при первом вызове)."""
    return load_catalog()


def get_ticket_type(ticket_type_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает метаданные типа заявки по id."""
    return get_catalog().get(ticket_type_id)
