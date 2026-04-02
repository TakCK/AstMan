from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import asset_service, csv_import_service, label_service

router = APIRouter()


def _value_error_message(err: ValueError) -> str:
    if str(err) == "owner_required_for_in_use":
        return "사용중 상태로 변경하려면 사용자를 지정해야 합니다"
    if str(err) == "rental_period_invalid":
        return "대여 만료일자는 대여 시작일자보다 빠를 수 없습니다"
    if str(err) == "category_immutable":
        return "카테고리는 자산 생성 후 변경할 수 없습니다"
    if str(err) == "org_unit_not_found":
        return "지정한 조직을 찾을 수 없습니다"
    if str(err) == "asset_not_disposed":
        return "폐기완료 자산만 삭제할 수 있습니다"
    return "요청 값을 확인해주세요"


@router.post("/imports/hw-sw-csv", response_model=schemas.CsvHwSwImportResponse, summary="HW/SW CSV 통합 업로드", tags=["자산"])
async def import_hw_sw_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    return await csv_import_service.import_csv_upload(file, db, current_user, forced_kind=None)


@router.post("/imports/hardware-csv", response_model=schemas.CsvHwSwImportResponse, summary="하드웨어 CSV 업로드", tags=["자산"])
async def import_hardware_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    return await csv_import_service.import_csv_upload(file, db, current_user, forced_kind="hw")


@router.post("/assets", response_model=schemas.AssetResponse, status_code=201, summary="자산 등록", tags=["자산"])
def create_asset(
    asset: schemas.AssetCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    try:
        return asset_service.create_asset(db, asset, actor=current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="자산코드 또는 시리얼번호가 이미 존재합니다")
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=_value_error_message(e))


@router.get("/assets", response_model=list[schemas.AssetResponse], summary="자산 목록 조회", tags=["자산"])
def list_assets(
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    usage_type: str | None = None,
    category: str | None = None,
    department: str | None = None,
    org_unit_id: int | None = None,
    q: str | None = None,
    exclude_disposed: bool = False,
    warranty_expiring_days: int | None = None,
    warranty_overdue: bool = False,
    rental_expiring_days: int | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return asset_service.list_assets(
        db,
        skip=skip,
        limit=limit,
        status=status,
        usage_type=usage_type,
        category=category,
        department=department,
        org_unit_id=org_unit_id,
        q=q,
        exclude_disposed=exclude_disposed,
        warranty_expiring_days=warranty_expiring_days,
        warranty_overdue=warranty_overdue,
        rental_expiring_days=rental_expiring_days,
    )


@router.post("/assets/labels/preview", response_model=schemas.AssetLabelPreviewResponse, summary="자산 스티커 미리보기 데이터(다중)", tags=["자산"])
def get_assets_label_preview(
    payload: schemas.AssetLabelPreviewRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return label_service.get_assets_label_preview(db, payload.asset_ids)


@router.get("/assets/{asset_id}/label", response_model=schemas.AssetLabelPreviewResponse, summary="자산 스티커 미리보기 데이터(단일)", tags=["자산"])
def get_asset_label_preview(
    asset_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return label_service.get_asset_label_preview(db, asset_id)


@router.get("/assets/{asset_id}", response_model=schemas.AssetResponse, summary="자산 상세 조회", tags=["자산"])
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    row = asset_service.get_asset_response(db, asset_id)
    if not row:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")
    return row


@router.get("/assets/{asset_id}/history", response_model=list[schemas.AssetHistoryResponse], summary="자산 이력 조회", tags=["자산"])
def get_asset_history(
    asset_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    history = asset_service.list_asset_history(db, asset_id=asset_id, limit=limit)
    if not history and not asset_service.get_asset(db, asset_id):
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")
    return history


@router.put("/assets/{asset_id}", response_model=schemas.AssetResponse, summary="자산 정보 수정", tags=["자산"])
def update_asset(
    asset_id: int,
    payload: schemas.AssetUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    if payload.model_dump(exclude_unset=True) == {}:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    try:
        row = asset_service.update_asset(db, asset_id, payload, actor=current_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="자산코드 또는 시리얼번호가 이미 존재합니다")
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=_value_error_message(e))

    if not row:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    return row


@router.post("/assets/{asset_id}/assign", response_model=schemas.AssetResponse, summary="자산 할당", tags=["자산"])
def assign_asset(
    asset_id: int,
    payload: schemas.AssetAssignRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    try:
        row = asset_service.assign_asset(db, asset_id, payload, actor=current_user)
    except ValueError:
        raise HTTPException(status_code=400, detail="폐기완료 자산은 할당할 수 없습니다")

    if not row:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    return row


@router.post("/assets/{asset_id}/return", response_model=schemas.AssetResponse, summary="자산 반납", tags=["자산"])
def return_asset(
    asset_id: int,
    payload: schemas.AssetReturnRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    try:
        row = asset_service.return_asset(db, asset_id, payload, actor=current_user)
    except ValueError:
        raise HTTPException(status_code=400, detail="폐기완료 자산은 반납 처리할 수 없습니다")

    if not row:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    return row


@router.post("/assets/{asset_id}/mark-disposal-required", response_model=schemas.AssetResponse, summary="폐기필요 처리", tags=["자산"])
def mark_disposal_required(
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    row = asset_service.mark_disposal_required(db, asset_id, payload, actor=current_user)
    if not row:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    return row


@router.post("/assets/{asset_id}/mark-disposed", response_model=schemas.AssetResponse, summary="폐기완료 처리", tags=["자산"])
def mark_disposed(
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    row = asset_service.mark_disposed(db, asset_id, payload, actor=current_user)
    if not row:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    return row


@router.delete("/assets/{asset_id}", status_code=204, summary="자산 삭제", tags=["자산"])
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    try:
        deleted = asset_service.delete_asset(db, asset_id, actor=current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_value_error_message(e))

    if not deleted:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")



