from typing import Any

from sqlalchemy.orm import Session

from .. import legacy_main as legacy

LDAP_SYNC_SCHEDULE_KEY = legacy.LDAP_SYNC_SCHEDULE_KEY
LDAP_SYNC_STATE_KEY = legacy.LDAP_SYNC_STATE_KEY


def _default_sync_schedule() -> dict:
    return legacy._default_sync_schedule()


def _sanitize_sync_schedule(raw: dict | None) -> dict:
    return legacy._sanitize_sync_schedule(raw)


def _parse_iso_datetime(value):
    return legacy._parse_iso_datetime(value)


def _iso_or_none(value):
    return legacy._iso_or_none(value)


def _resolve_ldap_server(server_url: str, use_ssl: bool, port: int | None):
    return legacy._resolve_ldap_server(server_url, use_ssl, port)


def _first_attr_value(values):
    return legacy._first_attr_value(values)


def _ldap_fetch_users(**kwargs):
    return legacy._ldap_fetch_users(**kwargs)


def _sync_directory_users_now(db: Session, **kwargs):
    return legacy._sync_directory_users_now(db, **kwargs)


def _build_sync_schedule_response(db: Session) -> dict:
    return legacy._build_sync_schedule_response(db)


def _get_sync_schedule(db: Session) -> dict:
    return legacy._get_sync_schedule(db)


def _get_sync_state(db: Session) -> dict:
    return legacy._get_sync_state(db)


def _set_sync_state(db: Session, **kwargs):
    return legacy._set_sync_state(db, **kwargs)


def _has_runtime_bind_password() -> bool:
    return legacy._has_runtime_bind_password()


def _set_runtime_bind_password(bind_password: str | None):
    return legacy._set_runtime_bind_password(bind_password)


def _persist_bind_password(db: Session, bind_password: str | None):
    return legacy._persist_bind_password(db, bind_password)


def ldap_test(payload: Any):
    return legacy.ldap_test(payload, None)


def ldap_search(payload: Any):
    return legacy.ldap_search(payload, None)


def ldap_sync_now(payload: Any, db: Session):
    return legacy.ldap_sync_now(payload, db, None)
