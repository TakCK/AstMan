from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import crud, models, schemas, security
from ..database import get_db
from ..services import ldap_service

router = APIRouter()


def _normalize_username(value: str | None) -> str:
    return str(value or "").strip()


def _build_user_identity_candidates(db_user: models.DirectoryUser) -> set[str]:
    username = _normalize_username(db_user.username)
    display_name = _normalize_username(db_user.display_name)

    candidates = {username, display_name}
    candidates.discard("")

    if username and display_name:
        candidates.update(
            {
                f"{display_name} ({username})",
                f"{username} ({display_name})",
                f"{username} | {display_name}",
                f"{display_name} | {username}",
            }
        )

    return candidates


def _collect_user_assigned_assets(db: Session, db_user: models.DirectoryUser) -> list[models.Asset]:
    owner_candidates = _build_user_identity_candidates(db_user)
    if not owner_candidates:
        return []

    owner_filters = [models.Asset.owner == candidate for candidate in owner_candidates]

    return (
        db.query(models.Asset)
        .filter(or_(*owner_filters))
        .filter(models.Asset.status != "폐기완료")
        .order_by(models.Asset.id.asc())
        .all()
    )


def _collect_user_assigned_licenses(
    db: Session,
    db_user: models.DirectoryUser,
) -> list[schemas.DirectoryUserAssignedLicense]:
    assignee_candidates = _build_user_identity_candidates(db_user)
    if not assignee_candidates:
        return []

    rows: list[schemas.DirectoryUserAssignedLicense] = []

    for license_row in (
        db.query(models.SoftwareLicense)
        .order_by(models.SoftwareLicense.product_name.asc(), models.SoftwareLicense.id.asc())
        .all()
    ):
        assignees = license_row.assignees if isinstance(license_row.assignees, list) else []
        assignment_count = 0
        for raw in assignees:
            if _normalize_username(raw) in assignee_candidates:
                assignment_count += 1

        if assignment_count <= 0:
            continue

        rows.append(
            schemas.DirectoryUserAssignedLicense(
                license_id=int(license_row.id),
                license_name=str(license_row.product_name or "(이름없음)").strip() or "(이름없음)",
                assignment_count=assignment_count,
            )
        )

    return rows


def _build_deactivation_preview(
    db: Session,
    db_user: models.DirectoryUser,
) -> schemas.DirectoryUserDeactivationPreviewResponse:
    username = _normalize_username(db_user.username)
    assets = _collect_user_assigned_assets(db, db_user)
    licenses = _collect_user_assigned_licenses(db, db_user)

    return schemas.DirectoryUserDeactivationPreviewResponse(
        directory_user_id=int(db_user.id),
        username=username,
        display_name=db_user.display_name,
        is_active=bool(db_user.is_active),
        assigned_asset_count=len(assets),
        assigned_license_count=sum(int(row.assignment_count) for row in licenses),
        assigned_assets=[
            schemas.DirectoryUserAssignedAsset(
                id=int(asset.id),
                asset_code=asset.asset_code,
                name=str(asset.name or "").strip(),
                category=str(asset.category or "").strip(),
                status=crud.normalize_status(asset.status),
            )
            for asset in assets
        ],
        assigned_licenses=licenses,
    )


@router.get("/directory-users", response_model=list[schemas.DirectoryUserResponse], summary="동기화 사용자 목록", tags=["LDAP"])
def list_directory_users(
    q: str | None = None,
    limit: int = 200,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    safe_limit = max(1, min(limit, 5000))
    return crud.list_directory_users(db, q=q, limit=safe_limit, include_inactive=include_inactive)


@router.post("/directory-users", response_model=schemas.DirectoryUserResponse, status_code=201, summary="할당 사용자 수동 추가", tags=["LDAP"])
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


@router.put("/directory-users/{directory_user_id}", response_model=schemas.DirectoryUserResponse, summary="할당 사용자 수정", tags=["LDAP"])
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
    db_user = crud.get_directory_user_by_id(db, directory_user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    return _build_deactivation_preview(db, db_user)


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
    db_user = crud.get_directory_user_by_id(db, directory_user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    preview = _build_deactivation_preview(db, db_user)

    if not preview.is_active:
        return schemas.DirectoryUserDeactivateResponse(
            ok=True,
            message="이미 비활성 사용자입니다.",
            released_asset_count=0,
            remaining_asset_count=preview.assigned_asset_count,
            assigned_license_count=preview.assigned_license_count,
            user=db_user,
        )

    assigned_assets = _collect_user_assigned_assets(db, db_user)
    asset_map = {int(asset.id): asset for asset in assigned_assets}

    released_asset_count = 0

    if assigned_assets:
        if not payload.release_assets:
            raise HTTPException(
                status_code=409,
                detail="할당된 자산이 있어 비활성화할 수 없습니다. 팝업에서 자산 할당을 해제한 뒤 다시 시도해주세요.",
            )

        requested_ids = [int(v) for v in (payload.asset_ids or []) if int(v) > 0]
        target_ids = requested_ids if requested_ids else list(asset_map.keys())

        invalid_ids = [asset_id for asset_id in target_ids if asset_id not in asset_map]
        if invalid_ids:
            raise HTTPException(status_code=400, detail="할당되지 않은 자산이 포함되어 있습니다")

        for asset_id in target_ids:
            db_asset = asset_map.get(asset_id)
            if not db_asset:
                continue
            try:
                crud.return_asset(
                    db,
                    db_asset,
                    actor=current_admin,
                    payload=schemas.AssetReturnRequest(
                        memo=f"사용자 비활성화 처리로 자산 할당 자동 해제 ({preview.username})"
                    ),
                )
                released_asset_count += 1
            except ValueError:
                raise HTTPException(status_code=400, detail=f"자산(ID:{asset_id}) 할당 해제에 실패했습니다")

    remaining_assets = _collect_user_assigned_assets(db, db_user)
    if remaining_assets:
        raise HTTPException(
            status_code=409,
            detail="아직 할당된 자산이 남아 있어 비활성화할 수 없습니다. 남은 자산을 해제해주세요.",
        )

    updated_user = crud.update_directory_user(
        db,
        db_user,
        schemas.DirectoryUserUpdate(is_active=False),
    )

    remaining_license_rows = _collect_user_assigned_licenses(db, db_user)
    remaining_license_count = sum(int(row.assignment_count) for row in remaining_license_rows)

    return schemas.DirectoryUserDeactivateResponse(
        ok=True,
        message="사용자를 비활성화했습니다.",
        released_asset_count=released_asset_count,
        remaining_asset_count=0,
        assigned_license_count=remaining_license_count,
        user=updated_user,
    )


@router.post("/directory-users/import", response_model=schemas.DirectoryUserBulkImportResponse, summary="LDAP 검색결과 일괄 반영", tags=["LDAP"])
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




