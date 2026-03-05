"""
Поиск пользователя в AD по номеру телефона (и опционально по почте).
Используется при регистрации: почта + контакт → поиск по телефону в AD → профиль или ссылка на портал.
"""
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Атрибуты AD для профиля бота (поиск по телефону)
AD_ATTRS = [
    "displayName",
    "cn",
    "sAMAccountName",
    "mail",
    "userPrincipalName",
    "telephoneNumber",
    "mobile",
    "ipPhone",
    "department",
    "title",
]

# Атрибуты для проверки статуса пароля
AD_PASSWORD_ATTRS = [
    "pwdLastSet",
    "userAccountControl",
    "msDS-UserPasswordExpiryTimeComputed",
]


def _normalize_phone_digits(phone: str) -> str:
    """Последние 10 цифр номера (без ведущей 7) для поиска в AD."""
    digits = re.sub(r"\D", "", (phone or "").strip())
    if len(digits) >= 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        digits = digits[1:]
    return digits[-10:] if len(digits) >= 10 else digits


def _decode_value(val: Any) -> str:
    """Строка из атрибута AD (может быть bytes/base64 в LDIF)."""
    if val is None:
        return ""
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            return ""
    if isinstance(val, list):
        return _decode_value(val[0]) if val else ""
    s = str(val).strip()
    # LDIF base64 (::) — уже декодируется ldap3 в строку или bytes
    return s


def _get_first(entry_attrs: Dict[str, List], key: str) -> str:
    raw = entry_attrs.get(key)
    if raw is None:
        return ""
    if isinstance(raw, list) and raw:
        v = raw[0]
        if isinstance(v, bytes):
            try:
                return v.decode("utf-8").strip()
            except Exception:
                return ""
        return str(v).strip()
    return str(raw).strip() if raw else ""


def search_user_by_phone(phone: str) -> Optional[Dict[str, str]]:
    """
    Ищет в AD пользователя по номеру телефона (telephoneNumber, mobile, ipPhone).
    Возвращает профиль для бота: full_name, login, email, phone, department
    или None, если не найден / AD недоступен.
    """
    from config import CONFIG

    ad = CONFIG.get("AD_LDAP") or {}
    url = (ad.get("URL") or "").strip()
    bind_user = (ad.get("BIND_USER") or "").strip()
    bind_password = (ad.get("BIND_PASSWORD") or "").strip()
    base_dn = (ad.get("BASE_DN") or "").strip()
    verify_ssl = ad.get("VERIFY_SSL", False)

    if not url or not bind_user or not bind_password or not base_dn:
        logger.warning("AD_LDAP не настроен (URL/BIND_USER/BIND_PASSWORD/BASE_DN)")
        return None

    digits = _normalize_phone_digits(phone)
    if len(digits) < 10:
        return None

    try:
        from ldap3 import Server, Connection, ALL, SUBTREE, Tls
        import ssl

        # Парсим ldaps://host:636 или ldap://host:389
        use_ssl = url.lower().startswith("ldaps://")
        if "://" in url:
            url = url.split("://", 1)[1]
        host, _, port_str = url.partition(":")
        port = int(port_str) if port_str else (636 if use_ssl else 389)

        tls = None
        if use_ssl and not verify_ssl:
            tls = Tls(validate=ssl.CERT_NONE)

        server = Server(host, port=port, use_ssl=use_ssl, tls=tls, get_info=ALL)
        conn = Connection(server, user=bind_user, password=bind_password, auto_bind=True)

        # Поиск по телефону: в AD номера могут быть +7911..., 8911..., 911...
        search_filter = (
            f"(|(telephoneNumber=*{digits}*)(mobile=*{digits}*)(ipPhone=*{digits}*))"
        )
        conn.search(
            base_dn,
            search_filter,
            search_scope=SUBTREE,
            attributes=AD_ATTRS,
            size_limit=5,
        )

        if not conn.entries:
            conn.unbind()
            return None

        entry = conn.entries[0]
        conn.unbind()

        attrs = entry.entry_attributes_as_dict
        full_name = _get_first(attrs, "displayName") or _get_first(attrs, "cn")
        login = _get_first(attrs, "sAMAccountName")
        email = _get_first(attrs, "mail") or _get_first(attrs, "userPrincipalName")
        phone_raw = (
            _get_first(attrs, "mobile")
            or _get_first(attrs, "telephoneNumber")
            or _get_first(attrs, "ipPhone")
        )
        department = _get_first(attrs, "department")

        if not login and not email:
            return None

        # Нормализуем телефон для хранения (единый формат)
        from validators import normalize_phone_display

        phone_display = normalize_phone_display(phone_raw) if phone_raw else phone_raw or phone

        return {
            "full_name": full_name or "",
            "login": (login or "").strip().lower(),
            "email": (email or "").strip().lower(),
            "phone": phone_display,
            "department": (department or "").strip(),
        }
    except Exception as e:
        logger.exception("AD search by phone failed: %s", e)
        return None


def is_password_expired(login: str) -> Optional[bool]:
    """
    Проверяет по AD, помечён ли пароль пользователя как истёкший.
    Возвращает:
      - True  — пароль истёк (PasswordExpired);
      - False — пароль не истёк;
      - None  — не удалось определить (ошибка подключения/поиска).
    Безопасное поведение на стороне вызывающего кода: при None лучше не разрешать смену
    пароля через бота и предложить обратиться в поддержку.
    """
    from config import CONFIG

    ad = CONFIG.get("AD_LDAP") or {}
    url = (ad.get("URL") or "").strip()
    bind_user = (ad.get("BIND_USER") or "").strip()
    bind_password = (ad.get("BIND_PASSWORD") or "").strip()
    base_dn = (ad.get("BASE_DN") or "").strip()
    verify_ssl = ad.get("VERIFY_SSL", False)

    if not url or not bind_user or not bind_password or not base_dn:
        logger.warning("AD_LDAP не настроен (URL/BIND_USER/BIND_PASSWORD/BASE_DN)")
        return None

    login = (login or "").strip()
    if not login:
        return None

    try:
        from ldap3 import Server, Connection, ALL, SUBTREE, Tls
        import ssl
        from datetime import datetime, timezone

        use_ssl = url.lower().startswith("ldaps://")
        if "://" in url:
            url = url.split("://", 1)[1]
        host, _, port_str = url.partition(":")
        port = int(port_str) if port_str else (636 if use_ssl else 389)

        tls = None
        if use_ssl and not verify_ssl:
            tls = Tls(validate=ssl.CERT_NONE)

        server = Server(host, port=port, use_ssl=use_ssl, tls=tls, get_info=ALL)
        conn = Connection(server, user=bind_user, password=bind_password, auto_bind=True)

        search_filter = f"(sAMAccountName={login})"
        conn.search(
            base_dn,
            search_filter,
            search_scope=SUBTREE,
            attributes=AD_PASSWORD_ATTRS,
            size_limit=1,
        )
        if not conn.entries:
            conn.unbind()
            return None
        entry = conn.entries[0]
        conn.unbind()
        attrs = entry.entry_attributes_as_dict

        # 1) Явный флаг PASSWORD_EXPIRED (0x800000) в userAccountControl
        try:
            uac_raw = _get_first(attrs, "userAccountControl")
            uac = int(uac_raw) if uac_raw else 0
        except Exception:
            uac = 0
        PASSWORD_EXPIRED_FLAG = 0x800000
        if uac & PASSWORD_EXPIRED_FLAG:
            return True

        # 2) Сравнение msDS-UserPasswordExpiryTimeComputed с текущим временем
        exp_raw = _get_first(attrs, "msDS-UserPasswordExpiryTimeComputed")
        if not exp_raw:
            return None
        try:
            filetime = int(exp_raw)
            # FILETIME (100-нс тики с 1601-01-01) -> Unix epoch
            unix_ts = (filetime - 116444736000000000) / 10**7
            expiry_dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            return now >= expiry_dt
        except Exception as e:
            logger.exception("AD password expiry parse failed for %s: %s", login, e)
            return None
