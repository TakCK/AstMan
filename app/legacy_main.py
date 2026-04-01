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
from .services import csv_import_service, ldap_service, mail_service, schema_upgrade_service

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



LDAP_SYNC_SCHEDULE_KEY = ldap_service.LDAP_SYNC_SCHEDULE_KEY
LDAP_SYNC_STATE_KEY = ldap_service.LDAP_SYNC_STATE_KEY
LDAP_SYNC_PASSWORD_KEY = ldap_service.LDAP_SYNC_PASSWORD_KEY

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

_default_sync_schedule = ldap_service._default_sync_schedule
_sanitize_sync_schedule = ldap_service._sanitize_sync_schedule
_parse_iso_datetime = ldap_service._parse_iso_datetime
_iso_or_none = ldap_service._iso_or_none
_get_ldap_cipher = ldap_service._get_ldap_cipher
_encrypt_bind_password = ldap_service._encrypt_bind_password
_decrypt_bind_password = ldap_service._decrypt_bind_password
_persist_bind_password = ldap_service._persist_bind_password
_has_persisted_bind_password = ldap_service._has_persisted_bind_password
_ensure_runtime_bind_password = ldap_service._ensure_runtime_bind_password
_get_sync_schedule = ldap_service._get_sync_schedule
_get_sync_state = ldap_service._get_sync_state
_set_sync_state = ldap_service._set_sync_state
_has_runtime_bind_password = ldap_service._has_runtime_bind_password
_set_runtime_bind_password = ldap_service._set_runtime_bind_password
_build_sync_schedule_response = ldap_service._build_sync_schedule_response
# Mail logic moved to services.mail_service
_default_software_mail_subject_template = mail_service._default_software_mail_subject_template
_default_software_mail_body_template = mail_service._default_software_mail_body_template
_default_software_mail_config = mail_service._default_software_mail_config
_sanitize_email_list = mail_service._sanitize_email_list
_sanitize_software_mail_config = mail_service._sanitize_software_mail_config
_get_software_mail_config = mail_service._get_software_mail_config
_get_software_mail_state = mail_service._get_software_mail_state
_set_software_mail_state = mail_service._set_software_mail_state
_set_runtime_software_mail_password = mail_service._set_runtime_software_mail_password
_persist_software_mail_password = mail_service._persist_software_mail_password
_has_persisted_software_mail_password = mail_service._has_persisted_software_mail_password
_ensure_runtime_software_mail_password = mail_service._ensure_runtime_software_mail_password
_build_software_mail_config_response = mail_service._build_software_mail_config_response
_default_software_user_mail_subject_template = mail_service._default_software_user_mail_subject_template
_default_software_user_mail_body_template = mail_service._default_software_user_mail_body_template
_default_software_user_mail_config = mail_service._default_software_user_mail_config
_sanitize_software_user_mail_config = mail_service._sanitize_software_user_mail_config
_get_software_user_mail_config = mail_service._get_software_user_mail_config
_get_software_user_mail_state = mail_service._get_software_user_mail_state
_set_software_user_mail_state = mail_service._set_software_user_mail_state
_get_mail_smtp_config = mail_service._get_mail_smtp_config
_build_mail_smtp_config_response = mail_service._build_mail_smtp_config_response
_build_mail_admin_config_response = mail_service._build_mail_admin_config_response
_build_mail_user_config_response = mail_service._build_mail_user_config_response
_update_mail_smtp_config = mail_service._update_mail_smtp_config
_update_mail_admin_config = mail_service._update_mail_admin_config
_update_mail_user_config = mail_service._update_mail_user_config
_normalize_optional_date = mail_service._normalize_optional_date
_collect_software_expiry_targets = mail_service._collect_software_expiry_targets
_render_software_mail_template = mail_service._render_software_mail_template
_compose_software_expiry_mail = mail_service._compose_software_expiry_mail
_send_mail_via_smtp = mail_service._send_mail_via_smtp
_send_software_expiry_alarm = mail_service._send_software_expiry_alarm
_compose_software_user_expiry_mail = mail_service._compose_software_user_expiry_mail
_build_software_user_mail_targets = mail_service._build_software_user_mail_targets
_preview_software_user_mail_targets = mail_service._preview_software_user_mail_targets
_send_software_user_expiry_alarm = mail_service._send_software_user_expiry_alarm
_is_mail_schedule_due = mail_service._is_mail_schedule_due
_run_software_mail_scheduled_once = mail_service._run_software_mail_scheduled_once
_software_mail_scheduler_loop = mail_service._software_mail_scheduler_loop
_start_software_mail_scheduler = mail_service._start_software_mail_scheduler
_stop_software_mail_scheduler = mail_service._stop_software_mail_scheduler

_ldap_fetch_users = ldap_service._ldap_fetch_users
_sync_directory_users_now = ldap_service._sync_directory_users_now
_run_ldap_scheduled_sync_once = ldap_service._run_ldap_scheduled_sync_once


def _ldap_scheduler_loop():
    from .jobs import ldap_sync_job

    ldap_sync_job._ldap_scheduler_loop()


def _start_ldap_scheduler():
    from .jobs import ldap_sync_job

    ldap_sync_job._start_ldap_scheduler()


def _stop_ldap_scheduler():
    from .jobs import ldap_sync_job

    ldap_sync_job._stop_ldap_scheduler()

def _upgrade_schema_for_existing_db():
    schema_upgrade_service.run_schema_upgrade(engine)


_resolve_ldap_server = ldap_service._resolve_ldap_server
_first_attr_value = ldap_service._first_attr_value
def _value_error_message(err: ValueError) -> str:
    if str(err) == "owner_required_for_in_use":
        return "사용중 상태로 변경하려면 사용자를 지정해야 합니다"
    if str(err) == "rental_period_invalid":
        return "대여 만료일자는 대여 시작일자보다 빠를 수 없습니다"
    if str(err) == "category_immutable":
        return "카테고리는 자산 생성 후 변경할 수 없습니다"
    return "요청 값을 확인해주세요"



# CSV import logic moved to services.csv_import_service
_decode_csv_text = csv_import_service._decode_csv_text
_normalize_csv_row = csv_import_service._normalize_csv_row
_pick_csv_value = csv_import_service._pick_csv_value
_parse_csv_date = csv_import_service._parse_csv_date
_parse_csv_float = csv_import_service._parse_csv_float
_parse_csv_int = csv_import_service._parse_csv_int
_normalize_import_kind = csv_import_service._normalize_import_kind
_build_hw_asset_payload = csv_import_service._build_hw_asset_payload
_build_sw_license_payload = csv_import_service._build_sw_license_payload
_import_csv_rows = csv_import_service._import_csv_rows


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


@app.post("/imports/hw-sw-csv", response_model=schemas.CsvHwSwImportResponse, summary="HW/SW CSV ?? ???", tags=["??"])
async def import_hw_sw_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    return await csv_import_service.import_csv_upload(file, db, current_user, forced_kind=None)


@app.post("/imports/hardware-csv", response_model=schemas.CsvHwSwImportResponse, summary="???? CSV ???", tags=["??"])
async def import_hardware_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    return await csv_import_service.import_csv_upload(file, db, current_user, forced_kind="hw")


@app.post("/imports/software-csv", response_model=schemas.CsvHwSwImportResponse, summary="????? CSV ???", tags=["?????"])
async def import_software_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    return await csv_import_service.import_csv_upload(file, db, current_user, forced_kind="sw")


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
    return ldap_service.ldap_test(payload)


@app.post("/ldap/search", response_model=schemas.LdapSearchResponse, summary="LDAP 사용자 검색", tags=["LDAP"])
def ldap_search(
    payload: schemas.LdapSearchRequest,
    _: models.User = Depends(security.get_current_user),
):
    return ldap_service.ldap_search(payload)


@app.post("/ldap/sync-now", response_model=schemas.LdapSyncNowResponse, summary="LDAP 사용자 즉시 동기화", tags=["LDAP"])
def ldap_sync_now(
    payload: schemas.LdapSyncNowRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return ldap_service.ldap_sync_now(payload, db)


@app.get("/ldap/sync-schedule", response_model=schemas.LdapSyncScheduleResponse, summary="LDAP 동기화 스케줄 조회", tags=["LDAP"])
def get_ldap_sync_schedule(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return ldap_service._build_sync_schedule_response(db)


@app.put("/ldap/sync-schedule", response_model=schemas.LdapSyncScheduleResponse, summary="LDAP 동기화 스케줄 저장", tags=["LDAP"])
def set_ldap_sync_schedule(
    payload: schemas.LdapSyncScheduleRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    schedule = ldap_service._sanitize_sync_schedule(payload.model_dump(exclude={"bind_password"}))
    crud.set_app_setting(db, ldap_service.LDAP_SYNC_SCHEDULE_KEY, schedule)

    try:
        if payload.bind_password:
            ldap_service._set_runtime_bind_password(payload.bind_password)
            ldap_service._persist_bind_password(db, payload.bind_password)
    except ValueError as e:
        if str(e) == "ldap_password_encryption_key_missing":
            raise HTTPException(status_code=400, detail="LDAP 비밀번호 암호화 키가 설정되지 않았습니다. SECRET_KEY 또는 LDAP_BIND_PASSWORD_KEY를 확인해주세요")
        raise

    return ldap_service._build_sync_schedule_response(db)
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



























































































