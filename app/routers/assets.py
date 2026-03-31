from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from .. import legacy_main as legacy, models, schemas, security
from ..database import get_db

router = APIRouter()


@router.post("/imports/hw-sw-csv", response_model=schemas.CsvHwSwImportResponse, summary="HW/SW CSV 통합 업로드", tags=["자산"])
async def import_hw_sw_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    return await legacy.import_hw_sw_csv(file, db, current_user)


@router.post("/imports/hardware-csv", response_model=schemas.CsvHwSwImportResponse, summary="하드웨어 CSV 업로드", tags=["자산"])
async def import_hardware_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_admin),
):
    return await legacy.import_hardware_csv(file, db, current_user)


@router.post("/assets", response_model=schemas.AssetResponse, status_code=201, summary="자산 등록", tags=["자산"])
def create_asset(
    asset: schemas.AssetCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    return legacy.create_asset(asset, db, current_user)


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
    return legacy.list_assets(
        skip,
        limit,
        status,
        usage_type,
        category,
        department,
        q,
        exclude_disposed,
        warranty_expiring_days,
        warranty_overdue,
        rental_expiring_days,
        db,
        _,
    )


@router.get("/assets/{asset_id}", response_model=schemas.AssetResponse, summary="자산 상세 조회", tags=["자산"])
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return legacy.get_asset(asset_id, db, _)


@router.get("/assets/{asset_id}/history", response_model=list[schemas.AssetHistoryResponse], summary="자산 이력 조회", tags=["자산"])
def get_asset_history(
    asset_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return legacy.get_asset_history(asset_id, limit, db, _)


@router.put("/assets/{asset_id}", response_model=schemas.AssetResponse, summary="자산 정보 수정", tags=["자산"])
def update_asset(
    asset_id: int,
    payload: schemas.AssetUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    return legacy.update_asset(asset_id, payload, db, current_user)


@router.post("/assets/{asset_id}/assign", response_model=schemas.AssetResponse, summary="자산 할당", tags=["자산"])
def assign_asset(
    asset_id: int,
    payload: schemas.AssetAssignRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    return legacy.assign_asset(asset_id, payload, db, current_user)


@router.post("/assets/{asset_id}/return", response_model=schemas.AssetResponse, summary="자산 반납", tags=["자산"])
def return_asset(
    asset_id: int,
    payload: schemas.AssetReturnRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    return legacy.return_asset(asset_id, payload, db, current_user)


@router.post("/assets/{asset_id}/mark-disposal-required", response_model=schemas.AssetResponse, summary="폐기필요 처리", tags=["자산"])
def mark_disposal_required(
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    return legacy.mark_disposal_required(asset_id, payload, db, current_user)


@router.post("/assets/{asset_id}/mark-disposed", response_model=schemas.AssetResponse, summary="폐기완료 처리", tags=["자산"])
def mark_disposed(
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    return legacy.mark_disposed(asset_id, payload, db, current_user)


@router.delete("/assets/{asset_id}", status_code=204, summary="자산 삭제", tags=["자산"])
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    return legacy.delete_asset(asset_id, db, current_user)
