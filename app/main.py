import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import crud, security
from .database import Base, SessionLocal, engine
from .jobs import ldap_sync_job, software_mail_job
from .routers import assets, auth, branding, dashboard, ldap, orgs, software, users
from .services import ldap_service, mail_service, schema_upgrade_service

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
        {"name": "조직", "description": "조직 구조 관리"},
        {"name": "설정", "description": "환율 등 시스템 설정"},
        {"name": "LDAP", "description": "사내 AD/LDAP 연동"},
    ],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(dashboard.router)
app.include_router(assets.router)
app.include_router(software.router)
app.include_router(ldap.router)
app.include_router(orgs.router)
app.include_router(branding.router)


def initialize_default_admin(db: Session) -> None:
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")

    existing_admin = crud.get_user_by_username(db, admin_username)
    if existing_admin is not None:
        return

    crud.create_user(
        db=db,
        username=admin_username,
        password_hash=security.hash_password(admin_password),
        role="admin",
    )


def restore_runtime_secrets(db: Session) -> None:
    ldap_service._ensure_runtime_bind_password(db)
    mail_service.ensure_runtime_software_mail_password(db)


def _bootstrap_application_state() -> None:
    db = SessionLocal()
    try:
        initialize_default_admin(db)
        restore_runtime_secrets(db)
    finally:
        db.close()


def _start_background_jobs() -> None:
    ldap_sync_job._start_ldap_scheduler()
    software_mail_job._start_software_mail_scheduler()


def _stop_background_jobs() -> None:
    ldap_sync_job._stop_ldap_scheduler()
    software_mail_job._stop_software_mail_scheduler()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    schema_upgrade_service.run_schema_upgrade(engine)
    _bootstrap_application_state()
    _start_background_jobs()


@app.on_event("shutdown")
def on_shutdown() -> None:
    _stop_background_jobs()


@app.get("/", include_in_schema=False)
def web_index():
    return FileResponse(STATIC_DIR / "index.html")
