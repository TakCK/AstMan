import base64
import csv
import hashlib
import io
import smtplib
import os
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from ldap3 import Connection, Server, SUBTREE
from fastapi.responses import FileResponse
from ldap3.core.exceptions import LDAPException
from fastapi.staticfiles import StaticFiles
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import crud, models, schemas, security
from .database import Base, SessionLocal, engine, get_db

app = FastAPI(
    title="IT 자산관리 시스템",
    version="0.7.0",
    description=(
        "사내 IT 자산의 등록, 검색, 상태 관리, 이력 추적을 위한 API입니다. "
        "웹 화면은 루트 경로(/)에서 사용할 수 있습니다."
    ),
    openapi_tags=[
        {"name": "인증", "description": "로그인 및 내 계정 확인"},
        {"name": "사용자", "description": "사용자 관리 (관리자 권한 필요)"},
        {"name": "대시보드", "description": "자산 현황 요약"},
        {"name": "자산", "description": "자산 등록/조회/수정/이력/상태변경"},
        {"name": "소프트웨어", "description": "소프트웨어 라이선스 관리"},
        {"name": "설정", "description": "환율 등 시스템 설정"},
        {"name": "LDAP", "description": "사내 AD/LDAP 연동"},
    ],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")



LDAP_SYNC_SCHEDULE_KEY = "ldap_sync_schedule"
LDAP_SYNC_STATE_KEY = "ldap_sync_state"
LDAP_SYNC_PASSWORD_KEY = "ldap_sync_bind_password"

LDAP_RUNTIME_LOCK = threading.Lock()
LDAP_RUNTIME_BIND_PASSWORD: str | None = None
LDAP_SCHEDULER_STOP = threading.Event()
LDAP_SCHEDULER_THREAD: threading.Thread | None = None
LDAP_PASSWORD_CIPHER: Fernet | None = None

SOFTWARE_MAIL_CONFIG_KEY = "software_expiry_mail_config"
SOFTWARE_MAIL_STATE_KEY = "software_expiry_mail_state"
SOFTWARE_MAIL_PASSWORD_KEY = "software_expiry_mail_password"
SOFTWARE_USER_MAIL_CONFIG_KEY = "software_user_expiry_mail_config"
SOFTWARE_USER_MAIL_STATE_KEY = "software_user_expiry_mail_state"

SOFTWARE_MAIL_RUNTIME_LOCK = threading.Lock()
SOFTWARE_MAIL_RUNTIME_PASSWORD: str | None = None
SOFTWARE_MAIL_SCHEDULER_STOP = threading.Event()
SOFTWARE_MAIL_SCHEDULER_THREAD: threading.Thread | None = None
KST = timezone(timedelta(hours=9))


def _default_sync_schedule() -> dict:
    return {
        "enabled": False,
        "interval_minutes": 60,
        "server_url": "",
        "use_ssl": False,
        "port": None,
        "bind_dn": "",
        "base_dn": "",
        "user_id_attribute": "sAMAccountName",
        "user_name_attribute": "displayName",
        "user_email_attribute": "mail",
        "user_department_attribute": "department",
        "user_title_attribute": "title",
        "manager_dn_attribute": "manager",
        "user_dn_attribute": "distinguishedName",
        "user_guid_attribute": "objectGUID",
        "size_limit": 1000,
    }


def _sanitize_sync_schedule(raw: dict | None) -> dict:
    src = raw or {}
    defaults = _default_sync_schedule()

    interval = src.get("interval_minutes", defaults["interval_minutes"])
    try:
        interval = int(interval)
    except (TypeError, ValueError):
        interval = defaults["interval_minutes"]
    interval = max(5, min(1440, interval))

    size_limit = src.get("size_limit", defaults["size_limit"])
    try:
        size_limit = int(size_limit)
    except (TypeError, ValueError):
        size_limit = defaults["size_limit"]
    size_limit = max(50, min(5000, size_limit))

    port_raw = src.get("port", defaults["port"])
    port = None
    if port_raw not in (None, ""):
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            port = None

    return {
        "enabled": bool(src.get("enabled", defaults["enabled"])),
        "interval_minutes": interval,
        "server_url": str(src.get("server_url", defaults["server_url"]) or "").strip(),
        "use_ssl": bool(src.get("use_ssl", defaults["use_ssl"])),
        "port": port,
        "bind_dn": str(src.get("bind_dn", defaults["bind_dn"]) or "").strip(),
        "base_dn": str(src.get("base_dn", defaults["base_dn"]) or "").strip(),
        "user_id_attribute": str(src.get("user_id_attribute", defaults["user_id_attribute"]) or "sAMAccountName").strip() or "sAMAccountName",
        "user_name_attribute": str(src.get("user_name_attribute", defaults["user_name_attribute"]) or "displayName").strip() or "displayName",
        "user_email_attribute": str(src.get("user_email_attribute", defaults["user_email_attribute"]) or "mail").strip() or "mail",
        "user_department_attribute": str(src.get("user_department_attribute", defaults["user_department_attribute"]) or "department").strip() or "department",
        "user_title_attribute": str(src.get("user_title_attribute", defaults["user_title_attribute"]) or "title").strip() or "title",
        "manager_dn_attribute": str(src.get("manager_dn_attribute", defaults["manager_dn_attribute"]) or "manager").strip() or "manager",
        "user_dn_attribute": str(src.get("user_dn_attribute", defaults["user_dn_attribute"]) or "distinguishedName").strip() or "distinguishedName",
        "user_guid_attribute": str(src.get("user_guid_attribute", defaults["user_guid_attribute"]) or "objectGUID").strip() or "objectGUID",
        "size_limit": size_limit,
    }


def _parse_iso_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _get_ldap_cipher() -> Fernet | None:
    global LDAP_PASSWORD_CIPHER

    if LDAP_PASSWORD_CIPHER is not None:
        return LDAP_PASSWORD_CIPHER

    secret_source = os.getenv("LDAP_BIND_PASSWORD_KEY") or os.getenv("SECRET_KEY") or ""
    if not secret_source.strip():
        return None

    seed = hashlib.sha256(f"{secret_source}|ldap-bind-password|v1".encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(seed)
    LDAP_PASSWORD_CIPHER = Fernet(key)
    return LDAP_PASSWORD_CIPHER


def _encrypt_bind_password(bind_password: str) -> str:
    cipher = _get_ldap_cipher()
    if not cipher:
        raise ValueError("ldap_password_encryption_key_missing")

    return cipher.encrypt(bind_password.encode("utf-8")).decode("utf-8")


def _decrypt_bind_password(encrypted_text: str) -> str | None:
    cipher = _get_ldap_cipher()
    if not cipher:
        return None

    token = str(encrypted_text or "").strip()
    if not token:
        return None

    try:
        return cipher.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def _persist_bind_password(db: Session, bind_password: str | None):
    password = str(bind_password or "")
    if not password:
        crud.set_app_setting(db, LDAP_SYNC_PASSWORD_KEY, {"ciphertext": ""})
        return

    encrypted = _encrypt_bind_password(password)
    crud.set_app_setting(
        db,
        LDAP_SYNC_PASSWORD_KEY,
        {
            "ciphertext": encrypted,
            "updated_at": _iso_or_none(datetime.now(timezone.utc)),
        },
    )


def _has_persisted_bind_password(db: Session) -> bool:
    row = crud.get_app_setting(db, LDAP_SYNC_PASSWORD_KEY, {})
    return bool(str(row.get("ciphertext") or "").strip())


def _ensure_runtime_bind_password(db: Session) -> str | None:
    with LDAP_RUNTIME_LOCK:
        runtime_password = LDAP_RUNTIME_BIND_PASSWORD

    if runtime_password:
        return runtime_password

    row = crud.get_app_setting(db, LDAP_SYNC_PASSWORD_KEY, {})
    restored_password = _decrypt_bind_password(str(row.get("ciphertext") or ""))
    if restored_password:
        _set_runtime_bind_password(restored_password)

    return restored_password


def _get_sync_schedule(db: Session) -> dict:
    raw = crud.get_app_setting(db, LDAP_SYNC_SCHEDULE_KEY, _default_sync_schedule())
    return _sanitize_sync_schedule(raw)


def _get_sync_state(db: Session) -> dict:
    raw = crud.get_app_setting(db, LDAP_SYNC_STATE_KEY, {})
    return {
        "last_attempt_at": raw.get("last_attempt_at"),
        "last_synced_at": raw.get("last_synced_at"),
        "last_error": raw.get("last_error"),
        "last_result": raw.get("last_result") if isinstance(raw.get("last_result"), dict) else None,
    }


def _set_sync_state(
    db: Session,
    *,
    last_attempt_at: datetime | None = None,
    last_synced_at: datetime | None = None,
    last_error: str | None = None,
    last_result: dict | None = None,
):
    current = _get_sync_state(db)
    payload = {
        "last_attempt_at": _iso_or_none(last_attempt_at) if last_attempt_at is not None else current.get("last_attempt_at"),
        "last_synced_at": _iso_or_none(last_synced_at) if last_synced_at is not None else current.get("last_synced_at"),
        "last_error": last_error,
        "last_result": last_result if isinstance(last_result, dict) else None,
    }
    crud.set_app_setting(db, LDAP_SYNC_STATE_KEY, payload)


def _has_runtime_bind_password() -> bool:
    with LDAP_RUNTIME_LOCK:
        return bool(LDAP_RUNTIME_BIND_PASSWORD)


def _set_runtime_bind_password(bind_password: str | None):
    global LDAP_RUNTIME_BIND_PASSWORD
    with LDAP_RUNTIME_LOCK:
        LDAP_RUNTIME_BIND_PASSWORD = str(bind_password or "") or None


def _build_sync_schedule_response(db: Session) -> dict:
    schedule = _get_sync_schedule(db)
    state = _get_sync_state(db)
    runtime_password = _ensure_runtime_bind_password(db)

    return {
        **schedule,
        "has_runtime_password": bool(runtime_password),
        "has_stored_password": _has_persisted_bind_password(db),
        "last_synced_at": _parse_iso_datetime(state.get("last_synced_at")),
        "last_error": state.get("last_error"),
        "last_result": state.get("last_result"),
    }


def _default_software_mail_subject_template() -> str:
    return "[ITAM] 소프트웨어 만료 알림 ({DATE})"


def _default_software_mail_body_template() -> str:
    return """소프트웨어 만료 알림 ({DATE})

- 조회 라이선스: {CHECKED_LICENSES}건
- 만료 예정({NOTIFY_DAYS}일 이내): {EXPIRING_COUNT}건
- 이미 만료: {EXPIRED_COUNT}건

[만료 예정 목록]
{EXPIRING_ITEMS}

[만료 목록]
{EXPIRED_ITEMS}
"""


def _default_software_mail_config() -> dict:
    return {
        "enabled": False,
        "smtp_host": "",
        "smtp_port": 587,
        "use_tls": True,
        "use_ssl": False,
        "smtp_username": "",
        "from_email": "",
        "to_emails": [],
        "notify_days": 30,
        "schedule_hour": 9,
        "schedule_minute": 0,
        "include_expired": True,
        "subject_template": _default_software_mail_subject_template(),
        "body_template": _default_software_mail_body_template(),
    }


def _sanitize_email_list(values) -> list[str]:
    if isinstance(values, str):
        raw_values = values.replace(";", ",").replace("\n", ",").split(",")
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = []

    result: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        email = str(raw or "").strip()
        if not email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(email)
    return result


def _sanitize_software_mail_config(raw: dict | None) -> dict:
    src = raw or {}
    defaults = _default_software_mail_config()

    try:
        smtp_port = int(src.get("smtp_port", defaults["smtp_port"]))
    except (TypeError, ValueError):
        smtp_port = defaults["smtp_port"]
    smtp_port = max(1, min(65535, smtp_port))

    try:
        notify_days = int(src.get("notify_days", defaults["notify_days"]))
    except (TypeError, ValueError):
        notify_days = defaults["notify_days"]
    notify_days = max(1, min(365, notify_days))

    try:
        schedule_hour = int(src.get("schedule_hour", defaults["schedule_hour"]))
    except (TypeError, ValueError):
        schedule_hour = defaults["schedule_hour"]
    schedule_hour = max(0, min(23, schedule_hour))

    try:
        schedule_minute = int(src.get("schedule_minute", defaults["schedule_minute"]))
    except (TypeError, ValueError):
        schedule_minute = defaults["schedule_minute"]
    schedule_minute = max(0, min(59, schedule_minute))

    subject_template = str(src.get("subject_template", defaults["subject_template"]) or "").strip()
    if not subject_template:
        subject_template = defaults["subject_template"]
    if len(subject_template) > 300:
        subject_template = subject_template[:300]

    body_template = str(src.get("body_template", defaults["body_template"]) or "").strip()
    if not body_template:
        body_template = defaults["body_template"]
    if len(body_template) > 20000:
        body_template = body_template[:20000]

    return {
        "enabled": bool(src.get("enabled", defaults["enabled"])),
        "smtp_host": str(src.get("smtp_host", defaults["smtp_host"]) or "").strip(),
        "smtp_port": smtp_port,
        "use_tls": bool(src.get("use_tls", defaults["use_tls"])),
        "use_ssl": bool(src.get("use_ssl", defaults["use_ssl"])),
        "smtp_username": str(src.get("smtp_username", defaults["smtp_username"]) or "").strip(),
        "from_email": str(src.get("from_email", defaults["from_email"]) or "").strip(),
        "to_emails": _sanitize_email_list(src.get("to_emails", defaults["to_emails"])),
        "notify_days": notify_days,
        "schedule_hour": schedule_hour,
        "schedule_minute": schedule_minute,
        "include_expired": bool(src.get("include_expired", defaults["include_expired"])),
        "subject_template": subject_template,
        "body_template": body_template,
    }


def _get_software_mail_config(db: Session) -> dict:
    raw = crud.get_app_setting(db, SOFTWARE_MAIL_CONFIG_KEY, _default_software_mail_config())
    return _sanitize_software_mail_config(raw)


def _get_software_mail_state(db: Session) -> dict:
    raw = crud.get_app_setting(db, SOFTWARE_MAIL_STATE_KEY, {})
    return {
        "last_sent_at": raw.get("last_sent_at"),
        "last_error": raw.get("last_error"),
        "last_result": raw.get("last_result") if isinstance(raw.get("last_result"), dict) else None,
    }


def _set_software_mail_state(
    db: Session,
    *,
    last_sent_at: datetime | None = None,
    last_error: str | None = None,
    last_result: dict | None = None,
):
    current = _get_software_mail_state(db)
    payload = {
        "last_sent_at": _iso_or_none(last_sent_at) if last_sent_at is not None else current.get("last_sent_at"),
        "last_error": last_error,
        "last_result": last_result if isinstance(last_result, dict) else current.get("last_result"),
    }
    crud.set_app_setting(db, SOFTWARE_MAIL_STATE_KEY, payload)


def _set_runtime_software_mail_password(password: str | None):
    global SOFTWARE_MAIL_RUNTIME_PASSWORD
    with SOFTWARE_MAIL_RUNTIME_LOCK:
        SOFTWARE_MAIL_RUNTIME_PASSWORD = str(password or "").strip() or None


def _persist_software_mail_password(db: Session, password: str | None):
    raw = str(password or "").strip()
    if not raw:
        crud.set_app_setting(db, SOFTWARE_MAIL_PASSWORD_KEY, {"ciphertext": ""})
        return

    encrypted = _encrypt_bind_password(raw)
    crud.set_app_setting(
        db,
        SOFTWARE_MAIL_PASSWORD_KEY,
        {
            "ciphertext": encrypted,
            "updated_at": _iso_or_none(datetime.now(timezone.utc)),
        },
    )


def _has_persisted_software_mail_password(db: Session) -> bool:
    row = crud.get_app_setting(db, SOFTWARE_MAIL_PASSWORD_KEY, {})
    return bool(str(row.get("ciphertext") or "").strip())


def _ensure_runtime_software_mail_password(db: Session) -> str | None:
    with SOFTWARE_MAIL_RUNTIME_LOCK:
        runtime_password = SOFTWARE_MAIL_RUNTIME_PASSWORD

    if runtime_password:
        return runtime_password

    row = crud.get_app_setting(db, SOFTWARE_MAIL_PASSWORD_KEY, {})
    restored = _decrypt_bind_password(str(row.get("ciphertext") or ""))
    if restored:
        _set_runtime_software_mail_password(restored)

    return restored


def _build_software_mail_config_response(db: Session) -> dict:
    config = _get_software_mail_config(db)
    state = _get_software_mail_state(db)
    runtime_password = _ensure_runtime_software_mail_password(db)

    return {
        **config,
        "has_runtime_password": bool(runtime_password),
        "has_stored_password": _has_persisted_software_mail_password(db),
        "last_sent_at": _parse_iso_datetime(state.get("last_sent_at")),
        "last_error": state.get("last_error"),
        "last_result": state.get("last_result"),
    }



def _default_software_user_mail_subject_template() -> str:
    return "[ITAM] {USER_NAME}님 소프트웨어 만료 알림 ({DATE})"


def _default_software_user_mail_body_template() -> str:
    return """안녕하세요 {USER_NAME}님,

소프트웨어 라이선스 만료 안내입니다. ({DATE})

- 만료 예정({NOTIFY_DAYS}일 이내): {USER_EXPIRING_COUNT}건
- 이미 만료: {USER_EXPIRED_COUNT}건

[내 만료 예정 목록]
{EXPIRING_ITEMS}

[내 만료 목록]
{EXPIRED_ITEMS}
"""


def _default_software_user_mail_config() -> dict:
    return {
        "enabled": False,
        "notify_days": 30,
        "schedule_hour": 9,
        "schedule_minute": 0,
        "include_expired": True,
        "only_active_users": True,
        "subject_template": _default_software_user_mail_subject_template(),
        "body_template": _default_software_user_mail_body_template(),
    }


def _sanitize_software_user_mail_config(raw: dict | None) -> dict:
    src = raw or {}
    defaults = _default_software_user_mail_config()

    try:
        notify_days = int(src.get("notify_days", defaults["notify_days"]))
    except (TypeError, ValueError):
        notify_days = defaults["notify_days"]
    notify_days = max(1, min(365, notify_days))

    try:
        schedule_hour = int(src.get("schedule_hour", defaults["schedule_hour"]))
    except (TypeError, ValueError):
        schedule_hour = defaults["schedule_hour"]
    schedule_hour = max(0, min(23, schedule_hour))

    try:
        schedule_minute = int(src.get("schedule_minute", defaults["schedule_minute"]))
    except (TypeError, ValueError):
        schedule_minute = defaults["schedule_minute"]
    schedule_minute = max(0, min(59, schedule_minute))

    subject_template = str(src.get("subject_template", defaults["subject_template"]) or "").strip()
    if not subject_template:
        subject_template = defaults["subject_template"]
    if len(subject_template) > 300:
        subject_template = subject_template[:300]

    body_template = str(src.get("body_template", defaults["body_template"]) or "").strip()
    if not body_template:
        body_template = defaults["body_template"]
    if len(body_template) > 20000:
        body_template = body_template[:20000]

    return {
        "enabled": bool(src.get("enabled", defaults["enabled"])),
        "notify_days": notify_days,
        "schedule_hour": schedule_hour,
        "schedule_minute": schedule_minute,
        "include_expired": bool(src.get("include_expired", defaults["include_expired"])),
        "only_active_users": bool(src.get("only_active_users", defaults["only_active_users"])),
        "subject_template": subject_template,
        "body_template": body_template,
    }


def _get_software_user_mail_config(db: Session) -> dict:
    raw = crud.get_app_setting(db, SOFTWARE_USER_MAIL_CONFIG_KEY, _default_software_user_mail_config())
    return _sanitize_software_user_mail_config(raw)


def _get_software_user_mail_state(db: Session) -> dict:
    raw = crud.get_app_setting(db, SOFTWARE_USER_MAIL_STATE_KEY, {})
    return {
        "last_sent_at": raw.get("last_sent_at"),
        "last_error": raw.get("last_error"),
        "last_result": raw.get("last_result") if isinstance(raw.get("last_result"), dict) else None,
    }


def _set_software_user_mail_state(
    db: Session,
    *,
    last_sent_at: datetime | None = None,
    last_error: str | None = None,
    last_result: dict | None = None,
):
    current = _get_software_user_mail_state(db)
    payload = {
        "last_sent_at": _iso_or_none(last_sent_at) if last_sent_at is not None else current.get("last_sent_at"),
        "last_error": last_error,
        "last_result": last_result if isinstance(last_result, dict) else current.get("last_result"),
    }
    crud.set_app_setting(db, SOFTWARE_USER_MAIL_STATE_KEY, payload)


def _get_mail_smtp_config(db: Session) -> dict:
    config = _get_software_mail_config(db)
    return {
        "smtp_host": str(config.get("smtp_host") or "").strip(),
        "smtp_port": int(config.get("smtp_port") or 587),
        "use_tls": bool(config.get("use_tls")),
        "use_ssl": bool(config.get("use_ssl")),
        "smtp_username": str(config.get("smtp_username") or "").strip(),
        "from_email": str(config.get("from_email") or "").strip(),
    }


def _build_mail_smtp_config_response(db: Session) -> dict:
    smtp_config = _get_mail_smtp_config(db)
    runtime_password = _ensure_runtime_software_mail_password(db)
    return {
        **smtp_config,
        "has_runtime_password": bool(runtime_password),
        "has_stored_password": _has_persisted_software_mail_password(db),
    }


def _build_mail_admin_config_response(db: Session) -> dict:
    config = _get_software_mail_config(db)
    state = _get_software_mail_state(db)
    return {
        "enabled": bool(config.get("enabled")),
        "to_emails": _sanitize_email_list(config.get("to_emails") or []),
        "notify_days": int(config.get("notify_days") or 30),
        "schedule_hour": int(config.get("schedule_hour") or 9),
        "schedule_minute": int(config.get("schedule_minute") or 0),
        "include_expired": bool(config.get("include_expired")),
        "subject_template": str(config.get("subject_template") or _default_software_mail_subject_template()),
        "body_template": str(config.get("body_template") or _default_software_mail_body_template()),
        "last_sent_at": _parse_iso_datetime(state.get("last_sent_at")),
        "last_error": state.get("last_error"),
        "last_result": state.get("last_result"),
    }


def _build_mail_user_config_response(db: Session) -> dict:
    config = _get_software_user_mail_config(db)
    state = _get_software_user_mail_state(db)
    return {
        **config,
        "last_sent_at": _parse_iso_datetime(state.get("last_sent_at")),
        "last_error": state.get("last_error"),
        "last_result": state.get("last_result"),
    }


def _update_mail_smtp_config(db: Session, payload: dict) -> dict:
    current = _get_software_mail_config(db)
    merged = {
        **current,
        "smtp_host": payload.get("smtp_host"),
        "smtp_port": payload.get("smtp_port"),
        "use_tls": payload.get("use_tls"),
        "use_ssl": payload.get("use_ssl"),
        "smtp_username": payload.get("smtp_username"),
        "from_email": payload.get("from_email"),
    }
    sanitized = _sanitize_software_mail_config(merged)
    crud.set_app_setting(db, SOFTWARE_MAIL_CONFIG_KEY, sanitized)
    return _build_mail_smtp_config_response(db)


def _update_mail_admin_config(db: Session, payload: dict) -> dict:
    current = _get_software_mail_config(db)
    merged = {
        **current,
        "enabled": payload.get("enabled"),
        "to_emails": payload.get("to_emails"),
        "notify_days": payload.get("notify_days"),
        "schedule_hour": payload.get("schedule_hour"),
        "schedule_minute": payload.get("schedule_minute"),
        "include_expired": payload.get("include_expired"),
        "subject_template": payload.get("subject_template"),
        "body_template": payload.get("body_template"),
    }
    sanitized = _sanitize_software_mail_config(merged)
    crud.set_app_setting(db, SOFTWARE_MAIL_CONFIG_KEY, sanitized)
    return _build_mail_admin_config_response(db)


def _update_mail_user_config(db: Session, payload: dict) -> dict:
    sanitized = _sanitize_software_user_mail_config(payload)
    crud.set_app_setting(db, SOFTWARE_USER_MAIL_CONFIG_KEY, sanitized)
    return _build_mail_user_config_response(db)

def _normalize_optional_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return datetime.fromisoformat(text).date()
            except ValueError:
                try:
                    return datetime.strptime(text, "%Y-%m-%d").date()
                except ValueError:
                    return None
    return None


def _collect_software_expiry_targets(db: Session, notify_days: int) -> dict:
    today = datetime.now(KST).date()
    until = today + timedelta(days=notify_days)

    user_map = {
        str(username or "").strip(): {
            "display_name": (str(display_name or "").strip() or str(username or "").strip()),
            "email": str(email or "").strip(),
            "is_active": bool(is_active),
        }
        for username, display_name, email, is_active in db.query(
            models.DirectoryUser.username,
            models.DirectoryUser.display_name,
            models.DirectoryUser.email,
            models.DirectoryUser.is_active,
        ).all()
        if str(username or "").strip()
    }

    expiring_items: list[dict] = []
    expired_items: list[dict] = []

    for sw in db.query(models.SoftwareLicense).all():
        assignees = [str(v or "").strip() for v in (sw.assignees or []) if str(v or "").strip()]
        if not assignees:
            continue

        detail_end_map: dict[str, date | None] = {}
        if isinstance(sw.assignee_details, list):
            for detail in sw.assignee_details:
                if not isinstance(detail, dict):
                    continue
                username = str(detail.get("username") or "").strip()
                if not username or username in detail_end_map:
                    continue
                detail_end_map[username] = _normalize_optional_date(detail.get("end_date"))

        default_end = _normalize_optional_date(sw.end_date)

        for username in assignees:
            end_date = detail_end_map.get(username) or default_end
            if not end_date:
                continue

            user_info = user_map.get(username) or {
                "display_name": username,
                "email": "",
                "is_active": True,
            }

            days_left = (end_date - today).days
            row = {
                "license_name": str(sw.product_name or "(이름없음)").strip(),
                "username": username,
                "display_name": str(user_info.get("display_name") or username).strip() or username,
                "email": str(user_info.get("email") or "").strip(),
                "is_active": bool(user_info.get("is_active", True)),
                "end_date": end_date.isoformat(),
                "days_left": days_left,
            }

            if days_left < 0:
                expired_items.append(row)
            elif today <= end_date <= until:
                expiring_items.append(row)

    expiring_items.sort(key=lambda item: (item["end_date"], item["display_name"], item["license_name"]))
    expired_items.sort(key=lambda item: (item["end_date"], item["display_name"], item["license_name"]))

    return {
        "checked_licenses": int(db.query(models.SoftwareLicense.id).count() or 0),
        "expiring_count": len(expiring_items),
        "expired_count": len(expired_items),
        "expiring_items": expiring_items,
        "expired_items": expired_items,
        "today": today.isoformat(),
        "notify_days": notify_days,
    }

def _render_software_mail_template(template: str, token_values: dict[str, str]) -> str:
    rendered = str(template or "")
    for key, value in token_values.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered


def _compose_software_expiry_mail(config: dict, payload: dict) -> tuple[str, str, dict[str, int]]:
    today_text = payload.get("today") or datetime.now(KST).date().isoformat()
    expiring_items = payload.get("expiring_items") or []
    expired_items = payload.get("expired_items") or []

    if not config.get("include_expired"):
        expired_items = []

    expiring_lines: list[str] = []
    if expiring_items:
        for row in expiring_items[:200]:
            expiring_lines.append(
                f"- {row['end_date']} ({row['days_left']}일 남음) | {row['license_name']} | {row['display_name']} ({row['username']})"
            )
        if len(expiring_items) > 200:
            expiring_lines.append(f"- ... 외 {len(expiring_items) - 200}건")
    else:
        expiring_lines.append("- 대상 없음")

    expired_lines: list[str] = []
    if expired_items:
        for row in expired_items[:200]:
            expired_lines.append(
                f"- {row['end_date']} ({abs(row['days_left'])}일 경과) | {row['license_name']} | {row['display_name']} ({row['username']})"
            )
        if len(expired_items) > 200:
            expired_lines.append(f"- ... 외 {len(expired_items) - 200}건")
    else:
        expired_lines.append("- 대상 없음")

    recipient_count = len(config.get("to_emails") or [])
    notify_days = int(config.get("notify_days") or 30)

    token_values = {
        "DATE": today_text,
        "NOTIFY_DAYS": str(notify_days),
        "CHECKED_LICENSES": str(int(payload.get("checked_licenses") or 0)),
        "EXPIRING_COUNT": str(len(expiring_items)),
        "EXPIRED_COUNT": str(len(expired_items)),
        "RECIPIENT_COUNT": str(recipient_count),
        "EXPIRING_ITEMS": "\n".join(expiring_lines),
        "EXPIRED_ITEMS": "\n".join(expired_lines),
    }

    subject_template = str(config.get("subject_template") or _default_software_mail_subject_template()).strip()
    body_template = str(config.get("body_template") or _default_software_mail_body_template()).strip()

    subject = _render_software_mail_template(subject_template, token_values).strip()
    if not subject:
        subject = _render_software_mail_template(_default_software_mail_subject_template(), token_values).strip()

    body = _render_software_mail_template(body_template, token_values).strip()
    if not body:
        body = _render_software_mail_template(_default_software_mail_body_template(), token_values).strip()

    result = {
        "checked_licenses": int(payload.get("checked_licenses") or 0),
        "expiring_count": len(expiring_items),
        "expired_count": len(expired_items),
        "mail_recipient_count": recipient_count,
    }

    return subject, body, result


def _send_mail_via_smtp(
    config: dict,
    smtp_password: str | None,
    subject: str,
    body_text: str,
    recipients: list[str] | None = None,
):
    host = str(config.get("smtp_host") or "").strip()
    if not host:
        raise ValueError("SMTP 서버 주소를 입력해주세요")

    recipient_list = _sanitize_email_list(recipients if recipients is not None else (config.get("to_emails") or []))
    if not recipient_list:
        raise ValueError("수신 이메일 주소를 1개 이상 입력해주세요")

    port = int(config.get("smtp_port") or 587)
    use_ssl = bool(config.get("use_ssl"))
    use_tls = bool(config.get("use_tls"))
    username = str(config.get("smtp_username") or "").strip()
    from_email = str(config.get("from_email") or "").strip() or username or "assetmanager@local"

    if username and not str(smtp_password or "").strip():
        raise ValueError("SMTP 비밀번호를 입력해주세요")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(recipient_list)
    msg.set_content(body_text)

    if use_ssl:
        with smtplib.SMTP_SSL(host=host, port=port, timeout=20) as server:
            if username:
                server.login(username, str(smtp_password or ""))
            server.send_message(msg)
        return

    with smtplib.SMTP(host=host, port=port, timeout=20) as server:
        server.ehlo()
        if use_tls:
            server.starttls()
            server.ehlo()
        if username:
            server.login(username, str(smtp_password or ""))
        server.send_message(msg)

def _send_software_expiry_alarm(
    db: Session,
    *,
    smtp_password: str | None = None,
    force_send_when_empty: bool = False,
) -> dict[str, int]:
    config = _get_software_mail_config(db)
    payload = _collect_software_expiry_targets(db, int(config.get("notify_days") or 30))
    subject, body, result = _compose_software_expiry_mail(config, payload)

    has_targets = (result.get("expiring_count") or 0) > 0 or (result.get("expired_count") or 0) > 0
    if not has_targets and not force_send_when_empty:
        _set_software_mail_state(db, last_error=None, last_result=result)
        return {**result, "sent": 0}

    runtime_password = str(smtp_password or "").strip() or _ensure_runtime_software_mail_password(db)
    _send_mail_via_smtp(config, runtime_password, subject, body)
    _set_software_mail_state(db, last_sent_at=datetime.now(timezone.utc), last_error=None, last_result=result)
    return {**result, "sent": 1}



def _compose_software_user_expiry_mail(config: dict, username: str, display_name: str, email: str, payload: dict) -> tuple[str, str, int, int]:
    today_text = payload.get("today") or datetime.now(KST).date().isoformat()
    all_expiring_items = payload.get("expiring_items") or []
    all_expired_items = payload.get("expired_items") or []

    expiring_items = [row for row in all_expiring_items if str(row.get("username") or "") == username]
    expired_items = [row for row in all_expired_items if str(row.get("username") or "") == username]

    if not config.get("include_expired"):
        expired_items = []

    expiring_lines: list[str] = []
    if expiring_items:
        for row in expiring_items[:200]:
            expiring_lines.append(f"- {row['end_date']} ({row['days_left']}일 남음) | {row['license_name']}")
        if len(expiring_items) > 200:
            expiring_lines.append(f"- ... 외 {len(expiring_items) - 200}건")
    else:
        expiring_lines.append("- 대상 없음")

    expired_lines: list[str] = []
    if expired_items:
        for row in expired_items[:200]:
            expired_lines.append(f"- {row['end_date']} ({abs(row['days_left'])}일 경과) | {row['license_name']}")
        if len(expired_items) > 200:
            expired_lines.append(f"- ... 외 {len(expired_items) - 200}건")
    else:
        expired_lines.append("- 대상 없음")

    user_items = expiring_lines + ([""] if expiring_lines and expired_lines else []) + expired_lines

    token_values = {
        "DATE": today_text,
        "NOTIFY_DAYS": str(int(config.get("notify_days") or 30)),
        "USER_ID": username,
        "USER_NAME": display_name or username,
        "USER_EMAIL": email,
        "USER_EXPIRING_COUNT": str(len(expiring_items)),
        "USER_EXPIRED_COUNT": str(len(expired_items)),
        "EXPIRING_ITEMS": "\n".join(expiring_lines),
        "EXPIRED_ITEMS": "\n".join(expired_lines),
        "USER_ITEMS": "\n".join(user_items),
    }

    subject_template = str(config.get("subject_template") or _default_software_user_mail_subject_template()).strip()
    body_template = str(config.get("body_template") or _default_software_user_mail_body_template()).strip()

    subject = _render_software_mail_template(subject_template, token_values).strip()
    if not subject:
        subject = _render_software_mail_template(_default_software_user_mail_subject_template(), token_values).strip()

    body = _render_software_mail_template(body_template, token_values).strip()
    if not body:
        body = _render_software_mail_template(_default_software_user_mail_body_template(), token_values).strip()

    return subject, body, len(expiring_items), len(expired_items)



def _build_software_user_mail_targets(user_config: dict, payload: dict) -> tuple[list[dict], dict[str, int]]:
    include_expired = bool(user_config.get("include_expired", True))
    only_active_users = bool(user_config.get("only_active_users", True))

    users: dict[str, dict] = {}

    def _touch_user(row: dict, kind: str):
        username = str(row.get("username") or "").strip()
        if not username:
            return

        user = users.setdefault(
            username,
            {
                "username": username,
                "display_name": str(row.get("display_name") or username),
                "email": str(row.get("email") or "").strip(),
                "is_active": bool(row.get("is_active", True)),
                "expiring_count": 0,
                "expired_count": 0,
                "expiring_license_names": [],
                "expired_license_names": [],
                "_expiring_license_seen": set(),
                "_expired_license_seen": set(),
            },
        )

        license_name = str(row.get("license_name") or "").strip()

        if kind == "expiring":
            user["expiring_count"] = int(user.get("expiring_count") or 0) + 1
            if license_name and license_name not in user["_expiring_license_seen"]:
                user["_expiring_license_seen"].add(license_name)
                user["expiring_license_names"].append(license_name)
        else:
            user["expired_count"] = int(user.get("expired_count") or 0) + 1
            if license_name and license_name not in user["_expired_license_seen"]:
                user["_expired_license_seen"].add(license_name)
                user["expired_license_names"].append(license_name)

    for row in payload.get("expiring_items") or []:
        if isinstance(row, dict):
            _touch_user(row, "expiring")

    if include_expired:
        for row in payload.get("expired_items") or []:
            if isinstance(row, dict):
                _touch_user(row, "expired")

    rows: list[dict] = []
    sendable_users = 0
    skipped_no_email = 0
    skipped_inactive = 0

    for username in sorted(users.keys(), key=lambda key: ((str(users[key].get("display_name") or key)).lower(), key.lower())):
        user = users[username]
        email = str(user.get("email") or "").strip()
        is_active = bool(user.get("is_active", True))

        status = "발송대상"
        sendable = True

        if only_active_users and not is_active:
            status = "비활성 사용자 제외"
            sendable = False
            skipped_inactive += 1
        elif not email:
            status = "이메일 없음"
            sendable = False
            skipped_no_email += 1
        else:
            sendable_users += 1

        rows.append(
            {
                "username": username,
                "display_name": str(user.get("display_name") or username),
                "email": email or None,
                "is_active": is_active,
                "expiring_count": int(user.get("expiring_count") or 0),
                "expired_count": int(user.get("expired_count") or 0),
                "expiring_license_names": list(user.get("expiring_license_names") or []),
                "expired_license_names": list(user.get("expired_license_names") or []),
                "status": status,
                "sendable": sendable,
            }
        )

    summary = {
        "checked_licenses": int(payload.get("checked_licenses") or 0),
        "target_users": len(rows),
        "sendable_users": sendable_users,
        "skipped_no_email": skipped_no_email,
        "skipped_inactive": skipped_inactive,
        "expiring_count": int(payload.get("expiring_count") or 0),
        "expired_count": int(payload.get("expired_count") or 0) if include_expired else 0,
    }

    return rows, summary

def _preview_software_user_mail_targets(db: Session, user_config: dict) -> dict:
    payload = _collect_software_expiry_targets(db, int(user_config.get("notify_days") or 30))
    rows, summary = _build_software_user_mail_targets(user_config, payload)
    return {
        **summary,
        "rows": rows,
    }

def _send_software_user_expiry_alarm(
    db: Session,
    *,
    smtp_password: str | None = None,
    force_send_when_empty: bool = False,
) -> dict[str, int]:
    user_config = _get_software_user_mail_config(db)
    smtp_config = _get_mail_smtp_config(db)
    payload = _collect_software_expiry_targets(db, int(user_config.get("notify_days") or 30))
    rows, summary = _build_software_user_mail_targets(user_config, payload)

    if int(summary.get("target_users") or 0) == 0 and not force_send_when_empty:
        result = {
            **summary,
            "sent_users": 0,
            "failed_users": 0,
        }
        _set_software_user_mail_state(db, last_error=None, last_result=result)
        return {**result, "sent": 0}

    runtime_password = str(smtp_password or "").strip() or _ensure_runtime_software_mail_password(db)

    sent_users = 0
    failed_users = 0
    first_error: str | None = None

    for user in rows:
        if not bool(user.get("sendable")):
            continue

        username = str(user.get("username") or "").strip()
        email = str(user.get("email") or "").strip()

        if not username or not email:
            continue

        try:
            subject, body, _, _ = _compose_software_user_expiry_mail(
                user_config,
                username,
                str(user.get("display_name") or username),
                email,
                payload,
            )
            _send_mail_via_smtp(smtp_config, runtime_password, subject, body, recipients=[email])
            sent_users += 1
        except Exception as e:
            failed_users += 1
            if first_error is None:
                first_error = str(e)

    result = {
        **summary,
        "sent_users": sent_users,
        "failed_users": failed_users,
    }

    _set_software_user_mail_state(
        db,
        last_sent_at=datetime.now(timezone.utc),
        last_error=(f"사용자 메일 일부 발송 실패: {first_error}" if first_error else None),
        last_result=result,
    )

    return {**result, "sent": sent_users}

def _is_mail_schedule_due(config: dict, state: dict, now: datetime) -> bool:
    if not config.get("enabled"):
        return False

    schedule_hour = int(config.get("schedule_hour") or 9)
    schedule_minute = int(config.get("schedule_minute") or 0)
    if (now.hour, now.minute) < (schedule_hour, schedule_minute):
        return False

    last_sent = _parse_iso_datetime(state.get("last_sent_at"))
    if last_sent and last_sent.astimezone(KST).date() == now.date():
        return False

    return True

def _run_software_mail_scheduled_once(db: Session):
    now = datetime.now(KST)

    admin_config = _get_software_mail_config(db)
    admin_state = _get_software_mail_state(db)
    if _is_mail_schedule_due(admin_config, admin_state, now):
        try:
            result = _send_software_expiry_alarm(db, force_send_when_empty=False)
            if int(result.get("sent") or 0) == 0:
                _set_software_mail_state(db, last_sent_at=datetime.now(timezone.utc), last_error=None, last_result=result)
        except Exception as e:
            _set_software_mail_state(db, last_error=f"관리자 메일 발송 실패: {e}")

    user_config = _get_software_user_mail_config(db)
    user_state = _get_software_user_mail_state(db)
    if _is_mail_schedule_due(user_config, user_state, now):
        try:
            result = _send_software_user_expiry_alarm(db, force_send_when_empty=False)
            if int(result.get("sent") or 0) == 0 and int(result.get("failed_users") or 0) == 0:
                _set_software_user_mail_state(db, last_sent_at=datetime.now(timezone.utc), last_error=None, last_result=result)
        except Exception as e:
            _set_software_user_mail_state(db, last_error=f"사용자 메일 발송 실패: {e}")

def _software_mail_scheduler_loop():
    while not SOFTWARE_MAIL_SCHEDULER_STOP.wait(30):
        db = SessionLocal()
        try:
            _run_software_mail_scheduled_once(db)
        except Exception:
            pass
        finally:
            db.close()


def _start_software_mail_scheduler():
    global SOFTWARE_MAIL_SCHEDULER_THREAD

    if SOFTWARE_MAIL_SCHEDULER_THREAD and SOFTWARE_MAIL_SCHEDULER_THREAD.is_alive():
        return

    SOFTWARE_MAIL_SCHEDULER_STOP.clear()
    SOFTWARE_MAIL_SCHEDULER_THREAD = threading.Thread(
        target=_software_mail_scheduler_loop,
        name="software-mail-scheduler",
        daemon=True,
    )
    SOFTWARE_MAIL_SCHEDULER_THREAD.start()


def _stop_software_mail_scheduler():
    SOFTWARE_MAIL_SCHEDULER_STOP.set()


def _ldap_fetch_users(
    *,
    server_url: str,
    use_ssl: bool,
    port: int | None,
    bind_dn: str,
    bind_password: str,
    base_dn: str,
    user_id_attribute: str,
    user_name_attribute: str,
    user_email_attribute: str,
    user_department_attribute: str,
    user_title_attribute: str,
    manager_dn_attribute: str,
    user_dn_attribute: str,
    user_guid_attribute: str,
    query: str,
    size_limit: int,
) -> list[dict]:
    conn = None
    try:
        host, resolved_ssl, resolved_port = _resolve_ldap_server(server_url, use_ssl, port)
        server = Server(host=host, port=resolved_port, use_ssl=resolved_ssl, connect_timeout=8)
        conn = Connection(server, user=bind_dn, password=bind_password, auto_bind=True, receive_timeout=20)

        uid_attr = user_id_attribute.strip() or "sAMAccountName"
        name_attr = user_name_attribute.strip() or "displayName"
        mail_attr = user_email_attribute.strip() or "mail"
        dept_attr = user_department_attribute.strip() or "department"
        title_attr = user_title_attribute.strip() or "title"
        manager_attr = manager_dn_attribute.strip() or "manager"
        dn_attr = user_dn_attribute.strip() or "distinguishedName"
        guid_attr = user_guid_attribute.strip() or "objectGUID"

        def _unique_attr_names(values: list[str]) -> list[str]:
            result: list[str] = []
            for value in values:
                key = str(value or "").strip()
                if not key or key in result:
                    continue
                result.append(key)
            return result

        uid_attrs = _unique_attr_names([uid_attr, "sAMAccountName", "uid", "userPrincipalName"])
        name_attrs = _unique_attr_names([name_attr, "displayName", "cn", "name"])
        mail_attrs = _unique_attr_names([mail_attr, "mail", "userPrincipalName"])
        dept_attrs = _unique_attr_names([dept_attr, "department"])
        title_attrs = _unique_attr_names([title_attr, "title"])
        manager_attrs = _unique_attr_names([manager_attr, "manager"])
        dn_attrs = _unique_attr_names([dn_attr, "distinguishedName"])
        guid_attrs = _unique_attr_names([guid_attr, "objectGUID"])

        escaped_query = escape_filter_chars((query or "").strip())
        base_filter = "(&(objectClass=user)(!(objectClass=computer)))"
        if escaped_query:
            query_parts = [f"({attr}=*{escaped_query}*)" for attr in [*uid_attrs, *name_attrs, *mail_attrs]]
            query_filter = f"(|{''.join(query_parts)})"
            search_filter = f"(&{base_filter}{query_filter})"
        else:
            search_filter = base_filter

        attributes = _unique_attr_names([*uid_attrs, *name_attrs, *mail_attrs, *dept_attrs, *title_attrs, *manager_attrs, *dn_attrs, *guid_attrs])
        conn.search(
            search_base=base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=attributes,
            size_limit=size_limit,
        )

        users = []
        for entry in conn.entries:
            attrs = entry.entry_attributes_as_dict

            def _first_from(attr_names: list[str]) -> str | None:
                for attr_name in attr_names:
                    value = _first_attr_value(attrs.get(attr_name))
                    if value:
                        return value
                return None

            username = _first_from(uid_attrs)
            if not username:
                continue

            entry_dn = str(entry.entry_dn)
            users.append(
                {
                    "dn": entry_dn,
                    "username": username,
                    "display_name": _first_from(name_attrs) or username,
                    "email": _first_from(mail_attrs),
                    "department": _first_from(dept_attrs),
                    "title": _first_from(title_attrs),
                    "manager_dn": _first_from(manager_attrs),
                    "user_dn": _first_from(dn_attrs) or entry_dn,
                    "object_guid": _first_from(guid_attrs),
                }
            )

        return users
    finally:
        if conn is not None:
            conn.unbind()


def _sync_directory_users_now(
    db: Session,
    *,
    server_url: str,
    use_ssl: bool,
    port: int | None,
    bind_dn: str,
    bind_password: str,
    base_dn: str,
    user_id_attribute: str,
    user_name_attribute: str,
    user_email_attribute: str,
    user_department_attribute: str,
    user_title_attribute: str,
    manager_dn_attribute: str,
    user_dn_attribute: str,
    user_guid_attribute: str,
    size_limit: int,
) -> dict:
    users = _ldap_fetch_users(
        server_url=server_url,
        use_ssl=use_ssl,
        port=port,
        bind_dn=bind_dn,
        bind_password=bind_password,
        base_dn=base_dn,
        user_id_attribute=user_id_attribute,
        user_name_attribute=user_name_attribute,
        user_email_attribute=user_email_attribute,
        user_department_attribute=user_department_attribute,
        user_title_attribute=user_title_attribute,
        manager_dn_attribute=manager_dn_attribute,
        user_dn_attribute=user_dn_attribute,
        user_guid_attribute=user_guid_attribute,
        query="",
        size_limit=size_limit,
    )
    result = crud.upsert_directory_users(db, users, source="ldap", deactivate_missing=True, keep_inactive=True)
    result["total_synced"] = len(users)
    return result


def _run_ldap_scheduled_sync_once(db: Session):
    now = datetime.now(timezone.utc)
    schedule = _get_sync_schedule(db)
    state = _get_sync_state(db)

    if not schedule.get("enabled"):
        return

    last_attempt = _parse_iso_datetime(state.get("last_attempt_at"))
    interval = timedelta(minutes=schedule.get("interval_minutes", 60))
    if last_attempt and now - last_attempt < interval:
        return

    _set_sync_state(db, last_attempt_at=now, last_error=None, last_result=state.get("last_result"))

    runtime_password = _ensure_runtime_bind_password(db)

    if not runtime_password:
        if _has_persisted_bind_password(db):
            _set_sync_state(db, last_error="저장된 Bind 비밀번호를 복호화할 수 없습니다. LDAP_BIND_PASSWORD_KEY 또는 SECRET_KEY를 확인한 뒤 비밀번호를 다시 저장해주세요.")
        else:
            _set_sync_state(db, last_error="스케줄 동기화를 위한 Bind 비밀번호가 설정되지 않았습니다.")
        return

    try:
        result = _sync_directory_users_now(
            db,
            server_url=schedule["server_url"],
            use_ssl=schedule["use_ssl"],
            port=schedule["port"],
            bind_dn=schedule["bind_dn"],
            bind_password=runtime_password,
            base_dn=schedule["base_dn"],
            user_id_attribute=schedule["user_id_attribute"],
            user_name_attribute=schedule["user_name_attribute"],
            user_email_attribute=schedule["user_email_attribute"],
            user_department_attribute=schedule["user_department_attribute"],
            user_title_attribute=schedule["user_title_attribute"],
            manager_dn_attribute=schedule["manager_dn_attribute"],
            user_dn_attribute=schedule["user_dn_attribute"],
            user_guid_attribute=schedule["user_guid_attribute"],
            size_limit=schedule["size_limit"],
        )
        _set_sync_state(db, last_synced_at=now, last_error=None, last_result=result)
    except (LDAPException, ValueError) as e:
        _set_sync_state(db, last_error=f"LDAP 동기화 실패: {e}")


def _ldap_scheduler_loop():
    while not LDAP_SCHEDULER_STOP.wait(20):
        db = SessionLocal()
        try:
            _run_ldap_scheduled_sync_once(db)
        except Exception:
            pass
        finally:
            db.close()


def _start_ldap_scheduler():
    global LDAP_SCHEDULER_THREAD

    if LDAP_SCHEDULER_THREAD and LDAP_SCHEDULER_THREAD.is_alive():
        return

    LDAP_SCHEDULER_STOP.clear()
    LDAP_SCHEDULER_THREAD = threading.Thread(target=_ldap_scheduler_loop, name="ldap-sync-scheduler", daemon=True)
    LDAP_SCHEDULER_THREAD.start()


def _stop_ldap_scheduler():
    LDAP_SCHEDULER_STOP.set()

def _upgrade_schema_for_existing_db():
    if engine.url.get_backend_name() != "postgresql":
        return

    statements = [
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS asset_code VARCHAR(50)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS usage_type VARCHAR(30)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS manager VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS manufacturer VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS model_name VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS department VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS vendor VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS purchase_date DATE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS purchase_cost NUMERIC(12, 2)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS warranty_expiry DATE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS rental_start_date DATE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS rental_end_date DATE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS disposed_at TIMESTAMPTZ",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS license_category VARCHAR(40)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS subscription_type VARCHAR(30)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS license_scope VARCHAR(20)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS purchase_cost NUMERIC(14, 2)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS purchase_currency VARCHAR(10)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS assignee_details JSONB",
        "ALTER TABLE directory_users ADD COLUMN IF NOT EXISTS manager_dn VARCHAR(500)",
        "ALTER TABLE directory_users ADD COLUMN IF NOT EXISTS user_dn VARCHAR(500)",
        "ALTER TABLE directory_users ADD COLUMN IF NOT EXISTS object_guid VARCHAR(80)",
    ]

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))

        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_assets_asset_code ON assets (asset_code)"))
        conn.execute(text("ALTER TABLE assets ALTER COLUMN serial_number DROP NOT NULL"))
        conn.execute(text("UPDATE assets SET owner = '미지정' WHERE owner IS NULL OR owner = ''"))
        conn.execute(text("UPDATE assets SET location = '미지정' WHERE location IS NULL OR location = ''"))
        conn.execute(text("UPDATE assets SET manager = COALESCE(NULLIF(manager, ''), owner, '미지정')"))
        conn.execute(text("UPDATE assets SET disposed_at = COALESCE(disposed_at, updated_at, now()) WHERE status = '폐기완료'"))
        conn.execute(text("UPDATE assets SET disposed_at = NULL WHERE status <> '폐기완료'"))

        conn.execute(
            text(
                "UPDATE assets SET usage_type = CASE "
                "WHEN usage_type IN ('주장비', 'primary') THEN '주장비' "
                "WHEN usage_type IN ('대여장비', 'loaner') THEN '대여장비' "
                "WHEN usage_type IN ('프로젝트장비', 'project') THEN '프로젝트장비' "
                "WHEN usage_type IN ('보조장비', 'auxiliary') THEN '보조장비' "
                "WHEN usage_type IN ('서버장비', 'server') THEN '서버장비' "
                "WHEN usage_type IN ('네트워크장비', 'network') THEN '네트워크장비' "
                "WHEN usage_type IN ('기타장비', 'other') THEN '기타장비' "
                "ELSE COALESCE(NULLIF(usage_type, ''), '기타장비') END"
            )
        )

        conn.execute(text("UPDATE assets SET rental_start_date = NULL, rental_end_date = NULL WHERE usage_type <> '대여장비'"))

        conn.execute(
            text(
                "UPDATE assets SET status = CASE "
                "WHEN status IN ('active', 'assigned', 'in_use', '사용중') THEN '사용중' "
                "WHEN status IN ('available', 'maintenance', 'standby', '대기') THEN '대기' "
                "WHEN status IN ('retired', 'disposal_required', '폐기필요') THEN '폐기필요' "
                "WHEN status IN ('disposed', 'disposal_done', '폐기완료') THEN '폐기완료' "
                "ELSE '대기' END"
            )
        )

        conn.execute(
            text(
                "UPDATE assets "
                "SET asset_code = 'AST-' || LPAD(id::text, 5, '0') "
                "WHERE asset_code IS NULL"
            )
        )

        conn.execute(text("UPDATE software_licenses SET license_category = COALESCE(NULLIF(license_category, ''), '기타')"))
        conn.execute(
            text(
                "UPDATE software_licenses SET subscription_type = CASE "
                "WHEN subscription_type IS NOT NULL AND subscription_type <> '' THEN subscription_type "
                "WHEN license_type IN ('영구', '영구 구매') THEN '영구 구매' "
                "WHEN license_type IN ('월 구독') THEN '월 구독' "
                "WHEN license_type IN ('사용량만큼 지불') THEN '사용량만큼 지불' "
                "ELSE '연 구독' END"
            )
        )
        conn.execute(text("UPDATE software_licenses SET purchase_currency = COALESCE(NULLIF(purchase_currency, ''), '원')"))
        conn.execute(
            text(
                "UPDATE software_licenses SET license_scope = CASE "
                "WHEN license_scope IN ('필수', 'required', 'mandatory', 'critical') THEN '필수' "
                "WHEN license_scope IN ('일반', 'general') THEN '일반' "
                "ELSE '일반' END"
            )
        )
        conn.execute(text("UPDATE software_licenses SET license_type = COALESCE(NULLIF(subscription_type, ''), '연 구독')"))



def _resolve_ldap_server(server_url: str, use_ssl: bool, port: int | None) -> tuple[str, bool, int]:
    raw = server_url.strip()
    if not raw:
        raise ValueError("ldap_server_required")

    resolved_ssl = bool(use_ssl)
    resolved_port = port
    host = raw

    if "://" in raw:
        parsed = urlparse(raw)
        host = parsed.hostname or ""
        if parsed.scheme.lower() == "ldaps":
            resolved_ssl = True
        if parsed.port:
            resolved_port = parsed.port

    if not host:
        raise ValueError("ldap_server_required")

    if not resolved_port:
        resolved_port = 636 if resolved_ssl else 389

    return host, resolved_ssl, resolved_port


def _first_attr_value(values):
    def _to_text(raw) -> str | None:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            if len(raw) == 16:
                try:
                    return str(uuid.UUID(bytes_le=raw))
                except (ValueError, TypeError):
                    pass
            return raw.hex() if raw else None

        text = str(raw).strip()
        return text if text else None

    if values is None:
        return None
    if isinstance(values, list):
        for item in values:
            text = _to_text(item)
            if text:
                return text
        return None

    return _to_text(values)

def _value_error_message(err: ValueError) -> str:
    if str(err) == "owner_required_for_in_use":
        return "사용중 상태로 변경하려면 사용자를 지정해야 합니다"
    if str(err) == "rental_period_invalid":
        return "대여 만료일자는 대여 시작일자보다 빠를 수 없습니다"
    if str(err) == "category_immutable":
        return "카테고리는 자산 생성 후 변경할 수 없습니다"
    return "요청 값을 확인해주세요"



def _decode_csv_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 파일 인코딩을 확인해주세요 (UTF-8 또는 CP949)")


def _normalize_csv_row(raw_row: dict) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (raw_row or {}).items():
        if key is None:
            continue
        key_text = str(key).strip().lower()
        if not key_text:
            continue
        normalized[key_text] = str(value or "").strip()
    return normalized


def _pick_csv_value(row: dict[str, str], aliases: list[str]) -> str:
    for alias in aliases:
        value = row.get(str(alias).strip().lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_csv_date(value: str, field_name: str):
    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"{field_name} 날짜 형식이 올바르지 않습니다 (예: 2026-03-27)")


def _parse_csv_float(value: str, field_name: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError as err:
        raise ValueError(f"{field_name} 숫자 형식이 올바르지 않습니다") from err


def _parse_csv_int(value: str, field_name: str, default: int = 1) -> int:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError as err:
        raise ValueError(f"{field_name} 정수 형식이 올바르지 않습니다") from err


def _normalize_import_kind(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"hw", "hardware", "하드웨어", "자산", "asset", "it_asset", "itasset"}:
        return "hw"
    if text in {"sw", "software", "소프트웨어", "license", "licence", "라이선스", "라이센스"}:
        return "sw"
    return ""


def _build_hw_asset_payload(row: dict[str, str]) -> schemas.AssetCreate:
    name = _pick_csv_value(row, ["자산명", "name", "asset_name"])
    category = _pick_csv_value(row, ["카테고리", "category"])

    if not name:
        raise ValueError("HW 자산명은 필수입니다")
    if not category:
        raise ValueError("HW 카테고리는 필수입니다")

    return schemas.AssetCreate(
        name=name,
        category=category,
        usage_type=_pick_csv_value(row, ["사용분류", "usage_type", "usage"]) or "기타장비",
        status=_pick_csv_value(row, ["상태", "status"]) or "대기",
        owner=_pick_csv_value(row, ["사용자", "owner", "assignee"]) or "미지정",
        manager=_pick_csv_value(row, ["담당자", "manager"]) or "미지정",
        department=_pick_csv_value(row, ["부서", "department"]) or None,
        location=_pick_csv_value(row, ["위치", "location"]) or "미지정",
        manufacturer=_pick_csv_value(row, ["제조사", "manufacturer"]) or None,
        model_name=_pick_csv_value(row, ["모델명", "model_name", "model"]) or None,
        serial_number=_pick_csv_value(row, ["시리얼번호", "serial_number", "serial"]) or None,
        asset_code=_pick_csv_value(row, ["자산코드", "asset_code"]) or None,
        vendor=_pick_csv_value(row, ["구매처", "vendor"]) or None,
        purchase_date=_parse_csv_date(_pick_csv_value(row, ["구매일", "purchase_date"]), "HW 구매일"),
        warranty_expiry=_parse_csv_date(_pick_csv_value(row, ["보증만료일", "warranty_expiry", "warranty"]), "HW 보증만료일"),
        purchase_cost=_parse_csv_float(_pick_csv_value(row, ["구매금액", "purchase_cost"]), "HW 구매금액"),
        rental_start_date=_parse_csv_date(_pick_csv_value(row, ["대여시작일", "대여시작일자", "rental_start_date"]), "HW 대여시작일"),
        rental_end_date=_parse_csv_date(_pick_csv_value(row, ["대여만료일", "대여만료일자", "rental_end_date"]), "HW 대여만료일"),
        notes=_pick_csv_value(row, ["메모", "notes", "비고"]) or None,
    )


def _build_sw_license_payload(row: dict[str, str]) -> schemas.SoftwareLicenseCreate:
    product_name = _pick_csv_value(row, ["라이선스명", "product_name", "software_name"])
    if not product_name:
        raise ValueError("SW 라이선스명은 필수입니다")

    total_quantity = _parse_csv_int(_pick_csv_value(row, ["총수량", "총 보유량", "total_quantity"]), "SW 총수량", default=1)
    if total_quantity < 1:
        raise ValueError("SW 총수량은 1 이상이어야 합니다")

    return schemas.SoftwareLicenseCreate(
        product_name=product_name,
        vendor=_pick_csv_value(row, ["공급사", "vendor", "구매처"]) or None,
        license_category=_pick_csv_value(row, ["라이선스구분", "sw구분", "license_category", "category"]) or "기타",
        license_scope=_pick_csv_value(row, ["라이선스성격", "성격", "license_scope", "scope", "필수여부"]) or "일반",
        subscription_type=_pick_csv_value(row, ["구독형태", "subscription_type", "purchase_model"]) or "연 구독",
        start_date=_parse_csv_date(_pick_csv_value(row, ["라이선스시작일", "시작일", "start_date"]), "SW 라이선스시작일"),
        end_date=_parse_csv_date(_pick_csv_value(row, ["라이선스만료일", "만료일", "end_date"]), "SW 라이선스만료일"),
        purchase_cost=_parse_csv_float(_pick_csv_value(row, ["라이선스구매비용", "구매비용", "purchase_cost"]), "SW 구매비용"),
        purchase_currency=_pick_csv_value(row, ["통화", "purchase_currency", "currency"]) or "원",
        total_quantity=total_quantity,
        assignees=[],
        assignee_details=[],
        drafter=_pick_csv_value(row, ["기안자", "drafter"]) or None,
        notes=_pick_csv_value(row, ["메모", "notes", "비고"]) or None,
    )

def _import_csv_rows(
    reader: csv.DictReader,
    db: Session,
    current_user: models.User,
    forced_kind: str | None = None,
) -> dict:
    total_rows = 0
    processed_rows = 0
    created_hardware = 0
    created_software = 0
    failed_rows = 0
    errors: list[dict[str, str | int | None]] = []

    for row_index, raw_row in enumerate(reader, start=2):
        row = _normalize_csv_row(raw_row)
        if not any(str(value or "").strip() for value in row.values()):
            continue

        total_rows += 1

        if forced_kind in {"hw", "sw"}:
            kind = forced_kind
        else:
            kind_raw = _pick_csv_value(row, ["자산유형", "type", "kind", "구분"])
            kind = _normalize_import_kind(kind_raw)

        kind_label = "HW" if kind == "hw" else "SW" if kind == "sw" else None

        if kind not in {"hw", "sw"}:
            failed_rows += 1
            errors.append({"row": row_index, "kind": None, "message": "자산유형은 HW 또는 SW로 입력해주세요"})
            continue

        try:
            if kind == "hw":
                payload = _build_hw_asset_payload(row)
                crud.create_asset(db, payload, actor=current_user)
                created_hardware += 1
            else:
                payload = _build_sw_license_payload(row)
                crud.create_software_license(db, payload)
                created_software += 1

            processed_rows += 1
        except IntegrityError:
            db.rollback()
            failed_rows += 1
            msg = "중복된 자산코드 또는 시리얼번호가 있습니다" if kind == "hw" else "중복 또는 제약조건 오류가 있습니다"
            errors.append({"row": row_index, "kind": kind_label, "message": msg})
        except ValueError as e:
            db.rollback()
            msg = _value_error_message(e) if kind == "hw" else str(e)
            errors.append({"row": row_index, "kind": kind_label, "message": msg})
            failed_rows += 1
        except Exception:
            db.rollback()
            failed_rows += 1
            errors.append({"row": row_index, "kind": kind_label, "message": "행 처리 중 알 수 없는 오류가 발생했습니다"})

    return {
        "ok": True,
        "total_rows": total_rows,
        "processed_rows": processed_rows,
        "created_hardware": created_hardware,
        "created_software": created_software,
        "failed_rows": failed_rows,
        "errors": errors,
    }


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _upgrade_schema_for_existing_db()

    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")

    db = SessionLocal()
    try:
        existing_admin = crud.get_user_by_username(db, admin_username)
        if existing_admin is None:
            crud.create_user(
                db=db,
                username=admin_username,
                password_hash=security.hash_password(admin_password),
                role="admin",
            )

        _ensure_runtime_bind_password(db)
        _ensure_runtime_software_mail_password(db)
    finally:
        db.close()

    _start_ldap_scheduler()
    _start_software_mail_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    _stop_ldap_scheduler()
    _stop_software_mail_scheduler()


@app.get("/", include_in_schema=False)
def web_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", summary="헬스 체크", tags=["대시보드"])
def health_check():
    return {"status": "ok"}


@app.post("/auth/login", response_model=schemas.TokenResponse, summary="로그인", tags=["인증"])
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = security.authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")

    access_token = security.create_access_token(
        subject=user.username,
        role=user.role,
        expires_delta=timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return schemas.TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=security.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@app.get("/me", response_model=schemas.UserResponse, summary="내 계정 조회", tags=["인증"])
def get_me(current_user: models.User = Depends(security.get_current_user)):
    return current_user


@app.post("/users", response_model=schemas.UserResponse, status_code=201, summary="사용자 생성", tags=["사용자"])
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    if crud.get_user_by_username(db, payload.username):
        raise HTTPException(status_code=409, detail="이미 존재하는 사용자명입니다")

    try:
        return crud.create_user(
            db=db,
            username=payload.username,
            password_hash=security.hash_password(payload.password),
            role=payload.role,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 존재하는 사용자명입니다")



@app.get("/users", response_model=list[schemas.UserResponse], summary="사용자 목록 조회", tags=["사용자"])
def list_users(
    role: str | None = None,
    q: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    if role and role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="role은 user 또는 admin 이어야 합니다")

    safe_limit = max(1, min(limit, 500))
    return crud.list_users(db, role=role, q=q, limit=safe_limit)


@app.put("/users/{user_id}", response_model=schemas.UserResponse, summary="사용자 정보 수정", tags=["사용자"])
def update_user_admin(
    user_id: int,
    payload: schemas.UserAdminUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    password_hash = None
    if updates.get("password"):
        password_hash = security.hash_password(updates["password"])

    return crud.update_user_admin(
        db,
        db_user,
        is_active=updates.get("is_active"),
        password_hash=password_hash,
    )


@app.get("/directory-users", response_model=list[schemas.DirectoryUserResponse], summary="동기화 사용자 목록", tags=["LDAP"])
def list_directory_users(
    q: str | None = None,
    limit: int = 200,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    safe_limit = max(1, min(limit, 5000))
    return crud.list_directory_users(db, q=q, limit=safe_limit, include_inactive=include_inactive)



@app.post("/directory-users", response_model=schemas.DirectoryUserResponse, status_code=201, summary="할당 사용자 수동 추가", tags=["LDAP"])
def create_directory_user(
    payload: schemas.DirectoryUserCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        return crud.create_directory_user(db, payload, source="manual")
    except ValueError as e:
        if str(e) == "directory_user_exists":
            raise HTTPException(status_code=409, detail="이미 존재하는 사용자 ID입니다")
        raise HTTPException(status_code=400, detail="사용자 ID를 확인해주세요")


@app.put("/directory-users/{directory_user_id}", response_model=schemas.DirectoryUserResponse, summary="할당 사용자 수정", tags=["LDAP"])
def update_directory_user(
    directory_user_id: int,
    payload: schemas.DirectoryUserUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    db_user = crud.get_directory_user_by_id(db, directory_user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    if payload.model_dump(exclude_unset=True) == {}:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    return crud.update_directory_user(db, db_user, payload)


@app.post("/directory-users/import", response_model=schemas.DirectoryUserBulkImportResponse, summary="LDAP 검색결과 일괄 반영", tags=["LDAP"])
def import_directory_users(
    payload: schemas.DirectoryUserBulkImportRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    users = [item.model_dump() for item in payload.users]
    result = crud.upsert_directory_users(db, users, source="ldap", deactivate_missing=False)
    return {
        "ok": True,
        "message": "LDAP 검색결과를 사용자 탭에 반영했습니다",
        "result": result,
    }


@app.get("/dashboard/summary", response_model=schemas.DashboardSummaryResponse, summary="자산 현황 요약", tags=["대시보드"])
def dashboard_summary(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return crud.get_dashboard_summary(db)


@app.get("/settings/exchange-rate", response_model=schemas.ExchangeRateSettingResponse, summary="USD->KRW 환율 조회", tags=["설정"])
def get_exchange_rate_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return crud.get_exchange_rate_setting(db)


@app.put("/settings/exchange-rate", response_model=schemas.ExchangeRateSettingResponse, summary="USD->KRW 환율 저장", tags=["설정"])
def set_exchange_rate_setting(
    payload: schemas.ExchangeRateSettingUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return crud.set_exchange_rate_setting(db, payload.usd_krw, payload.effective_date)


@app.get("/settings/mail/smtp", response_model=schemas.MailSmtpConfigResponse, summary="메일 SMTP 설정 조회", tags=["설정"])
def get_mail_smtp_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return _build_mail_smtp_config_response(db)


@app.put("/settings/mail/smtp", response_model=schemas.MailSmtpConfigResponse, summary="메일 SMTP 설정 저장", tags=["설정"])
def set_mail_smtp_setting(
    payload: schemas.MailSmtpConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        if payload.smtp_password:
            _set_runtime_software_mail_password(payload.smtp_password)
            _persist_software_mail_password(db, payload.smtp_password)
    except ValueError as e:
        if str(e) == "ldap_password_encryption_key_missing":
            raise HTTPException(status_code=400, detail="SMTP 비밀번호 암호화 키가 설정되지 않았습니다. SECRET_KEY 또는 LDAP_BIND_PASSWORD_KEY를 확인해주세요")
        raise

    return _update_mail_smtp_config(db, payload.model_dump(exclude={"smtp_password"}))


@app.get("/settings/mail/admin", response_model=schemas.MailAdminConfigResponse, summary="관리자 메일 설정 조회", tags=["설정"])
def get_mail_admin_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return _build_mail_admin_config_response(db)


@app.put("/settings/mail/admin", response_model=schemas.MailAdminConfigResponse, summary="관리자 메일 설정 저장", tags=["설정"])
def set_mail_admin_setting(
    payload: schemas.MailAdminConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return _update_mail_admin_config(db, payload.model_dump())


@app.get("/settings/mail/user", response_model=schemas.MailUserConfigResponse, summary="사용자 메일 설정 조회", tags=["설정"])
def get_mail_user_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return _build_mail_user_config_response(db)


@app.put("/settings/mail/user", response_model=schemas.MailUserConfigResponse, summary="사용자 메일 설정 저장", tags=["설정"])
def set_mail_user_setting(
    payload: schemas.MailUserConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return _update_mail_user_config(db, payload.model_dump())


@app.post("/settings/mail/user/preview-targets", response_model=schemas.MailUserPreviewResponse, summary="사용자 메일 대상자 미리보기", tags=["설정"])
def preview_mail_user_targets(
    payload: schemas.MailUserConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    config = _sanitize_software_user_mail_config(payload.model_dump())
    return _preview_software_user_mail_targets(db, config)

@app.post("/settings/mail/admin/send-now", response_model=schemas.MailSendNowResponse, summary="관리자 메일 즉시 발송", tags=["설정"])
def send_admin_mail_now(
    payload: schemas.MailSendNowRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    password = str(payload.smtp_password or "").strip() or None
    if password:
        _set_runtime_software_mail_password(password)

    try:
        result = _send_software_expiry_alarm(db, smtp_password=password, force_send_when_empty=True)
        return {
            "ok": True,
            "message": "관리자 만료 알림 메일을 발송했습니다",
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (smtplib.SMTPException, OSError) as e:
        raise HTTPException(status_code=400, detail=f"SMTP 발송 실패: {e}")


@app.post("/settings/mail/user/send-now", response_model=schemas.MailSendNowResponse, summary="사용자 메일 즉시 발송", tags=["설정"])
def send_user_mail_now(
    payload: schemas.MailSendNowRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    password = str(payload.smtp_password or "").strip() or None
    if password:
        _set_runtime_software_mail_password(password)

    try:
        result = _send_software_user_expiry_alarm(db, smtp_password=password, force_send_when_empty=True)
        return {
            "ok": True,
            "message": "사용자 만료 알림 메일을 발송했습니다",
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (smtplib.SMTPException, OSError) as e:
        raise HTTPException(status_code=400, detail=f"SMTP 발송 실패: {e}")

@app.get("/settings/software-expiry-mail", response_model=schemas.SoftwareExpiryMailConfigResponse, summary="소프트웨어 만료 메일 설정 조회", tags=["설정"])
def get_software_expiry_mail_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return _build_software_mail_config_response(db)


@app.put("/settings/software-expiry-mail", response_model=schemas.SoftwareExpiryMailConfigResponse, summary="소프트웨어 만료 메일 설정 저장", tags=["설정"])
def set_software_expiry_mail_setting(
    payload: schemas.SoftwareExpiryMailConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    config = _sanitize_software_mail_config(payload.model_dump(exclude={"smtp_password"}))
    crud.set_app_setting(db, SOFTWARE_MAIL_CONFIG_KEY, config)

    try:
        if payload.smtp_password:
            _set_runtime_software_mail_password(payload.smtp_password)
            _persist_software_mail_password(db, payload.smtp_password)
    except ValueError as e:
        if str(e) == "ldap_password_encryption_key_missing":
            raise HTTPException(status_code=400, detail="SMTP 비밀번호 암호화 키가 설정되지 않았습니다. SECRET_KEY 또는 LDAP_BIND_PASSWORD_KEY를 확인해주세요")
        raise

    return _build_software_mail_config_response(db)


@app.post("/settings/software-expiry-mail/send-now", response_model=schemas.SoftwareExpiryMailSendNowResponse, summary="소프트웨어 만료 메일 즉시 발송", tags=["설정"])
def send_software_expiry_mail_now(
    payload: schemas.SoftwareExpiryMailSendNowRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    password = str(payload.smtp_password or "").strip() or None
    if password:
        _set_runtime_software_mail_password(password)

    try:
        result = _send_software_expiry_alarm(db, smtp_password=password, force_send_when_empty=True)
        return {
            "ok": True,
            "message": "소프트웨어 만료 알림 메일을 발송했습니다",
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (smtplib.SMTPException, OSError) as e:
        raise HTTPException(status_code=400, detail=f"SMTP 발송 실패: {e}")


@app.post("/imports/hw-sw-csv", response_model=schemas.CsvHwSwImportResponse, summary="HW/SW CSV 통합 업로드", tags=["자산"])
async def import_hw_sw_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    filename = (file.filename or "").strip().lower()
    if filename and not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드할 수 있습니다")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다")

    try:
        csv_text = _decode_csv_text(raw_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 헤더를 찾을 수 없습니다")

    total_rows = 0
    processed_rows = 0
    created_hardware = 0
    created_software = 0
    failed_rows = 0
    errors: list[dict[str, str | int | None]] = []

    for row_index, raw_row in enumerate(reader, start=2):
        row = _normalize_csv_row(raw_row)
        if not any(str(value or "").strip() for value in row.values()):
            continue

        total_rows += 1
        kind_raw = _pick_csv_value(row, ["자산유형", "type", "kind", "구분"])
        kind = _normalize_import_kind(kind_raw)
        kind_label = "HW" if kind == "hw" else "SW" if kind == "sw" else None

        if not kind:
            failed_rows += 1
            errors.append({"row": row_index, "kind": None, "message": "자산유형은 HW 또는 SW로 입력해주세요"})
            continue

        try:
            if kind == "hw":
                payload = _build_hw_asset_payload(row)
                crud.create_asset(db, payload, actor=current_user)
                created_hardware += 1
            else:
                payload = _build_sw_license_payload(row)
                crud.create_software_license(db, payload)
                created_software += 1

            processed_rows += 1
        except IntegrityError:
            db.rollback()
            failed_rows += 1
            if kind == "hw":
                msg = "중복된 자산코드 또는 시리얼번호가 있습니다"
            else:
                msg = "중복 또는 제약조건 오류가 있습니다"
            errors.append({"row": row_index, "kind": kind_label, "message": msg})
        except ValueError as e:
            db.rollback()
            msg = _value_error_message(e) if kind == "hw" else str(e)
            errors.append({"row": row_index, "kind": kind_label, "message": msg})
            failed_rows += 1
        except Exception:
            db.rollback()
            failed_rows += 1
            errors.append({"row": row_index, "kind": kind_label, "message": "행 처리 중 알 수 없는 오류가 발생했습니다"})

    return {
        "ok": True,
        "total_rows": total_rows,
        "processed_rows": processed_rows,
        "created_hardware": created_hardware,
        "created_software": created_software,
        "failed_rows": failed_rows,
        "errors": errors,
    }
@app.post("/imports/hardware-csv", response_model=schemas.CsvHwSwImportResponse, summary="하드웨어 CSV 업로드", tags=["자산"])
async def import_hardware_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    filename = (file.filename or "").strip().lower()
    if filename and not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드할 수 있습니다")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다")

    try:
        csv_text = _decode_csv_text(raw_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 헤더를 찾을 수 없습니다")

    return _import_csv_rows(reader, db, current_user, forced_kind="hw")


@app.post("/imports/software-csv", response_model=schemas.CsvHwSwImportResponse, summary="소프트웨어 CSV 업로드", tags=["소프트웨어"])
async def import_software_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    filename = (file.filename or "").strip().lower()
    if filename and not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드할 수 있습니다")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다")

    try:
        csv_text = _decode_csv_text(raw_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 헤더를 찾을 수 없습니다")

    return _import_csv_rows(reader, db, current_user, forced_kind="sw")
@app.post("/software-licenses", response_model=schemas.SoftwareLicenseResponse, status_code=201, summary="소프트웨어 라이선스 등록", tags=["소프트웨어"])
def create_software_license(
    payload: schemas.SoftwareLicenseCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    try:
        return crud.create_software_license(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/software-licenses", response_model=list[schemas.SoftwareLicenseResponse], summary="소프트웨어 라이선스 목록", tags=["소프트웨어"])
def list_software_licenses(
    skip: int = 0,
    limit: int = 200,
    q: str | None = None,
    expiring_days: int | None = None,
    expired_only: bool = False,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    safe_limit = max(1, min(limit, 5000))
    return crud.list_software_licenses(
        db,
        skip=max(0, skip),
        limit=safe_limit,
        q=q,
        expiring_days=expiring_days,
        expired_only=expired_only,
    )


@app.get("/software-licenses/{license_id}", response_model=schemas.SoftwareLicenseResponse, summary="소프트웨어 라이선스 상세", tags=["소프트웨어"])
def get_software_license(
    license_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")
    return db_row


@app.put("/software-licenses/{license_id}", response_model=schemas.SoftwareLicenseResponse, summary="소프트웨어 라이선스 수정", tags=["소프트웨어"])
def update_software_license(
    license_id: int,
    payload: schemas.SoftwareLicenseUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")

    if payload.model_dump(exclude_unset=True) == {}:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    try:
        return crud.update_software_license(db, db_row, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/software-licenses/{license_id}", status_code=204, summary="소프트웨어 라이선스 삭제", tags=["소프트웨어"])
def delete_software_license(
    license_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")

    crud.delete_software_license(db, db_row)
@app.post("/ldap/test", summary="LDAP 연결 테스트", tags=["LDAP"])
def ldap_test(
    payload: schemas.LdapTestRequest,
    _: models.User = Depends(security.get_current_user),
):
    try:
        host, use_ssl, port = _resolve_ldap_server(payload.server_url, payload.use_ssl, payload.port)
        server = Server(host=host, port=port, use_ssl=use_ssl, connect_timeout=8)
        conn = Connection(server, user=payload.bind_dn, password=payload.bind_password, auto_bind=True, receive_timeout=12)
        conn.unbind()
        return {"ok": True, "message": "LDAP 연결 성공"}
    except LDAPException as e:
        raise HTTPException(status_code=400, detail=f"LDAP 연결 실패: {e}")
    except ValueError:
        raise HTTPException(status_code=400, detail="LDAP 서버 주소를 확인해주세요")


@app.post("/ldap/search", response_model=schemas.LdapSearchResponse, summary="LDAP 사용자 검색", tags=["LDAP"])
def ldap_search(
    payload: schemas.LdapSearchRequest,
    _: models.User = Depends(security.get_current_user),
):
    try:
        users = _ldap_fetch_users(
            server_url=payload.server_url,
            use_ssl=payload.use_ssl,
            port=payload.port,
            bind_dn=payload.bind_dn,
            bind_password=payload.bind_password,
            base_dn=payload.base_dn,
            user_id_attribute=payload.user_id_attribute,
            user_name_attribute=payload.user_name_attribute,
            user_email_attribute=payload.user_email_attribute,
            user_department_attribute=payload.user_department_attribute,
            user_title_attribute=payload.user_title_attribute,
            manager_dn_attribute=payload.manager_dn_attribute,
            user_dn_attribute=payload.user_dn_attribute,
            user_guid_attribute=payload.user_guid_attribute,
            query=payload.query,
            size_limit=payload.size_limit,
        )
        return {"total": len(users), "users": users}
    except LDAPException as e:
        raise HTTPException(status_code=400, detail=f"LDAP 검색 실패: {e}")
    except ValueError:
        raise HTTPException(status_code=400, detail="LDAP 서버 주소를 확인해주세요")


@app.post("/ldap/sync-now", response_model=schemas.LdapSyncNowResponse, summary="LDAP 사용자 즉시 동기화", tags=["LDAP"])
def ldap_sync_now(
    payload: schemas.LdapSyncNowRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    started_at = datetime.now(timezone.utc)
    _set_sync_state(db, last_attempt_at=started_at, last_error=None, last_result=None)

    try:
        result = _sync_directory_users_now(
            db,
            server_url=payload.server_url,
            use_ssl=payload.use_ssl,
            port=payload.port,
            bind_dn=payload.bind_dn,
            bind_password=payload.bind_password,
            base_dn=payload.base_dn,
            user_id_attribute=payload.user_id_attribute,
            user_name_attribute=payload.user_name_attribute,
            user_email_attribute=payload.user_email_attribute,
            user_department_attribute=payload.user_department_attribute,
            user_title_attribute=payload.user_title_attribute,
            manager_dn_attribute=payload.manager_dn_attribute,
            user_dn_attribute=payload.user_dn_attribute,
            user_guid_attribute=payload.user_guid_attribute,
            size_limit=payload.size_limit,
        )

        if payload.save_for_schedule:
            _set_runtime_bind_password(payload.bind_password)
            _persist_bind_password(db, payload.bind_password)

        _set_sync_state(db, last_synced_at=started_at, last_error=None, last_result=result)
        return {
            "ok": True,
            "message": "LDAP 사용자 동기화 완료",
            "result": result,
        }
    except LDAPException as e:
        _set_sync_state(db, last_error=f"LDAP 동기화 실패: {e}", last_result=None)
        raise HTTPException(status_code=400, detail=f"LDAP 동기화 실패: {e}")
    except ValueError as e:
        if str(e) == "ldap_password_encryption_key_missing":
            _set_sync_state(db, last_error="LDAP 비밀번호 암호화 키가 설정되지 않았습니다.", last_result=None)
            raise HTTPException(status_code=400, detail="LDAP 비밀번호 암호화 키가 설정되지 않았습니다. SECRET_KEY 또는 LDAP_BIND_PASSWORD_KEY를 확인해주세요")

        _set_sync_state(db, last_error="LDAP 서버 주소를 확인해주세요", last_result=None)
        raise HTTPException(status_code=400, detail="LDAP 서버 주소를 확인해주세요")


@app.get("/ldap/sync-schedule", response_model=schemas.LdapSyncScheduleResponse, summary="LDAP 동기화 스케줄 조회", tags=["LDAP"])
def get_ldap_sync_schedule(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return _build_sync_schedule_response(db)


@app.put("/ldap/sync-schedule", response_model=schemas.LdapSyncScheduleResponse, summary="LDAP 동기화 스케줄 저장", tags=["LDAP"])
def set_ldap_sync_schedule(
    payload: schemas.LdapSyncScheduleRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    schedule = _sanitize_sync_schedule(payload.model_dump(exclude={"bind_password"}))
    crud.set_app_setting(db, LDAP_SYNC_SCHEDULE_KEY, schedule)

    try:
        if payload.bind_password:
            _set_runtime_bind_password(payload.bind_password)
            _persist_bind_password(db, payload.bind_password)
    except ValueError as e:
        if str(e) == "ldap_password_encryption_key_missing":
            raise HTTPException(status_code=400, detail="LDAP 비밀번호 암호화 키가 설정되지 않았습니다. SECRET_KEY 또는 LDAP_BIND_PASSWORD_KEY를 확인해주세요")
        raise

    return _build_sync_schedule_response(db)

@app.post("/assets", response_model=schemas.AssetResponse, status_code=201, summary="자산 등록", tags=["자산"])
def create_asset(
    asset: schemas.AssetCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    try:
        return crud.create_asset(db, asset, actor=current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="자산코드 또는 시리얼번호가 이미 존재합니다")
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=_value_error_message(e))


@app.get("/assets", response_model=list[schemas.AssetResponse], summary="자산 목록 조회", tags=["자산"])
def list_assets(
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    usage_type: str | None = None,
    category: str | None = None,
    department: str | None = None,
    q: str | None = None,
    exclude_disposed: bool = False,
    warranty_expiring_days: int | None = None,
    warranty_overdue: bool = False,
    rental_expiring_days: int | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return crud.list_assets(
        db,
        skip=skip,
        limit=limit,
        status=status,
        usage_type=usage_type,
        category=category,
        department=department,
        q=q,
        exclude_disposed=exclude_disposed,
        warranty_expiring_days=warranty_expiring_days,
        warranty_overdue=warranty_overdue,
        rental_expiring_days=rental_expiring_days,
    )


@app.get("/assets/{asset_id}", response_model=schemas.AssetResponse, summary="자산 상세 조회", tags=["자산"])
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")
    return db_asset


@app.get("/assets/{asset_id}/history", response_model=list[schemas.AssetHistoryResponse], summary="자산 이력 조회", tags=["자산"])
def get_asset_history(
    asset_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    history = crud.list_asset_history(db, asset_id=asset_id, limit=limit)
    if not history and not crud.get_asset(db, asset_id):
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")
    return history


@app.put("/assets/{asset_id}", response_model=schemas.AssetResponse, summary="자산 정보 수정", tags=["자산"])
def update_asset(
    asset_id: int,
    payload: schemas.AssetUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    if payload.model_dump(exclude_unset=True) == {}:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    try:
        return crud.update_asset(db, db_asset, payload, actor=current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="자산코드 또는 시리얼번호가 이미 존재합니다")
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=_value_error_message(e))


@app.post("/assets/{asset_id}/assign", response_model=schemas.AssetResponse, summary="자산 할당", tags=["자산"])
def assign_asset(
    asset_id: int,
    payload: schemas.AssetAssignRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    try:
        return crud.assign_asset(db, db_asset, actor=current_user, payload=payload)
    except ValueError:
        raise HTTPException(status_code=400, detail="폐기완료 자산은 할당할 수 없습니다")


@app.post("/assets/{asset_id}/return", response_model=schemas.AssetResponse, summary="자산 반납", tags=["자산"])
def return_asset(
    asset_id: int,
    payload: schemas.AssetReturnRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    try:
        return crud.return_asset(db, db_asset, actor=current_user, payload=payload)
    except ValueError:
        raise HTTPException(status_code=400, detail="폐기완료 자산은 반납 처리할 수 없습니다")


@app.post("/assets/{asset_id}/mark-disposal-required", response_model=schemas.AssetResponse, summary="폐기필요 처리", tags=["자산"])
def mark_disposal_required(
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    return crud.mark_disposal_required(db, db_asset, actor=current_user, payload=payload)


@app.post("/assets/{asset_id}/mark-disposed", response_model=schemas.AssetResponse, summary="폐기완료 처리", tags=["자산"])
def mark_disposed(
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    return crud.mark_disposed(db, db_asset, actor=current_user, payload=payload)


@app.delete("/assets/{asset_id}", status_code=204, summary="자산 삭제", tags=["자산"])
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    if crud.normalize_status(db_asset.status) != "폐기완료":
        raise HTTPException(status_code=400, detail="폐기완료 자산만 삭제할 수 있습니다")

    crud.delete_asset(db, db_asset, actor=current_user)





















































































