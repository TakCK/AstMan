import os
from pathlib import Path

from sqlalchemy.orm import Session

from .. import crud
from . import branding_service

SYSTEM_INFO_SETTING_KEY = "system_info_settings"
SMTP_CONFIG_SETTING_KEY = "software_expiry_mail_config"
SMTP_PASSWORD_SETTING_KEY = "software_expiry_mail_password"
LDAP_SYNC_SCHEDULE_KEY = "ldap_sync_schedule"

DEFAULT_APP_VERSION = "0.7.0"
DEFAULT_SYSTEM_INFO_SETTING = {
    "external_access_url": "",
    "deployment_environment": "",
}


def _read_dict_setting(db: Session, key: str, default: dict | None = None) -> dict:
    value = crud.get_app_setting(db, key, default or {})
    return value if isinstance(value, dict) else {}


def _normalize_text(value: str | None, max_length: int = 500) -> str:
    return str(value or "").strip()[:max_length]


def _resolve_external_access_url(db: Session, settings_payload: dict) -> str:
    direct = _normalize_text(settings_payload.get("external_access_url"))
    if direct:
        return direct

    # Compatibility fallback when URL was stored under another key in app_settings.
    for key in ("service_public_url", "external_access_url"):
        payload = _read_dict_setting(db, key, {})
        candidate = _normalize_text(payload.get("value"))
        if candidate:
            return candidate
    return ""


def _is_logo_configured(logo_path: str) -> bool:
    normalized = _normalize_text(logo_path)
    if not normalized.startswith("/static/"):
        return False

    static_relative = normalized.replace("/static/", "", 1)
    logo_file = Path(branding_service.STATIC_DIR) / static_relative
    return logo_file.exists()


def _is_smtp_configured(db: Session) -> bool:
    config = _read_dict_setting(db, SMTP_CONFIG_SETTING_KEY, {})
    password_payload = _read_dict_setting(db, SMTP_PASSWORD_SETTING_KEY, {})

    smtp_host = _normalize_text(config.get("smtp_host"), 255)
    from_email = _normalize_text(config.get("from_email"), 255)
    has_stored_password = bool(_normalize_text(password_payload.get("ciphertext"), 5000))

    return bool(smtp_host and (from_email or has_stored_password))


def _is_ldap_configured(db: Session) -> bool:
    schedule = _read_dict_setting(db, LDAP_SYNC_SCHEDULE_KEY, {})

    server_url = _normalize_text(schedule.get("server_url"), 255)
    bind_dn = _normalize_text(schedule.get("bind_dn"), 255)
    base_dn = _normalize_text(schedule.get("base_dn"), 255)

    return bool(server_url and bind_dn and base_dn)


def get_system_info(db: Session) -> dict:
    system_info_payload = _read_dict_setting(db, SYSTEM_INFO_SETTING_KEY, DEFAULT_SYSTEM_INFO_SETTING)
    branding = branding_service.get_branding_settings(db)

    service_name = _normalize_text(branding.get("service_title"), 200) or branding_service.DEFAULT_BRANDING_SETTINGS["service_title"]
    version = _normalize_text(os.getenv("APP_VERSION"), 40) or DEFAULT_APP_VERSION
    deployment_environment = (
        _normalize_text(system_info_payload.get("deployment_environment"), 100)
        or _normalize_text(os.getenv("APP_ENV"), 100)
        or _normalize_text(os.getenv("ENVIRONMENT"), 100)
    )

    return {
        "service_name": service_name,
        "version": version,
        "external_access_url": _resolve_external_access_url(db, system_info_payload),
        "deployment_environment": deployment_environment,
        "logo_configured": _is_logo_configured(str(branding.get("company_logo_path") or "")),
        "smtp_configured": _is_smtp_configured(db),
        "ldap_configured": _is_ldap_configured(db),
        # Future extension point: fill SSL certificate expiry metadata here.
        "ssl_info": {
            "certificate_expires_at": None,
            "days_until_expiry": None,
        },
    }
