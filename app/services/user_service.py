from collections import defaultdict

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas, security


def create_user(db: Session, payload: schemas.UserCreate) -> models.User:
    if crud.get_user_by_username(db, payload.username):
        raise ValueError("user_exists")

    try:
        return crud.create_user(
            db=db,
            username=payload.username,
            password_hash=security.hash_password(payload.password),
            role=payload.role,
        )
    except IntegrityError:
        db.rollback()
        raise ValueError("user_exists")


def list_users(db: Session, role: str | None = None, q: str | None = None, limit: int = 200) -> list[models.User]:
    if role and role not in {"user", "admin"}:
        raise ValueError("invalid_role")

    safe_limit = max(1, min(limit, 500))
    return crud.list_users(db, role=role, q=q, limit=safe_limit)


def update_user_admin(db: Session, user_id: int, payload: schemas.UserAdminUpdate) -> models.User | None:
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        return None

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise ValueError("empty_update")

    password_hash = None
    if updates.get("password"):
        password_hash = security.hash_password(updates["password"])

    return crud.update_user_admin(
        db,
        db_user,
        is_active=updates.get("is_active"),
        password_hash=password_hash,
    )


def _to_directory_user_response(db: Session, db_user: models.DirectoryUser) -> schemas.DirectoryUserResponse:
    org_unit_name = None
    if db_user.org_unit_id:
        db_org = crud.get_org_unit_by_id(db, int(db_user.org_unit_id))
        if db_org:
            org_unit_name = str(db_org.name or "").strip() or None
    if not org_unit_name:
        org_unit_name = str(db_user.department or "").strip() or None

    payload = {
        "id": db_user.id,
        "username": db_user.username,
        "display_name": db_user.display_name,
        "email": db_user.email,
        "department": db_user.department,
        "org_unit_id": db_user.org_unit_id,
        "org_unit_name": org_unit_name,
        "title": db_user.title,
        "manager_dn": db_user.manager_dn,
        "user_dn": db_user.user_dn,
        "object_guid": db_user.object_guid,
        "is_active": db_user.is_active,
        "source": db_user.source,
        "synced_at": db_user.synced_at,
    }
    return schemas.DirectoryUserResponse.model_validate(payload)


def list_directory_users(
    db: Session,
    *,
    q: str | None = None,
    limit: int = 200,
    include_inactive: bool = False,
    org_unit_id: int | None = None,
) -> list[schemas.DirectoryUserResponse]:
    safe_limit = max(1, min(limit, 5000))
    rows = crud.list_directory_users(db, q=q, limit=safe_limit, include_inactive=include_inactive, org_unit_id=org_unit_id)
    return [_to_directory_user_response(db, row) for row in rows]


def create_directory_user(
    db: Session,
    payload: schemas.DirectoryUserCreate,
    *,
    source: str = "manual",
) -> schemas.DirectoryUserResponse:
    db_user = crud.create_directory_user(db, payload, source=source)
    return _to_directory_user_response(db, db_user)


def update_directory_user(
    db: Session,
    directory_user_id: int,
    payload: schemas.DirectoryUserUpdate,
) -> schemas.DirectoryUserResponse | None:
    db_user = crud.get_directory_user_by_id(db, directory_user_id)
    if not db_user:
        return None

    if payload.model_dump(exclude_unset=True) == {}:
        raise ValueError("empty_update")

    db_user = crud.update_directory_user(db, db_user, payload)
    return _to_directory_user_response(db, db_user)


def apply_directory_user_sync_hooks(db: Session, users: list[dict]) -> list[dict]:
    # LDAP source hook point: currently maps department(name) -> org_unit_id (exact match).
    mapped: list[dict] = []
    for item in users:
        row = dict(item or {})
        if row.get("org_unit_id") in (None, ""):
            department = str(row.get("department") or "").strip()
            if department:
                db_org = crud.get_org_unit_by_name(db, department)
                if db_org:
                    row["org_unit_id"] = int(db_org.id)
        mapped.append(row)
    return mapped


def import_directory_users(
    db: Session,
    payload: schemas.DirectoryUserBulkImportRequest,
    *,
    source: str = "ldap",
) -> dict:
    users = [item.model_dump() for item in payload.users]
    users = apply_directory_user_sync_hooks(db, users)
    result = crud.upsert_directory_users(db, users, source=source, deactivate_missing=False)
    return {
        "ok": True,
        "message": "LDAP 검색결과를 사용자 탭에 반영했습니다",
        "result": result,
    }


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


def build_directory_user_deactivation_preview(
    db: Session,
    directory_user_id: int,
) -> schemas.DirectoryUserDeactivationPreviewResponse | None:
    db_user = crud.get_directory_user_by_id(db, directory_user_id)
    if not db_user:
        return None

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


def deactivate_directory_user(
    db: Session,
    directory_user_id: int,
    payload: schemas.DirectoryUserDeactivateRequest,
    current_admin: models.User,
) -> schemas.DirectoryUserDeactivateResponse | None:
    db_user = crud.get_directory_user_by_id(db, directory_user_id)
    if not db_user:
        return None

    preview = build_directory_user_deactivation_preview(db, directory_user_id)
    if not preview:
        return None

    if not preview.is_active:
        return schemas.DirectoryUserDeactivateResponse(
            ok=True,
            message="이미 비활성 사용자입니다.",
            released_asset_count=0,
            remaining_asset_count=preview.assigned_asset_count,
            assigned_license_count=preview.assigned_license_count,
            user=_to_directory_user_response(db, db_user),
        )

    assigned_assets = _collect_user_assigned_assets(db, db_user)
    asset_map = {int(asset.id): asset for asset in assigned_assets}

    released_asset_count = 0

    if assigned_assets:
        if not payload.release_assets:
            raise ValueError("assigned_assets_exist")

        requested_ids = [int(v) for v in (payload.asset_ids or []) if int(v) > 0]
        target_ids = requested_ids if requested_ids else list(asset_map.keys())

        invalid_ids = [asset_id for asset_id in target_ids if asset_id not in asset_map]
        if invalid_ids:
            raise ValueError("invalid_asset_ids")

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
            except ValueError as exc:
                raise ValueError(f"asset_release_failed:{asset_id}") from exc

    remaining_assets = _collect_user_assigned_assets(db, db_user)
    if remaining_assets:
        raise ValueError("remaining_assets_exist")

    updated_user = crud.update_directory_user(
        db,
        db_user,
        schemas.DirectoryUserUpdate(is_active=False),
    )

    remaining_license_rows = _collect_user_assigned_licenses(db, updated_user)
    remaining_license_count = sum(int(row.assignment_count) for row in remaining_license_rows)

    return schemas.DirectoryUserDeactivateResponse(
        ok=True,
        message="사용자를 비활성화했습니다.",
        released_asset_count=released_asset_count,
        remaining_asset_count=0,
        assigned_license_count=remaining_license_count,
        user=_to_directory_user_response(db, updated_user),
    )



