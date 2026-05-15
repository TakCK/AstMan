from sqlalchemy.orm import Session

from .. import crud, models, schemas
from . import access_scope_service


def _scope_filters(access_scope: access_scope_service.UserAccessScope | None) -> tuple[set[int] | None, set[str] | None]:
    if not access_scope or access_scope.is_admin:
        return None, None
    return access_scope.subordinate_org_unit_ids, access_scope.asset_owner_values


def to_asset_response(db: Session, asset: models.Asset) -> schemas.AssetResponse:
    owner = (getattr(asset, "owner", None) or "").strip() or "미지정"
    manager_raw = (getattr(asset, "manager", None) or "").strip()
    location_raw = (getattr(asset, "location", None) or "").strip()
    name_raw = (getattr(asset, "name", None) or "").strip()
    category_raw = (getattr(asset, "category", None) or "").strip()

    org_unit_id = getattr(asset, "org_unit_id", None)
    org_unit_name = None
    if org_unit_id:
        db_org = crud.get_org_unit_by_id(db, int(org_unit_id))
        if db_org:
            org_unit_name = str(db_org.name or "").strip() or None
    if not org_unit_name:
        org_unit_name = str(getattr(asset, "department", None) or "").strip() or None

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
        "org_unit_id": org_unit_id,
        "org_unit_name": org_unit_name,
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


def create_asset(db: Session, payload: schemas.AssetCreate, actor: models.AppAccount) -> schemas.AssetResponse:
    db_asset = crud.create_asset(db, payload, actor=actor)
    return to_asset_response(db, db_asset)


def list_assets(
    db: Session,
    *,
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
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> list[schemas.AssetResponse]:
    allowed_org_unit_ids, allowed_owner_values = _scope_filters(access_scope)
    rows = crud.list_assets(
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
        allowed_org_unit_ids=allowed_org_unit_ids,
        allowed_owner_values=allowed_owner_values,
    )
    return [to_asset_response(db, row) for row in rows]


def get_asset(
    db: Session,
    asset_id: int,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> models.Asset | None:
    allowed_org_unit_ids, allowed_owner_values = _scope_filters(access_scope)
    return crud.get_asset(
        db,
        asset_id,
        allowed_org_unit_ids=allowed_org_unit_ids,
        allowed_owner_values=allowed_owner_values,
    )


def get_asset_response(
    db: Session,
    asset_id: int,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> schemas.AssetResponse | None:
    db_asset = get_asset(db, asset_id, access_scope=access_scope)
    if not db_asset:
        return None
    return to_asset_response(db, db_asset)


def update_asset(
    db: Session,
    asset_id: int,
    payload: schemas.AssetUpdate,
    actor: models.AppAccount,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> schemas.AssetResponse | None:
    db_asset = get_asset(db, asset_id, access_scope=access_scope)
    if not db_asset:
        return None
    db_asset = crud.update_asset(db, db_asset, payload, actor=actor)
    return to_asset_response(db, db_asset)


def assign_asset(
    db: Session,
    asset_id: int,
    payload: schemas.AssetAssignRequest,
    actor: models.AppAccount,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> schemas.AssetResponse | None:
    db_asset = get_asset(db, asset_id, access_scope=access_scope)
    if not db_asset:
        return None
    db_asset = crud.assign_asset(db, db_asset, actor=actor, payload=payload)
    return to_asset_response(db, db_asset)


def return_asset(
    db: Session,
    asset_id: int,
    payload: schemas.AssetReturnRequest,
    actor: models.AppAccount,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> schemas.AssetResponse | None:
    db_asset = get_asset(db, asset_id, access_scope=access_scope)
    if not db_asset:
        return None
    db_asset = crud.return_asset(db, db_asset, actor=actor, payload=payload)
    return to_asset_response(db, db_asset)


def mark_disposal_required(
    db: Session,
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    actor: models.AppAccount,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> schemas.AssetResponse | None:
    db_asset = get_asset(db, asset_id, access_scope=access_scope)
    if not db_asset:
        return None
    db_asset = crud.mark_disposal_required(db, db_asset, actor=actor, payload=payload)
    return to_asset_response(db, db_asset)


def mark_disposed(
    db: Session,
    asset_id: int,
    payload: schemas.AssetStatusChangeRequest,
    actor: models.AppAccount,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> schemas.AssetResponse | None:
    db_asset = get_asset(db, asset_id, access_scope=access_scope)
    if not db_asset:
        return None
    db_asset = crud.mark_disposed(db, db_asset, actor=actor, payload=payload)
    return to_asset_response(db, db_asset)


def delete_asset(
    db: Session,
    asset_id: int,
    actor: models.AppAccount,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> bool:
    db_asset = get_asset(db, asset_id, access_scope=access_scope)
    if not db_asset:
        return False

    if crud.normalize_status(db_asset.status) != "폐기완료":
        raise ValueError("asset_not_disposed")

    crud.delete_asset(db, db_asset, actor=actor)
    return True


def list_asset_history(
    db: Session,
    asset_id: int,
    limit: int = 100,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
):
    db_asset = get_asset(db, asset_id, access_scope=access_scope)
    if not db_asset:
        return []
    return crud.list_asset_history(db, asset_id=asset_id, limit=limit)


