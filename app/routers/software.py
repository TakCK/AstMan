from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import access_scope_service, csv_import_service, mail_service, software_service

router = APIRouter()


def _scope(db: Session, current_user: models.AppAccount) -> access_scope_service.UserAccessScope:
    return access_scope_service.build_user_access_scope(db, current_user)


@router.get("/settings/exchange-rate", response_model=schemas.ExchangeRateSettingResponse, summary="USD->KRW 환율 조회", tags=["설정"])
def get_exchange_rate_setting(
    db: Session = Depends(get_db),
    _: models.AppAccount = Depends(security.get_current_user),
):
    return software_service.get_exchange_rate_setting(db)


@router.put("/settings/exchange-rate", response_model=schemas.ExchangeRateSettingResponse, summary="USD->KRW 환율 저장", tags=["설정"])
def set_exchange_rate_setting(
    payload: schemas.ExchangeRateSettingUpdate,
    db: Session = Depends(get_db),
    _: models.AppAccount = Depends(security.get_current_admin),
):
    return software_service.set_exchange_rate_setting(db, payload)


@router.get("/settings/mail/smtp", response_model=schemas.MailSmtpConfigResponse, summary="메일 SMTP 설정 조회", tags=["설정"])
def get_mail_smtp_setting(
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.get_mail_smtp_setting(db, current_admin)


@router.put("/settings/mail/smtp", response_model=schemas.MailSmtpConfigResponse, summary="메일 SMTP 설정 저장", tags=["설정"])
def set_mail_smtp_setting(
    payload: schemas.MailSmtpConfigUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.set_mail_smtp_setting(payload, db, current_admin)


@router.get("/settings/mail/admin", response_model=schemas.MailAdminConfigResponse, summary="관리자 메일 설정 조회", tags=["설정"])
def get_mail_admin_setting(
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.get_mail_admin_setting(db, current_admin)


@router.put("/settings/mail/admin", response_model=schemas.MailAdminConfigResponse, summary="관리자 메일 설정 저장", tags=["설정"])
def set_mail_admin_setting(
    payload: schemas.MailAdminConfigUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.set_mail_admin_setting(payload, db, current_admin)


@router.get("/settings/mail/user", response_model=schemas.MailUserConfigResponse, summary="사용자 메일 설정 조회", tags=["설정"])
def get_mail_user_setting(
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.get_mail_user_setting(db, current_admin)


@router.put("/settings/mail/user", response_model=schemas.MailUserConfigResponse, summary="사용자 메일 설정 저장", tags=["설정"])
def set_mail_user_setting(
    payload: schemas.MailUserConfigUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.set_mail_user_setting(payload, db, current_admin)


@router.post("/settings/mail/user/preview-targets", response_model=schemas.MailUserPreviewResponse, summary="사용자 메일 대상자 미리보기", tags=["설정"])
def preview_mail_user_targets(
    payload: schemas.MailUserConfigUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.preview_mail_user_targets(payload, db, current_admin)


@router.post("/settings/mail/admin/send-now", response_model=schemas.MailSendNowResponse, summary="관리자 메일 즉시 발송", tags=["설정"])
def send_admin_mail_now(
    payload: schemas.MailSendNowRequest,
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.send_admin_mail_now(payload, db, current_admin)


@router.post("/settings/mail/user/send-now", response_model=schemas.MailSendNowResponse, summary="사용자 메일 즉시 발송", tags=["설정"])
def send_user_mail_now(
    payload: schemas.MailSendNowRequest,
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.send_user_mail_now(payload, db, current_admin)


@router.get("/settings/software-expiry-mail", response_model=schemas.SoftwareExpiryMailConfigResponse, summary="소프트웨어 만료 메일 설정 조회", tags=["설정"])
def get_software_expiry_mail_setting(
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.get_software_expiry_mail_setting(db, current_admin)


@router.put("/settings/software-expiry-mail", response_model=schemas.SoftwareExpiryMailConfigResponse, summary="소프트웨어 만료 메일 설정 저장", tags=["설정"])
def set_software_expiry_mail_setting(
    payload: schemas.SoftwareExpiryMailConfigUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.set_software_expiry_mail_setting(payload, db, current_admin)


@router.post("/settings/software-expiry-mail/send-now", response_model=schemas.SoftwareExpiryMailSendNowResponse, summary="소프트웨어 만료 메일 즉시 발송", tags=["설정"])
def send_software_expiry_mail_now(
    payload: schemas.SoftwareExpiryMailSendNowRequest,
    db: Session = Depends(get_db),
    current_admin: models.AppAccount = Depends(security.get_current_admin),
):
    return mail_service.send_software_expiry_mail_now(payload, db, current_admin)


@router.post("/imports/software-csv", response_model=schemas.CsvHwSwImportResponse, summary="소프트웨어 CSV 업로드", tags=["소프트웨어"])
async def import_software_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.AppAccount = Depends(security.get_current_admin),
):
    return await csv_import_service.import_csv_upload(file, db, current_user, forced_kind="sw")


@router.post("/software-licenses", response_model=schemas.SoftwareLicenseResponse, status_code=201, summary="소프트웨어 라이선스 등록", tags=["소프트웨어"])
def create_software_license(
    payload: schemas.SoftwareLicenseCreate,
    db: Session = Depends(get_db),
    current_user: models.AppAccount = Depends(security.get_current_user),
):
    try:
        return software_service.create_software_license(db, payload, access_scope=_scope(db, current_user))
    except ValueError as e:
        if str(e) in {"software_write_forbidden", "team_assignment_required", "assignee_scope_forbidden"}:
            raise HTTPException(status_code=403, detail="팀장 권한 범위 밖의 라이선스 작업입니다")
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
    current_user: models.AppAccount = Depends(security.get_current_user),
):
    return software_service.list_software_licenses(
        db,
        skip=skip,
        limit=limit,
        q=q,
        expiring_days=expiring_days,
        expired_only=expired_only,
        license_scope=license_scope,
        access_scope=_scope(db, current_user),
    )


@router.get("/software-licenses/{license_id}/license-key", response_model=schemas.SoftwareLicenseKeyResponse, summary="소프트웨어 라이선스 키 조회", tags=["소프트웨어"])
def get_software_license_key(
    license_id: int,
    db: Session = Depends(get_db),
    _: models.AppAccount = Depends(security.get_current_admin),
):
    response = software_service.get_software_license_key(db, license_id)
    if not response:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")
    return response


@router.put("/software-licenses/{license_id}/license-key", response_model=schemas.SoftwareLicenseKeyResponse, summary="소프트웨어 라이선스 키 저장", tags=["소프트웨어"])
def set_software_license_key(
    license_id: int,
    payload: schemas.SoftwareLicenseKeyUpdate,
    db: Session = Depends(get_db),
    _: models.AppAccount = Depends(security.get_current_admin),
):
    response = software_service.set_software_license_key(db, license_id, payload)
    if not response:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")
    return response


@router.get("/software-licenses/{license_id}", response_model=schemas.SoftwareLicenseResponse, summary="소프트웨어 라이선스 상세", tags=["소프트웨어"])
def get_software_license(
    license_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppAccount = Depends(security.get_current_user),
):
    db_row = software_service.get_software_license(
        db,
        license_id,
        access_scope=_scope(db, current_user),
    )
    if not db_row:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")
    return db_row


@router.put("/software-licenses/{license_id}", response_model=schemas.SoftwareLicenseResponse, summary="소프트웨어 라이선스 수정", tags=["소프트웨어"])
def update_software_license(
    license_id: int,
    payload: schemas.SoftwareLicenseUpdate,
    db: Session = Depends(get_db),
    current_user: models.AppAccount = Depends(security.get_current_user),
):
    if payload.model_dump(exclude_unset=True) == {}:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    try:
        db_row = software_service.update_software_license(
            db,
            license_id,
            payload,
            access_scope=_scope(db, current_user),
        )
    except ValueError as e:
        if str(e) in {"software_write_forbidden", "software_update_forbidden", "assignee_scope_forbidden"}:
            raise HTTPException(status_code=403, detail="팀장 권한 범위 밖의 라이선스 작업입니다")
        raise HTTPException(status_code=400, detail=str(e))

    if not db_row:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")

    return db_row


@router.delete("/software-licenses/{license_id}", status_code=204, summary="소프트웨어 라이선스 삭제", tags=["소프트웨어"])
def delete_software_license(
    license_id: int,
    db: Session = Depends(get_db),
    current_user: models.AppAccount = Depends(security.get_current_admin),
):
    deleted = software_service.delete_software_license(
        db,
        license_id,
        access_scope=_scope(db, current_user),
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")


@router.get(
    "/software-licenses/{license_id}/assignment-memos",
    response_model=list[schemas.SoftwareAssignmentMemoResponse],
    summary="소프트웨어 사용자 할당 메모 목록",
    tags=["소프트웨어"],
)
def list_software_assignment_memos(
    license_id: int,
    username: str,
    db: Session = Depends(get_db),
    current_user: models.AppAccount = Depends(security.get_current_user),
):
    try:
        rows = software_service.list_assignment_memos(
            db,
            license_id,
            username,
            access_scope=_scope(db, current_user),
        )
    except ValueError as e:
        if str(e) == "assignee_scope_forbidden":
            raise HTTPException(status_code=403, detail="팀장 권한 범위 밖의 사용자입니다")
        raise HTTPException(status_code=400, detail="요청 값을 확인해주세요")

    if rows is None:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")
    return rows


@router.post(
    "/software-licenses/{license_id}/assignment-memos",
    response_model=schemas.SoftwareAssignmentMemoResponse,
    status_code=201,
    summary="소프트웨어 사용자 할당 메모 추가",
    tags=["소프트웨어"],
)
def add_software_assignment_memo(
    license_id: int,
    payload: schemas.SoftwareAssignmentMemoCreate,
    db: Session = Depends(get_db),
    current_user: models.AppAccount = Depends(security.get_current_user),
):
    try:
        row = software_service.add_assignment_memo(
            db,
            license_id,
            payload,
            current_user,
            access_scope=_scope(db, current_user),
        )
    except ValueError as e:
        if str(e) == "assignee_scope_forbidden":
            raise HTTPException(status_code=403, detail="팀장 권한 범위 밖의 사용자입니다")
        raise HTTPException(status_code=400, detail="메모 내용을 확인해주세요")

    if row is None:
        raise HTTPException(status_code=404, detail="라이선스를 찾을 수 없습니다")
    return row


