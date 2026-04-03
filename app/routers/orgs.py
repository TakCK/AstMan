from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import org_service

router = APIRouter()


@router.get("/org-units", response_model=list[schemas.OrganizationUnitResponse], summary="조직 목록 조회", tags=["조직"])
def list_org_units(
    include_inactive: bool = True,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return org_service.list_org_units(db, include_inactive=include_inactive)


@router.post("/org-units", response_model=schemas.OrganizationUnitResponse, status_code=201, summary="조직 생성", tags=["조직"])
def create_org_unit(
    payload: schemas.OrganizationUnitCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        return org_service.create_org_unit(db, payload)
    except ValueError as e:
        if str(e) == "org_unit_name_required":
            raise HTTPException(status_code=400, detail="조직명은 필수입니다")
        if str(e) == "org_unit_parent_not_found":
            raise HTTPException(status_code=400, detail="상위 조직을 찾을 수 없습니다")
        if str(e) == "org_unit_parent_inactive":
            raise HTTPException(status_code=400, detail="비활성 조직은 상위 조직으로 지정할 수 없습니다")
        if str(e) == "org_unit_conflict":
            raise HTTPException(status_code=409, detail="이미 존재하는 조직명 또는 코드입니다")
        raise HTTPException(status_code=400, detail="조직 생성 요청을 확인해주세요")


@router.get("/org-units/integrity-check", summary="조직 데이터 정합 점검", tags=["조직"])
def get_org_data_integrity_check(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return org_service.build_org_data_integrity_report(db)


@router.get(
    "/org-units/{org_unit_id}/deactivation-preview",
    response_model=schemas.OrganizationUnitDeactivationPreviewResponse,
    summary="조직 비활성화 영향도 미리보기",
    tags=["조직"],
)
def get_org_unit_deactivation_preview(
    org_unit_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    preview = org_service.build_org_unit_deactivation_preview(db, org_unit_id)
    if not preview:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다")
    return preview


@router.get(
    "/org-units/{org_unit_id}/transfer-preview",
    response_model=schemas.OrganizationUnitTransferPreviewResponse,
    summary="조직 이관 영향도 미리보기",
    tags=["조직"],
)
def get_org_unit_transfer_preview(
    org_unit_id: int,
    target_org_unit_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        preview = org_service.build_org_unit_transfer_preview(db, org_unit_id, target_org_unit_id)
    except ValueError as e:
        if str(e) == "org_unit_transfer_same_target":
            raise HTTPException(status_code=400, detail="같은 조직으로는 이관할 수 없습니다")
        if str(e) == "org_unit_transfer_target_not_found":
            raise HTTPException(status_code=400, detail="이관 대상 조직을 찾을 수 없습니다")
        if str(e) == "org_unit_transfer_target_inactive":
            raise HTTPException(status_code=400, detail="비활성 조직으로는 이관할 수 없습니다")
        raise HTTPException(status_code=400, detail="조직 이관 미리보기 요청을 확인해주세요")

    if not preview:
        raise HTTPException(status_code=404, detail="원본 조직을 찾을 수 없습니다")
    return preview


@router.post(
    "/org-units/{org_unit_id}/transfer",
    response_model=schemas.OrganizationUnitTransferResponse,
    summary="조직 이관 실행",
    tags=["조직"],
)
def transfer_org_unit(
    org_unit_id: int,
    payload: schemas.OrganizationUnitTransferRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        result = org_service.transfer_org_unit(db, org_unit_id, payload.target_org_unit_id)
    except ValueError as e:
        if str(e) == "org_unit_transfer_same_target":
            raise HTTPException(status_code=400, detail="같은 조직으로는 이관할 수 없습니다")
        if str(e) == "org_unit_transfer_target_not_found":
            raise HTTPException(status_code=400, detail="이관 대상 조직을 찾을 수 없습니다")
        if str(e) == "org_unit_transfer_target_inactive":
            raise HTTPException(status_code=400, detail="비활성 조직으로는 이관할 수 없습니다")
        raise HTTPException(status_code=400, detail="조직 이관 요청을 확인해주세요")

    if not result:
        raise HTTPException(status_code=404, detail="원본 조직을 찾을 수 없습니다")
    return result


@router.put("/org-units/{org_unit_id}", response_model=schemas.OrganizationUnitResponse, summary="조직 수정", tags=["조직"])
def update_org_unit(
    org_unit_id: int,
    payload: schemas.OrganizationUnitUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    if payload.model_dump(exclude_unset=True) == {}:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    try:
        row = org_service.update_org_unit(db, org_unit_id, payload)
    except ValueError as e:
        if str(e) == "org_unit_name_required":
            raise HTTPException(status_code=400, detail="조직명은 비워둘 수 없습니다")
        if str(e) == "org_unit_parent_invalid":
            raise HTTPException(status_code=400, detail="상위 조직은 자기 자신으로 지정할 수 없습니다")
        if str(e) == "org_unit_parent_not_found":
            raise HTTPException(status_code=400, detail="상위 조직을 찾을 수 없습니다")
        if str(e) == "org_unit_parent_inactive":
            raise HTTPException(status_code=400, detail="비활성 조직은 상위 조직으로 지정할 수 없습니다")
        if str(e) == "org_unit_parent_cycle":
            raise HTTPException(status_code=400, detail="순환 참조가 발생하는 상위 조직 설정입니다")
        if str(e) == "org_unit_conflict":
            raise HTTPException(status_code=409, detail="이미 존재하는 조직명 또는 코드입니다")
        raise HTTPException(status_code=400, detail="조직 수정 요청을 확인해주세요")

    if not row:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다")

    return row


@router.post("/org-units/{org_unit_id}/deactivate", response_model=schemas.OrganizationUnitResponse, summary="조직 비활성화", tags=["조직"])
def deactivate_org_unit(
    org_unit_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        row = org_service.deactivate_org_unit(db, org_unit_id)
    except org_service.OrgUnitDeactivationBlockedError as e:
        reasons = e.preview.blocking_reasons or []
        message = "조직 비활성화를 진행할 수 없습니다. "
        if reasons:
            message += "; ".join(reasons)
        else:
            message += "비활성화 차단 조건이 있습니다"

        raise HTTPException(
            status_code=409,
            detail={
                "message": message,
                "blocking_reasons": reasons,
                "preview": e.preview.model_dump(),
            },
        )

    if not row:
        raise HTTPException(status_code=404, detail="조직을 찾을 수 없습니다")
    return row
