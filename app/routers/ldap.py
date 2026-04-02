from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, models, schemas, security
from ..database import get_db
from ..services import ldap_service, user_service

router = APIRouter()


@router.get("/directory-users", response_model=list[schemas.DirectoryUserResponse], summary="동기화 사용자 목록", tags=["LDAP"])
def list_directory_users(
    q: str | None = None,
    limit: int = 200,
    include_inactive: bool = False,
    org_unit_id: int | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return user_service.list_directory_users(
        db,
        q=q,
        limit=limit,
        include_inactive=include_inactive,
        org_unit_id=org_unit_id,
    )


@router.post("/directory-users", response_model=schemas.DirectoryUserResponse, status_code=201, summary="할당 사용자 수동 추가", tags=["LDAP"])
def create_directory_user(
    payload: schemas.DirectoryUserCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        return user_service.create_directory_user(db, payload, source="manual")
    except ValueError as e:
        if str(e) == "directory_user_exists":
            raise HTTPException(status_code=409, detail="이미 존재하는 사용자 ID입니다")
        if str(e) == "org_unit_not_found":
            raise HTTPException(status_code=400, detail="지정한 조직을 찾을 수 없습니다")
        raise HTTPException(status_code=400, detail="사용자 ID를 확인해주세요")


@router.put("/directory-users/{directory_user_id}", response_model=schemas.DirectoryUserResponse, summary="할당 사용자 수정", tags=["LDAP"])
def update_directory_user(
    directory_user_id: int,
    payload: schemas.DirectoryUserUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        row = user_service.update_directory_user(db, directory_user_id, payload)
    except ValueError as e:
        if str(e) == "empty_update":
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")
        if str(e) == "org_unit_not_found":
            raise HTTPException(status_code=400, detail="지정한 조직을 찾을 수 없습니다")
        raise HTTPException(status_code=400, detail="사용자 수정 요청을 확인해주세요")

    if not row:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    return row


@router.get(
    "/directory-users/{directory_user_id}/deactivation-preview",
    response_model=schemas.DirectoryUserDeactivationPreviewResponse,
    summary="사용자 비활성화 사전 점검",
    tags=["LDAP"],
)
def preview_directory_user_deactivation(
    directory_user_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    preview = user_service.build_directory_user_deactivation_preview(db, directory_user_id)
    if not preview:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return preview


@router.post(
    "/directory-users/{directory_user_id}/deactivate",
    response_model=schemas.DirectoryUserDeactivateResponse,
    summary="자산 해제 후 사용자 비활성화",
    tags=["LDAP"],
)
def deactivate_directory_user(
    directory_user_id: int,
    payload: schemas.DirectoryUserDeactivateRequest,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(security.get_current_admin),
):
    try:
        result = user_service.deactivate_directory_user(db, directory_user_id, payload, current_admin)
    except ValueError as e:
        message = str(e)
        if message == "assigned_assets_exist":
            raise HTTPException(
                status_code=409,
                detail="할당된 자산이 있어 비활성화할 수 없습니다. 팝업에서 자산 할당을 해제한 뒤 다시 시도해주세요.",
            )
        if message == "invalid_asset_ids":
            raise HTTPException(status_code=400, detail="할당되지 않은 자산이 포함되어 있습니다")
        if message.startswith("asset_release_failed:"):
            asset_id = message.split(":", 1)[1]
            raise HTTPException(status_code=400, detail=f"자산(ID:{asset_id}) 할당 해제에 실패했습니다")
        if message == "remaining_assets_exist":
            raise HTTPException(
                status_code=409,
                detail="아직 할당된 자산이 남아 있어 비활성화할 수 없습니다. 남은 자산을 해제해주세요.",
            )
        raise HTTPException(status_code=400, detail="사용자 비활성화 요청을 확인해주세요")

    if not result:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    return result


@router.post("/directory-users/import", response_model=schemas.DirectoryUserBulkImportResponse, summary="LDAP 검색결과 일괄 반영", tags=["LDAP"])
def import_directory_users(
    payload: schemas.DirectoryUserBulkImportRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return user_service.import_directory_users(db, payload, source="ldap")


@router.post("/ldap/test", summary="LDAP 연결 테스트", tags=["LDAP"])
def ldap_test(
    payload: schemas.LdapTestRequest,
    _: models.User = Depends(security.get_current_user),
):
    return ldap_service.ldap_test(payload)


@router.post("/ldap/search", response_model=schemas.LdapSearchResponse, summary="LDAP 사용자 검색", tags=["LDAP"])
def ldap_search(
    payload: schemas.LdapSearchRequest,
    _: models.User = Depends(security.get_current_user),
):
    return ldap_service.ldap_search(payload)


@router.post("/ldap/sync-now", response_model=schemas.LdapSyncNowResponse, summary="LDAP 사용자 즉시 동기화", tags=["LDAP"])
def ldap_sync_now(
    payload: schemas.LdapSyncNowRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return ldap_service.ldap_sync_now(payload, db)


@router.get("/ldap/sync-schedule", response_model=schemas.LdapSyncScheduleResponse, summary="LDAP 동기화 스케줄 조회", tags=["LDAP"])
def get_ldap_sync_schedule(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return ldap_service._build_sync_schedule_response(db)


@router.put("/ldap/sync-schedule", response_model=schemas.LdapSyncScheduleResponse, summary="LDAP 동기화 스케줄 저장", tags=["LDAP"])
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


