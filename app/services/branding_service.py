from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import crud

BRANDING_SETTING_KEY = "branding_settings"
BRANDING_DIR_NAME = "branding"
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
BRANDING_STATIC_DIR = STATIC_DIR / BRANDING_DIR_NAME

ALLOWED_LOGO_EXTENSIONS = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg"}
ALLOWED_LOGO_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}

DEFAULT_BRANDING_SETTINGS = {
    "service_title": "AstMan ITAM",
    "service_subtitle": "하드웨어 자산과 소프트웨어 라이선스를 통합 관리하는 오픈소스 웹 애플리케이션",
    "company_logo_path": f"/static/{BRANDING_DIR_NAME}/default_logo.png",
    "footer_text": "AstMan © 2026 TakCK · MIT License",
}


def _normalize_logo_path(value: str | None) -> str:
    raw = str(value or "").strip()
    prefix = f"/static/{BRANDING_DIR_NAME}/"
    if not raw.startswith(prefix):
        return ""

    filename = raw[len(prefix) :].strip()
    if not filename or "/" in filename or "\\" in filename:
        return ""
    return f"{prefix}{filename}"


def _normalize_branding_settings(raw: dict | None) -> dict:
    payload = raw or {}
    service_title = str(payload.get("service_title") or "").strip()[:200]
    service_subtitle = str(payload.get("service_subtitle") or "").strip()[:500]
    footer_text = str(payload.get("footer_text") or "").strip()[:1000]
    company_logo_path = _normalize_logo_path(payload.get("company_logo_path")) or DEFAULT_BRANDING_SETTINGS["company_logo_path"]

    return {
        "service_title": service_title or DEFAULT_BRANDING_SETTINGS["service_title"],
        "service_subtitle": service_subtitle or DEFAULT_BRANDING_SETTINGS["service_subtitle"],
        "company_logo_path": company_logo_path,
        "footer_text": footer_text,
    }


def _logo_path_to_file(path: str | None) -> Path | None:
    normalized = _normalize_logo_path(path)
    if not normalized:
        return None
    filename = normalized.split("/")[-1]
    return BRANDING_STATIC_DIR / filename


def get_branding_settings(db: Session) -> dict:
    raw = crud.get_app_setting(db, BRANDING_SETTING_KEY, DEFAULT_BRANDING_SETTINGS)
    return _normalize_branding_settings(raw)


def set_branding_settings(db: Session, payload: dict) -> dict:
    current = get_branding_settings(db)
    merged = {
        **current,
        **(payload or {}),
    }
    normalized = _normalize_branding_settings(merged)
    crud.set_app_setting(db, BRANDING_SETTING_KEY, normalized)
    return normalized


def _validate_logo_file(upload_file: UploadFile) -> str:
    suffix = Path(str(upload_file.filename or "").strip()).suffix.lower()
    if suffix not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="로고는 PNG/JPG 파일만 업로드할 수 있습니다")

    content_type = str(upload_file.content_type or "").strip().lower()
    if content_type and content_type not in ALLOWED_LOGO_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="로고는 PNG/JPG 파일만 업로드할 수 있습니다")

    return ALLOWED_LOGO_EXTENSIONS[suffix]


async def save_branding_logo(db: Session, upload_file: UploadFile) -> dict:
    extension = _validate_logo_file(upload_file)
    raw_bytes = await upload_file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다")

    BRANDING_STATIC_DIR.mkdir(parents=True, exist_ok=True)

    current = get_branding_settings(db)
    previous_logo_file = _logo_path_to_file(current.get("company_logo_path"))

    filename = f"company_logo.{extension}"
    next_logo_file = BRANDING_STATIC_DIR / filename

    next_logo_file.write_bytes(raw_bytes)

    if previous_logo_file and previous_logo_file != next_logo_file and previous_logo_file.exists():
        previous_logo_file.unlink()

    return set_branding_settings(
        db,
        {
            **current,
            "company_logo_path": f"/static/{BRANDING_DIR_NAME}/{filename}",
        },
    )
