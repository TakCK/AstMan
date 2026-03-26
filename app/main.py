import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException
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
        {"name": "LDAP", "description": "사내 AD/LDAP 연동"},
    ],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")



LDAP_SYNC_SCHEDULE_KEY = "ldap_sync_schedule"
LDAP_SYNC_STATE_KEY = "ldap_sync_state"

LDAP_RUNTIME_LOCK = threading.Lock()
LDAP_RUNTIME_BIND_PASSWORD: str | None = None
LDAP_SCHEDULER_STOP = threading.Event()
LDAP_SCHEDULER_THREAD: threading.Thread | None = None


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
    return {
        **schedule,
        "has_runtime_password": _has_runtime_bind_password(),
        "last_synced_at": _parse_iso_datetime(state.get("last_synced_at")),
        "last_error": state.get("last_error"),
        "last_result": state.get("last_result"),
    }


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

        escaped_query = escape_filter_chars((query or "").strip())
        base_filter = "(&(objectClass=user)(!(objectClass=computer)))"
        if escaped_query:
            query_parts = [f"({attr}=*{escaped_query}*)" for attr in [*uid_attrs, *name_attrs, *mail_attrs]]
            query_filter = f"(|{''.join(query_parts)})"
            search_filter = f"(&{base_filter}{query_filter})"
        else:
            search_filter = base_filter

        attributes = _unique_attr_names([*uid_attrs, *name_attrs, *mail_attrs, "department", "title"])
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

            users.append(
                {
                    "dn": str(entry.entry_dn),
                    "username": username,
                    "display_name": _first_from(name_attrs) or username,
                    "email": _first_from(mail_attrs),
                    "department": _first_attr_value(attrs.get("department")),
                    "title": _first_attr_value(attrs.get("title")),
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

    with LDAP_RUNTIME_LOCK:
        runtime_password = LDAP_RUNTIME_BIND_PASSWORD

    if not runtime_password:
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
    if values is None:
        return None
    if isinstance(values, list):
        if not values:
            return None
        return str(values[0])
    text = str(values)
    return text if text else None

def _value_error_message(err: ValueError) -> str:
    if str(err) == "owner_required_for_in_use":
        return "사용중 상태로 변경하려면 사용자를 지정해야 합니다"
    if str(err) == "rental_period_invalid":
        return "대여 만료일자는 대여 시작일자보다 빠를 수 없습니다"
    if str(err) == "category_immutable":
        return "카테고리는 자산 생성 후 변경할 수 없습니다"
    return "요청 값을 확인해주세요"


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
    finally:
        db.close()

    _start_ldap_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    _stop_ldap_scheduler()


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
    safe_limit = max(1, min(limit, 1000))
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



@app.post("/software-licenses", response_model=schemas.SoftwareLicenseResponse, status_code=201, summary="소프트웨어 라이선스 등록", tags=["소프트웨어"])
def create_software_license(
    payload: schemas.SoftwareLicenseCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return crud.create_software_license(db, payload)


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
    safe_limit = max(1, min(limit, 1000))
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

    return crud.update_software_license(db, db_row, payload)


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
            size_limit=payload.size_limit,
        )

        if payload.save_for_schedule:
            _set_runtime_bind_password(payload.bind_password)

        _set_sync_state(db, last_synced_at=started_at, last_error=None, last_result=result)
        return {
            "ok": True,
            "message": "LDAP 사용자 동기화 완료",
            "result": result,
        }
    except LDAPException as e:
        _set_sync_state(db, last_error=f"LDAP 동기화 실패: {e}", last_result=None)
        raise HTTPException(status_code=400, detail=f"LDAP 동기화 실패: {e}")
    except ValueError:
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

    if payload.bind_password:
        _set_runtime_bind_password(payload.bind_password)

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

























