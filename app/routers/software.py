from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import crud, models, schemas, security
from ..database import get_db
from ..services import csv_import_service, mail_service

router = APIRouter()

SOFTWARE_LICENSE_KEY_SETTING_PREFIX = "software_license_key"


def _software_license_key_setting_key(license_id: int) -> str:
    return f"{SOFTWARE_LICENSE_KEY_SETTING_PREFIX}:{license_id}"


def _get_software_license_or_404(db: Session, license_id: int):
    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")
    return db_row


def _build_software_license_key_response(db: Session, license_id: int) -> dict:
    key = _software_license_key_setting_key(license_id)
    payload = crud.get_app_setting(db, key, {})
    license_key = str(payload.get("license_key") or "")
    return {
        "license_id": license_id,
        "license_key": license_key,
        "has_license_key": bool(license_key.strip()),
    }


@router.get("/settings/exchange-rate", response_model=schemas.ExchangeRateSettingResponse, summary="USD->KRW 환율 조회", tags=["설정"])
def get_exchange_rate_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return crud.get_exchange_rate_setting(db)


@router.put("/settings/exchange-rate", response_model=schemas.ExchangeRateSettingResponse, summary="USD->KRW 환율 저장", tags=["설정"])
def set_exchange_rate_setting(
    payload: schemas.ExchangeRateSettingUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return crud.set_exchange_rate_setting(db, payload.usd_krw, payload.effective_date)


@router.get("/settings/mail/smtp", response_model=schemas.MailSmtpConfigResponse, summary="메일 SMTP 설정 조회", tags=["설정"])
def get_mail_smtp_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.get_mail_smtp_setting(db, _)


@router.put("/settings/mail/smtp", response_model=schemas.MailSmtpConfigResponse, summary="메일 SMTP 설정 저장", tags=["설정"])
def set_mail_smtp_setting(
    payload: schemas.MailSmtpConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.set_mail_smtp_setting(payload, db, _)


@router.get("/settings/mail/admin", response_model=schemas.MailAdminConfigResponse, summary="관리자 메일 설정 조회", tags=["설정"])
def get_mail_admin_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.get_mail_admin_setting(db, _)


@router.put("/settings/mail/admin", response_model=schemas.MailAdminConfigResponse, summary="관리자 메일 설정 저장", tags=["설정"])
def set_mail_admin_setting(
    payload: schemas.MailAdminConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.set_mail_admin_setting(payload, db, _)


@router.get("/settings/mail/user", response_model=schemas.MailUserConfigResponse, summary="사용자 메일 설정 조회", tags=["설정"])
def get_mail_user_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.get_mail_user_setting(db, _)


@router.put("/settings/mail/user", response_model=schemas.MailUserConfigResponse, summary="사용자 메일 설정 저장", tags=["설정"])
def set_mail_user_setting(
    payload: schemas.MailUserConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.set_mail_user_setting(payload, db, _)


@router.post("/settings/mail/user/preview-targets", response_model=schemas.MailUserPreviewResponse, summary="사용자 메일 대상자 미리보기", tags=["설정"])
def preview_mail_user_targets(
    payload: schemas.MailUserConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.preview_mail_user_targets(payload, db, _)


@router.post("/settings/mail/admin/send-now", response_model=schemas.MailSendNowResponse, summary="관리자 메일 즉시 발송", tags=["설정"])
def send_admin_mail_now(
    payload: schemas.MailSendNowRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.send_admin_mail_now(payload, db, _)


@router.post("/settings/mail/user/send-now", response_model=schemas.MailSendNowResponse, summary="사용자 메일 즉시 발송", tags=["설정"])
def send_user_mail_now(
    payload: schemas.MailSendNowRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.send_user_mail_now(payload, db, _)


@router.get("/settings/software-expiry-mail", response_model=schemas.SoftwareExpiryMailConfigResponse, summary="소프트웨어 만료 메일 설정 조회", tags=["설정"])
def get_software_expiry_mail_setting(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.get_software_expiry_mail_setting(db, _)


@router.put("/settings/software-expiry-mail", response_model=schemas.SoftwareExpiryMailConfigResponse, summary="소프트웨어 만료 메일 설정 저장", tags=["설정"])
def set_software_expiry_mail_setting(
    payload: schemas.SoftwareExpiryMailConfigUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.set_software_expiry_mail_setting(payload, db, _)


@router.post("/settings/software-expiry-mail/send-now", response_model=schemas.SoftwareExpiryMailSendNowResponse, summary="소프트웨어 만료 메일 즉시 발송", tags=["설정"])
def send_software_expiry_mail_now(
    payload: schemas.SoftwareExpiryMailSendNowRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return mail_service.send_software_expiry_mail_now(payload, db, _)


@router.post("/imports/software-csv", response_model=schemas.CsvHwSwImportResponse, summary="소프트웨어 CSV 업로드", tags=["소프트웨어"])
async def import_software_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    return await csv_import_service.import_csv_upload(file, db, current_user, forced_kind="sw")


@router.post("/software-licenses", response_model=schemas.SoftwareLicenseResponse, status_code=201, summary="소프트웨어 라이선스 등록", tags=["소프트웨어"])
def create_software_license(
    payload: schemas.SoftwareLicenseCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    try:
        return crud.create_software_license(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/software-licenses", response_model=list[schemas.SoftwareLicenseResponse], summary="소프트웨어 라이선스 목록", tags=["소프트웨어"])
def list_software_licenses(
    skip: int = 0,
    limit: int = 200,
    q: str | None = None,
    expiring_days: int | None = None,
    expired_only: bool = False,
    license_scope: str | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    safe_limit = max(1, min(limit, 5000))
    rows = crud.list_software_licenses(
        db,
        skip=max(0, skip),
        limit=safe_limit,
        q=q,
        expiring_days=expiring_days,
        expired_only=expired_only,
    )

    scope_raw = str(license_scope or "").strip()
    if scope_raw and scope_raw.lower() not in {"all", "전체"}:
        scope = crud.normalize_license_scope(scope_raw)
        rows = [row for row in rows if crud.normalize_license_scope(getattr(row, "license_scope", None)) == scope]

    return rows


@router.get("/software-licenses/{license_id}/license-key", response_model=schemas.SoftwareLicenseKeyResponse, summary="소프트웨어 라이선스 키 조회", tags=["소프트웨어"])
def get_software_license_key(
    license_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    _get_software_license_or_404(db, license_id)
    return _build_software_license_key_response(db, license_id)


@router.put("/software-licenses/{license_id}/license-key", response_model=schemas.SoftwareLicenseKeyResponse, summary="소프트웨어 라이선스 키 저장", tags=["소프트웨어"])
def set_software_license_key(
    license_id: int,
    payload: schemas.SoftwareLicenseKeyUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    _get_software_license_or_404(db, license_id)
    key = _software_license_key_setting_key(license_id)
    license_key = str(payload.license_key or "")
    crud.set_app_setting(db, key, {"license_key": license_key})
    return _build_software_license_key_response(db, license_id)


@router.get("/software-licenses/{license_id}", response_model=schemas.SoftwareLicenseResponse, summary="소프트웨어 라이선스 상세", tags=["소프트웨어"])
def get_software_license(
    license_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")
    return db_row


@router.put("/software-licenses/{license_id}", response_model=schemas.SoftwareLicenseResponse, summary="소프트웨어 라이선스 수정", tags=["소프트웨어"])
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


@router.delete("/software-licenses/{license_id}", status_code=204, summary="소프트웨어 라이선스 삭제", tags=["소프트웨어"])
def delete_software_license(
    license_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")

    crud.delete_software_license(db, db_row)
