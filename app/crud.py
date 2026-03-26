from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from . import models, schemas

STATUS_ALIAS = {
    "active": "사용중",
    "assigned": "사용중",
    "in_use": "사용중",
    "사용중": "사용중",
    "available": "대기",
    "maintenance": "대기",
    "standby": "대기",
    "대기": "대기",
    "retired": "폐기필요",
    "disposal_required": "폐기필요",
    "폐기필요": "폐기필요",
    "disposed": "폐기완료",
    "disposal_done": "폐기완료",
    "폐기완료": "폐기완료",
}

USAGE_TYPE_ALIAS = {
    "주장비": "주장비",
    "primary": "주장비",
    "대여장비": "대여장비",
    "loaner": "대여장비",
    "프로젝트장비": "프로젝트장비",
    "project": "프로젝트장비",
    "보조장비": "보조장비",
    "auxiliary": "보조장비",
    "기타장비": "기타장비",
    "other": "기타장비",
    "서버장비": "서버장비",
    "server": "서버장비",
    "네트워크장비": "네트워크장비",
    "network": "네트워크장비",
}

DEFAULT_STATUS = "대기"
DEFAULT_USAGE_TYPE = "기타장비"
NON_IN_USE_STATUSES = {"대기", "폐기필요", "폐기완료"}


def normalize_status(status: str | None) -> str:
    if not status:
        return DEFAULT_STATUS
    return STATUS_ALIAS.get(status, DEFAULT_STATUS)


def normalize_usage_type(usage_type: str | None) -> str:
    if not usage_type:
        return DEFAULT_USAGE_TYPE
    return USAGE_TYPE_ALIAS.get(usage_type, DEFAULT_USAGE_TYPE)


def _to_json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalize_manager(owner: str, manager: str | None) -> str:
    if manager and manager.strip():
        return manager.strip()
    return owner.strip() if owner and owner.strip() else "미지정"


def _resolve_department_from_owner(db: Session, owner: str | None, fallback: str | None = None) -> str | None:
    owner_key = (owner or "").strip()
    if not owner_key or owner_key == "미지정":
        return None

    directory_user = get_directory_user_by_username(db, owner_key)
    if directory_user and directory_user.department:
        resolved = directory_user.department.strip()
        if resolved:
            return resolved

    fallback_text = (fallback or "").strip()
    return fallback_text or None


def _normalize_assignees(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        key = str(value or "").strip()
        if not key or key in result:
            continue
        result.append(key)
    return result


def _normalize_rental_period(
    usage_type: str,
    rental_start_date: date | None,
    rental_end_date: date | None,
) -> tuple[date | None, date | None]:
    if usage_type != "대여장비":
        return None, None

    if rental_start_date and rental_end_date and rental_end_date < rental_start_date:
        raise ValueError("rental_period_invalid")

    return rental_start_date, rental_end_date


def _enforce_status_owner_rules(target_status: str, candidate_owner: str | None) -> str:
    if target_status in NON_IN_USE_STATUSES:
        return "미지정"

    owner = (candidate_owner or "").strip()
    if target_status == "사용중" and (not owner or owner == "미지정"):
        raise ValueError("owner_required_for_in_use")

    return owner if owner else "미지정"


def get_user_by_username(db: Session, username: str) -> models.User | None:
    return db.query(models.User).filter(models.User.username == username).first()


def create_user(
    db: Session,
    username: str,
    password_hash: str,
    role: str = "user",
    is_active: bool = True,
) -> models.User:
    db_user = models.User(
        username=username,
        password_hash=password_hash,
        role=role,
        is_active=is_active,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user



def list_users(
    db: Session,
    role: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[models.User]:
    query = db.query(models.User)

    if role:
        query = query.filter(models.User.role == role)

    if q:
        keyword = f"%{q}%"
        query = query.filter(models.User.username.ilike(keyword))

    return query.order_by(models.User.username.asc()).limit(limit).all()


def update_user_admin(
    db: Session,
    db_user: models.User,
    *,
    is_active: bool | None = None,
    password_hash: str | None = None,
    role: str | None = None,
) -> models.User:
    if is_active is not None:
        db_user.is_active = bool(is_active)
    if password_hash:
        db_user.password_hash = password_hash
    if role:
        db_user.role = role

    db.commit()
    db.refresh(db_user)
    return db_user


def get_app_setting(db: Session, key: str, default: dict | None = None) -> dict:
    row = db.query(models.AppSetting).filter(models.AppSetting.key == key).first()
    if not row or not isinstance(row.value, dict):
        return default.copy() if isinstance(default, dict) else {}
    return dict(row.value)


def set_app_setting(db: Session, key: str, value: dict) -> dict:
    row = db.query(models.AppSetting).filter(models.AppSetting.key == key).first()
    payload = dict(value or {})

    if row:
        row.value = payload
    else:
        row = models.AppSetting(key=key, value=payload)
        db.add(row)

    db.commit()
    db.refresh(row)
    return dict(row.value or {})


def list_directory_users(
    db: Session,
    q: str | None = None,
    limit: int = 200,
    include_inactive: bool = False,
) -> list[models.DirectoryUser]:
    query = db.query(models.DirectoryUser)

    if not include_inactive:
        query = query.filter(models.DirectoryUser.is_active.is_(True))

    if q:
        keyword = f"%{q}%"
        query = query.filter(
            or_(
                models.DirectoryUser.username.ilike(keyword),
                models.DirectoryUser.display_name.ilike(keyword),
                models.DirectoryUser.email.ilike(keyword),
            )
        )

    return query.order_by(models.DirectoryUser.username.asc()).limit(limit).all()


def get_directory_user_by_id(db: Session, directory_user_id: int) -> models.DirectoryUser | None:
    return db.query(models.DirectoryUser).filter(models.DirectoryUser.id == directory_user_id).first()


def get_directory_user_by_username(db: Session, username: str) -> models.DirectoryUser | None:
    return db.query(models.DirectoryUser).filter(models.DirectoryUser.username == username).first()


def create_directory_user(
    db: Session,
    payload: schemas.DirectoryUserCreate,
    source: str = "manual",
) -> models.DirectoryUser:
    username = payload.username.strip()
    if not username:
        raise ValueError("directory_user_username_required")

    if get_directory_user_by_username(db, username):
        raise ValueError("directory_user_exists")

    row = models.DirectoryUser(
        username=username,
        display_name=(payload.display_name or "").strip() or None,
        email=(payload.email or "").strip() or None,
        department=(payload.department or "").strip() or None,
        title=(payload.title or "").strip() or None,
        is_active=True,
        source=source,
        synced_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_directory_user(
    db: Session,
    db_user: models.DirectoryUser,
    payload: schemas.DirectoryUserUpdate,
) -> models.DirectoryUser:
    updates = payload.model_dump(exclude_unset=True)

    if "display_name" in updates:
        db_user.display_name = (updates.get("display_name") or "").strip() or None
    if "email" in updates:
        db_user.email = (updates.get("email") or "").strip() or None
    if "department" in updates:
        db_user.department = (updates.get("department") or "").strip() or None
    if "title" in updates:
        db_user.title = (updates.get("title") or "").strip() or None
    if "is_active" in updates:
        db_user.is_active = bool(updates.get("is_active"))

    db_user.synced_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(db_user)
    return db_user


def upsert_directory_users(
    db: Session,
    users: list[dict],
    *,
    source: str = "ldap",
    deactivate_missing: bool = False,
    keep_inactive: bool = False,
) -> dict:
    incoming = {}
    for item in users:
        username = str(item.get("username") or "").strip()
        if not username:
            continue
        incoming[username] = {
            "username": username,
            "display_name": (item.get("display_name") or "").strip() or None,
            "email": (item.get("email") or "").strip() or None,
            "department": (item.get("department") or "").strip() or None,
            "title": (item.get("title") or "").strip() or None,
        }

    now = datetime.now(timezone.utc)

    existing_rows = db.query(models.DirectoryUser).all()
    existing_map = {row.username: row for row in existing_rows}

    created = 0
    updated = 0
    reactivated = 0

    for username, payload in incoming.items():
        row = existing_map.get(username)
        if row is None:
            row = models.DirectoryUser(
                username=username,
                display_name=payload["display_name"],
                email=payload["email"],
                department=payload["department"],
                title=payload["title"],
                is_active=True,
                source=source,
                synced_at=now,
            )
            db.add(row)
            created += 1
            continue

        changed = False
        for field in ["display_name", "email", "department", "title"]:
            new_value = payload[field]
            if getattr(row, field) != new_value:
                setattr(row, field, new_value)
                changed = True

        if row.source != source and row.source != "manual":
            row.source = source
            changed = True

        if not row.is_active and not keep_inactive:
            row.is_active = True
            reactivated += 1
            changed = True

        row.synced_at = now
        if changed:
            updated += 1

    deactivated = 0
    if deactivate_missing:
        incoming_keys = set(incoming.keys())
        for row in existing_rows:
            if row.source != source:
                continue
            if row.username in incoming_keys:
                continue
            if row.is_active:
                row.is_active = False
                row.synced_at = now
                deactivated += 1

    db.commit()

    return {
        "total_incoming": len(incoming),
        "created": created,
        "updated": updated,
        "reactivated": reactivated,
        "deactivated": deactivated,
    }

def _asset_snapshot(asset: models.Asset) -> dict:
    return {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "name": asset.name,
        "category": asset.category,
        "usage_type": asset.usage_type,
        "manufacturer": asset.manufacturer,
        "model_name": asset.model_name,
        "owner": asset.owner,
        "manager": asset.manager,
        "department": asset.department,
        "location": asset.location,
        "status": normalize_status(asset.status),
        "disposed_at": _to_json_value(asset.disposed_at),
        "serial_number": asset.serial_number,
        "vendor": asset.vendor,
        "purchase_date": _to_json_value(asset.purchase_date),
        "purchase_cost": _to_json_value(asset.purchase_cost),
        "warranty_expiry": _to_json_value(asset.warranty_expiry),
        "rental_start_date": _to_json_value(asset.rental_start_date),
        "rental_end_date": _to_json_value(asset.rental_end_date),
        "notes": asset.notes,
    }


def _log_asset_history(
    db: Session,
    asset_id: int,
    action: str,
    actor: models.User,
    changed_fields: dict | None,
):
    db.add(
        models.AssetHistory(
            asset_id=asset_id,
            action=action,
            actor_user_id=actor.id,
            actor_username=actor.username,
            changed_fields=changed_fields,
        )
    )


def create_asset(db: Session, asset: schemas.AssetCreate, actor: models.User) -> models.Asset:
    payload = asset.model_dump()
    payload["status"] = normalize_status(payload.get("status"))
    payload["usage_type"] = normalize_usage_type(payload.get("usage_type"))

    payload_owner = _enforce_status_owner_rules(payload["status"], payload.get("owner"))
    payload["owner"] = payload_owner
    payload["manager"] = _normalize_manager(payload_owner, payload.get("manager"))
    payload["department"] = _resolve_department_from_owner(db, payload_owner, payload.get("department"))
    payload["disposed_at"] = datetime.now(timezone.utc) if payload["status"] == "폐기완료" else None

    rental_start_date, rental_end_date = _normalize_rental_period(
        payload["usage_type"],
        payload.get("rental_start_date"),
        payload.get("rental_end_date"),
    )
    payload["rental_start_date"] = rental_start_date
    payload["rental_end_date"] = rental_end_date

    db_asset = models.Asset(**payload)
    db.add(db_asset)
    db.flush()

    if not db_asset.asset_code:
        db_asset.asset_code = f"AST-{db_asset.id:05d}"

    _log_asset_history(
        db,
        asset_id=db_asset.id,
        action="created",
        actor=actor,
        changed_fields={"after": _asset_snapshot(db_asset)},
    )

    db.commit()
    db.refresh(db_asset)
    return db_asset


def list_assets(
    db: Session,
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
):
    query = db.query(models.Asset)

    if status:
        normalized = normalize_status(status)
        query = query.filter(or_(models.Asset.status == normalized, models.Asset.status == status))

    if usage_type:
        query = query.filter(models.Asset.usage_type == normalize_usage_type(usage_type))

    if category:
        query = query.filter(models.Asset.category.ilike(f"%{category}%"))

    if department:
        query = query.filter(models.Asset.department.ilike(f"%{department}%"))

    if exclude_disposed:
        query = query.filter(models.Asset.status != "폐기완료")

    if q:
        keyword = f"%{q}%"
        query = query.filter(
            or_(
                models.Asset.asset_code.ilike(keyword),
                models.Asset.name.ilike(keyword),
                models.Asset.serial_number.ilike(keyword),
                models.Asset.owner.ilike(keyword),
                models.Asset.manager.ilike(keyword),
                models.Asset.location.ilike(keyword),
                models.Asset.department.ilike(keyword),
            )
        )

    today = date.today()

    if warranty_expiring_days and warranty_expiring_days > 0:
        warranty_until = today + timedelta(days=warranty_expiring_days)
        query = query.filter(models.Asset.warranty_expiry.is_not(None))
        query = query.filter(models.Asset.warranty_expiry >= today)
        query = query.filter(models.Asset.warranty_expiry <= warranty_until)

    if warranty_overdue:
        query = query.filter(models.Asset.warranty_expiry.is_not(None))
        query = query.filter(models.Asset.warranty_expiry < today)

    if rental_expiring_days and rental_expiring_days > 0:
        rental_until = today + timedelta(days=rental_expiring_days)
        query = query.filter(models.Asset.usage_type == "대여장비")
        query = query.filter(models.Asset.rental_end_date.is_not(None))
        query = query.filter(models.Asset.rental_end_date >= today)
        query = query.filter(models.Asset.rental_end_date <= rental_until)

    return query.order_by(models.Asset.id.desc()).offset(skip).limit(limit).all()


def get_asset(db: Session, asset_id: int):
    return db.query(models.Asset).filter(models.Asset.id == asset_id).first()


def update_asset(
    db: Session,
    db_asset: models.Asset,
    payload: schemas.AssetUpdate,
    actor: models.User,
):
    updates = payload.model_dump(exclude_unset=True)

    if "category" in updates:
        requested_category = str(updates.get("category") or "").strip()
        current_category = str(db_asset.category or "").strip()
        if requested_category and requested_category != current_category:
            raise ValueError("category_immutable")

    if "usage_type" in updates:
        updates["usage_type"] = normalize_usage_type(updates.get("usage_type"))

    target_usage_type = updates.get("usage_type", db_asset.usage_type)
    rental_start_requested = updates.get("rental_start_date", db_asset.rental_start_date)
    rental_end_requested = updates.get("rental_end_date", db_asset.rental_end_date)
    rental_start_date, rental_end_date = _normalize_rental_period(
        target_usage_type,
        rental_start_requested,
        rental_end_requested,
    )
    updates["rental_start_date"] = rental_start_date
    updates["rental_end_date"] = rental_end_date

    status_requested = "status" in updates
    target_status = normalize_status(updates["status"]) if status_requested else db_asset.status
    updates["status"] = target_status

    if status_requested:
        current_status = normalize_status(db_asset.status)
        if target_status == "폐기완료" and current_status != "폐기완료":
            updates["disposed_at"] = datetime.now(timezone.utc)
        elif target_status != "폐기완료" and current_status == "폐기완료":
            updates["disposed_at"] = None

    current_owner = updates.get("owner", db_asset.owner)
    resolved_owner = _enforce_status_owner_rules(target_status, current_owner)
    updates["owner"] = resolved_owner

    manager_source = updates.get("manager", db_asset.manager)
    updates["manager"] = _normalize_manager(resolved_owner, manager_source)
    department_source = updates.get("department", db_asset.department)
    updates["department"] = _resolve_department_from_owner(db, resolved_owner, department_source)

    changes = {}

    for field, value in updates.items():
        old_value = getattr(db_asset, field)
        if old_value != value:
            changes[field] = {
                "before": _to_json_value(old_value),
                "after": _to_json_value(value),
            }
            setattr(db_asset, field, value)

    if changes:
        _log_asset_history(
            db,
            asset_id=db_asset.id,
            action="updated",
            actor=actor,
            changed_fields=changes,
        )

        db.commit()
        db.refresh(db_asset)

    return db_asset


def _apply_state_change(
    db: Session,
    db_asset: models.Asset,
    actor: models.User,
    action: str,
    updates: dict,
    memo: str | None,
):
    changes = {}
    for field, value in updates.items():
        old_value = getattr(db_asset, field)
        if old_value != value:
            changes[field] = {
                "before": _to_json_value(old_value),
                "after": _to_json_value(value),
            }
            setattr(db_asset, field, value)

    payload = {"changes": changes} if changes else {}
    if memo:
        payload["memo"] = memo

    _log_asset_history(
        db,
        asset_id=db_asset.id,
        action=action,
        actor=actor,
        changed_fields=payload or None,
    )

    db.commit()
    db.refresh(db_asset)
    return db_asset


def assign_asset(
    db: Session,
    db_asset: models.Asset,
    actor: models.User,
    payload: schemas.AssetAssignRequest,
):
    current_status = normalize_status(db_asset.status)
    if current_status == "폐기완료":
        raise ValueError("disposed")

    updates = {
        "status": "사용중",
        "owner": payload.assignee,
        "department": _resolve_department_from_owner(db, payload.assignee, payload.department),
        "disposed_at": None,
    }
    if payload.location is not None:
        updates["location"] = payload.location

    return _apply_state_change(
        db,
        db_asset,
        actor,
        action="assigned",
        updates=updates,
        memo=payload.memo,
    )


def return_asset(
    db: Session,
    db_asset: models.Asset,
    actor: models.User,
    payload: schemas.AssetReturnRequest,
):
    current_status = normalize_status(db_asset.status)
    if current_status == "폐기완료":
        raise ValueError("disposed")

    updates = {
        "status": "대기",
        "owner": "미지정",
        "department": None,
        "disposed_at": None,
    }
    if payload.location is not None:
        updates["location"] = payload.location

    return _apply_state_change(
        db,
        db_asset,
        actor,
        action="returned",
        updates=updates,
        memo=payload.memo,
    )


def mark_disposal_required(
    db: Session,
    db_asset: models.Asset,
    actor: models.User,
    payload: schemas.AssetStatusChangeRequest,
):
    return _apply_state_change(
        db,
        db_asset,
        actor,
        action="marked_disposal_required",
        updates={"status": "폐기필요", "owner": "미지정", "department": None, "disposed_at": None},
        memo=payload.memo,
    )


def mark_disposed(
    db: Session,
    db_asset: models.Asset,
    actor: models.User,
    payload: schemas.AssetStatusChangeRequest,
):
    return _apply_state_change(
        db,
        db_asset,
        actor,
        action="marked_disposed",
        updates={"status": "폐기완료", "owner": "미지정", "department": None, "disposed_at": datetime.now(timezone.utc)},
        memo=payload.memo,
    )


def delete_asset(db: Session, db_asset: models.Asset, actor: models.User):
    snapshot = _asset_snapshot(db_asset)

    _log_asset_history(
        db,
        asset_id=db_asset.id,
        action="deleted",
        actor=actor,
        changed_fields={"before": snapshot},
    )

    db.delete(db_asset)
    db.commit()


def list_asset_history(db: Session, asset_id: int, limit: int = 100):
    return (
        db.query(models.AssetHistory)
        .filter(models.AssetHistory.asset_id == asset_id)
        .order_by(models.AssetHistory.id.desc())
        .limit(limit)
        .all()
    )



def create_software_license(db: Session, payload: schemas.SoftwareLicenseCreate) -> models.SoftwareLicense:
    data = payload.model_dump()
    data["assignees"] = _normalize_assignees(data.get("assignees"))

    db_row = models.SoftwareLicense(**data)
    db.add(db_row)
    db.commit()
    db.refresh(db_row)
    return db_row


def list_software_licenses(
    db: Session,
    skip: int = 0,
    limit: int = 200,
    q: str | None = None,
    expiring_days: int | None = None,
    expired_only: bool = False,
):
    query = db.query(models.SoftwareLicense)

    if q:
        keyword = f"%{q}%"
        query = query.filter(
            or_(
                models.SoftwareLicense.product_name.ilike(keyword),
                models.SoftwareLicense.vendor.ilike(keyword),
                models.SoftwareLicense.drafter.ilike(keyword),
            )
        )

    today = date.today()

    if expiring_days and expiring_days > 0:
        until = today + timedelta(days=expiring_days)
        query = query.filter(models.SoftwareLicense.end_date.is_not(None))
        query = query.filter(models.SoftwareLicense.end_date >= today)
        query = query.filter(models.SoftwareLicense.end_date <= until)

    if expired_only:
        query = query.filter(models.SoftwareLicense.end_date.is_not(None))
        query = query.filter(models.SoftwareLicense.end_date < today)

    return query.order_by(models.SoftwareLicense.id.desc()).offset(skip).limit(limit).all()


def get_software_license(db: Session, license_id: int) -> models.SoftwareLicense | None:
    return db.query(models.SoftwareLicense).filter(models.SoftwareLicense.id == license_id).first()


def update_software_license(
    db: Session,
    db_row: models.SoftwareLicense,
    payload: schemas.SoftwareLicenseUpdate,
) -> models.SoftwareLicense:
    updates = payload.model_dump(exclude_unset=True)

    if "assignees" in updates:
        updates["assignees"] = _normalize_assignees(updates.get("assignees"))

    for field, value in updates.items():
        setattr(db_row, field, value)

    db.commit()
    db.refresh(db_row)
    return db_row


def delete_software_license(db: Session, db_row: models.SoftwareLicense):
    db.delete(db_row)
    db.commit()
def get_dashboard_summary(db: Session):
    status_keys = ["사용중", "대기", "폐기필요", "폐기완료"]
    usage_keys = [
        "주장비",
        "대여장비",
        "프로젝트장비",
        "보조장비",
        "기타장비",
        "서버장비",
        "네트워크장비",
    ]

    status_counts = {key: 0 for key in status_keys}
    for status, count in db.query(models.Asset.status, func.count(models.Asset.id)).group_by(models.Asset.status).all():
        normalized = normalize_status(status)
        status_counts[normalized] = status_counts.get(normalized, 0) + count

    usage_type_counts = {key: 0 for key in usage_keys}
    active_assets = db.query(models.Asset).filter(models.Asset.status != "폐기완료")
    for usage_type, count in active_assets.with_entities(models.Asset.usage_type, func.count(models.Asset.id)).group_by(models.Asset.usage_type).all():
        key = normalize_usage_type(usage_type)
        usage_type_counts[key] = usage_type_counts.get(key, 0) + count

    category_counts = {}
    for category, count in (
        active_assets.with_entities(models.Asset.category, func.count(models.Asset.id))
        .group_by(models.Asset.category)
        .order_by(func.count(models.Asset.id).desc())
        .all()
    ):
        category_counts[category] = count

    today = date.today()
    upcoming = today + timedelta(days=30)

    expiring_warranty_30d = (
        db.query(func.count(models.Asset.id))
        .filter(models.Asset.status != "폐기완료")
        .filter(models.Asset.warranty_expiry.is_not(None))
        .filter(models.Asset.warranty_expiry >= today)
        .filter(models.Asset.warranty_expiry <= upcoming)
        .scalar()
        or 0
    )

    overdue_warranty = (
        db.query(func.count(models.Asset.id))
        .filter(models.Asset.status != "폐기완료")
        .filter(models.Asset.warranty_expiry.is_not(None))
        .filter(models.Asset.warranty_expiry < today)
        .scalar()
        or 0
    )

    rental_expiring_7d = (
        db.query(func.count(models.Asset.id))
        .filter(models.Asset.usage_type == "대여장비")
        .filter(models.Asset.status != "폐기완료")
        .filter(models.Asset.rental_end_date.is_not(None))
        .filter(models.Asset.rental_end_date >= today)
        .filter(models.Asset.rental_end_date <= today + timedelta(days=7))
        .scalar()
        or 0
    )

    software_total = db.query(func.count(models.SoftwareLicense.id)).scalar() or 0

    software_expiring_30d = (
        db.query(func.count(models.SoftwareLicense.id))
        .filter(models.SoftwareLicense.end_date.is_not(None))
        .filter(models.SoftwareLicense.end_date >= today)
        .filter(models.SoftwareLicense.end_date <= upcoming)
        .scalar()
        or 0
    )

    software_expired = (
        db.query(func.count(models.SoftwareLicense.id))
        .filter(models.SoftwareLicense.end_date.is_not(None))
        .filter(models.SoftwareLicense.end_date < today)
        .scalar()
        or 0
    )

    hardware_total = sum(status_counts[key] for key in status_keys if key != "폐기완료")

    return {
        "total_assets": hardware_total + software_total,
        "total_hardware": hardware_total,
        "total_software": software_total,
        "expiring_warranty_30d": expiring_warranty_30d,
        "overdue_warranty": overdue_warranty,
        "rental_expiring_7d": rental_expiring_7d,
        "software_expiring_30d": software_expiring_30d,
        "software_expired": software_expired,
        "status_counts": status_counts,
        "usage_type_counts": usage_type_counts,
        "category_counts": category_counts,
    }
