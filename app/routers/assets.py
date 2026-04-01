from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas, security
from ..database import get_db
from ..services import csv_import_service, label_service

router = APIRouter()


def _value_error_message(err: ValueError) -> str:
    if str(err) == "owner_required_for_in_use":
        return "사용중 상태로 변경하려면 사용자를 지정해야 합니다"
    if str(err) == "rental_period_invalid":
        return "대여 만료일자는 대여 시작일자보다 빠를 수 없습니다"
    if str(err) == "category_immutable":
        return "카테고리는 자산 생성 후 변경할 수 없습니다"
    return "요청 값을 확인해주세요"


def _to_asset_response(asset: models.Asset) -> schemas.AssetResponse:
    owner = (getattr(asset, "owner", None) or "").strip() or "미지정"
    manager_raw = (getattr(asset, "manager", None) or "").strip()
    location_raw = (getattr(asset, "location", None) or "").strip()
    name_raw = (getattr(asset, "name", None) or "").strip()
    category_raw = (getattr(asset, "category", None) or "").strip()

    payload = {
        "id": asset.id,
        "name": name_raw or "미지정",
        "category": category_raw or "기타",
        "usage_type": crud.normalize_usage_type(getattr(asset, "usage_type", None)),
        "manufacturer": getattr(asset, "manufacturer", None),
        "model_name": getattr(asset, "model_name", None),
        "owner": owner,
        "manager": manager_raw or owner,
        "department": getattr(asset, "department", None),
        "location": location_raw or "미지정",
        "status": crud.normalize_status(getattr(asset, "status", None)),
        "serial_number": getattr(asset, "serial_number", None),
        "asset_code": getattr(asset, "asset_code", None),
        "vendor": getattr(asset, "vendor", None),
        "purchase_date": getattr(asset, "purchase_date", None),
        "purchase_cost": getattr(asset, "purchase_cost", None),
        "warranty_expiry": getattr(asset, "warranty_expiry", None),
        "rental_start_date": getattr(asset, "rental_start_date", None),
        "rental_end_date": getattr(asset, "rental_end_date", None),
        "notes": getattr(asset, "notes", None),
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
        "disposed_at": getattr(asset, "disposed_at", None),
    }
    return schemas.AssetResponse.model_validate(payload)


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
        return _to_asset_response(crud.create_asset(db, asset, actor=current_user))
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
    q: str | None = None,
    exclude_disposed: bool = False,
    warranty_expiring_days: int | None = None,
    warranty_overdue: bool = False,
    rental_expiring_days: int | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    assets = crud.list_assets(
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
    return [_to_asset_response(asset) for asset in assets]


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
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")
    return _to_asset_response(db_asset)


@router.get("/assets/{asset_id}/history", response_model=list[schemas.AssetHistoryResponse], summary="자산 이력 조회", tags=["자산"])
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


@router.put("/assets/{asset_id}", response_model=schemas.AssetResponse, summary="자산 정보 수정", tags=["자산"])
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
        return _to_asset_response(crud.update_asset(db, db_asset, payload, actor=current_user))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="자산코드 또는 시리얼번호가 이미 존재합니다")
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=_value_error_message(e))


@router.post("/assets/{asset_id}/assign", response_model=schemas.AssetResponse, summary="자산 할당", tags=["자산"])
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
        return _to_asset_response(crud.assign_asset(db, db_asset, actor=current_user, payload=payload))
    except ValueError:
        raise HTTPException(status_code=400, detail="폐기완료 자산은 할당할 수 없습니다")


@router.post("/assets/{asset_id}/return", response_model=schemas.AssetResponse, summary="자산 반납", tags=["자산"])
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
        return _to_asset_response(crud.return_asset(db, db_asset, actor=current_user, payload=payload))
    except ValueError:
        raise HTTPException(status_code=400, detail="폐기완료 자산은 반납 처리할 수 없습니다")


@router.post("/assets/{asset_id}/mark-disposal-required", response_model=schemas.AssetResponse, summary="폐기필요 처리", tags=["자산"])
def mark_disposal_required(
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    return _to_asset_response(crud.mark_disposal_required(db, db_asset, actor=current_user, payload=payload))


@router.post("/assets/{asset_id}/mark-disposed", response_model=schemas.AssetResponse, summary="폐기완료 처리", tags=["자산"])
def mark_disposed(
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    db_asset = crud.get_asset(db, asset_id)
    if not db_asset:
        raise HTTPException(status_code=404, detail="자산을 찾을 수 없습니다")

    return _to_asset_response(crud.mark_disposed(db, db_asset, actor=current_user, payload=payload))


@router.delete("/assets/{asset_id}", status_code=204, summary="자산 삭제", tags=["자산"])
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

