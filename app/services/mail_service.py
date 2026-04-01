from __future__ import annotations

import base64
import hashlib
import os
import smtplib
import threading
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..database import SessionLocal

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

LDAP_PASSWORD_CIPHER: Fernet | None = None


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

def ensure_runtime_software_mail_password(db: Session) -> str | None:
    return _ensure_runtime_software_mail_password(db)


def start_software_mail_scheduler() -> None:
    _start_software_mail_scheduler()


def stop_software_mail_scheduler() -> None:
    _stop_software_mail_scheduler()


def get_mail_smtp_setting(db: Session, _: models.User | None = None) -> dict:
    return _build_mail_smtp_config_response(db)


def set_mail_smtp_setting(payload: schemas.MailSmtpConfigUpdate, db: Session, _: models.User | None = None) -> dict:
    try:
        if payload.smtp_password:
            _set_runtime_software_mail_password(payload.smtp_password)
            _persist_software_mail_password(db, payload.smtp_password)
    except ValueError as e:
        if str(e) == "ldap_password_encryption_key_missing":
            raise HTTPException(status_code=400, detail="SMTP 비밀번호 암호화 키가 설정되지 않았습니다. SECRET_KEY 또는 LDAP_BIND_PASSWORD_KEY를 확인해주세요")
        raise

    return _update_mail_smtp_config(db, payload.model_dump(exclude={"smtp_password"}))


def get_mail_admin_setting(db: Session, _: models.User | None = None) -> dict:
    return _build_mail_admin_config_response(db)


def set_mail_admin_setting(payload: schemas.MailAdminConfigUpdate, db: Session, _: models.User | None = None) -> dict:
    return _update_mail_admin_config(db, payload.model_dump())


def get_mail_user_setting(db: Session, _: models.User | None = None) -> dict:
    return _build_mail_user_config_response(db)


def set_mail_user_setting(payload: schemas.MailUserConfigUpdate, db: Session, _: models.User | None = None) -> dict:
    return _update_mail_user_config(db, payload.model_dump())


def preview_mail_user_targets(payload: schemas.MailUserConfigUpdate, db: Session, _: models.User | None = None) -> dict:
    config = _sanitize_software_user_mail_config(payload.model_dump())
    return _preview_software_user_mail_targets(db, config)


def send_admin_mail_now(payload: schemas.MailSendNowRequest, db: Session, _: models.User | None = None) -> dict:
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


def send_user_mail_now(payload: schemas.MailSendNowRequest, db: Session, _: models.User | None = None) -> dict:
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


def get_software_expiry_mail_setting(db: Session, _: models.User | None = None) -> dict:
    return _build_software_mail_config_response(db)


def set_software_expiry_mail_setting(payload: schemas.SoftwareExpiryMailConfigUpdate, db: Session, _: models.User | None = None) -> dict:
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


def send_software_expiry_mail_now(payload: schemas.SoftwareExpiryMailSendNowRequest, db: Session, _: models.User | None = None) -> dict:
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

