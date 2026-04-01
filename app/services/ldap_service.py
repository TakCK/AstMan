import base64
import hashlib
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from ldap3 import Connection, SUBTREE, Server
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy.orm import Session

from .. import crud, schemas

LDAP_SYNC_SCHEDULE_KEY = "ldap_sync_schedule"
LDAP_SYNC_STATE_KEY = "ldap_sync_state"
LDAP_SYNC_PASSWORD_KEY = "ldap_sync_bind_password"

LDAP_RUNTIME_LOCK = threading.Lock()
LDAP_RUNTIME_BIND_PASSWORD: str | None = None
LDAP_PASSWORD_CIPHER: Fernet | None = None


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


def ldap_test(payload: schemas.LdapTestRequest):
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


def ldap_search(payload: schemas.LdapSearchRequest):
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


def ldap_sync_now(payload: schemas.LdapSyncNowRequest, db: Session):
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
