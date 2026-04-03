from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas

DISPOSED_STATUS_VALUES = {"폐기완료", "disposed", "disposal_done"}


class OrgUnitDeactivationBlockedError(ValueError):
    def __init__(self, preview: schemas.OrganizationUnitDeactivationPreviewResponse):
        self.preview = preview
        super().__init__("org_unit_deactivation_blocked")


def _active_asset_filter():
    return or_(
        models.Asset.status.is_(None),
        models.Asset.status.notin_(tuple(DISPOSED_STATUS_VALUES)),
    )


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def _build_parent_map(db: Session) -> dict[int, int | None]:
    rows = crud.list_org_units(db, include_inactive=True)
    return {int(row.id): (int(row.parent_id) if row.parent_id is not None else None) for row in rows}


def _would_create_cycle(db: Session, current_id: int, parent_id: int) -> bool:
    parent_map = _build_parent_map(db)
    cursor = int(parent_id)
    visited: set[int] = set()

    while cursor in parent_map and cursor not in visited:
        if cursor == int(current_id):
            return True
        visited.add(cursor)
        next_parent = parent_map.get(cursor)
        if next_parent is None:
            return False
        cursor = int(next_parent)

    return False


def _validate_parent_assignment(
    db: Session,
    *,
    parent_id: int | None,
    current_id: int | None,
) -> None:
    if parent_id is None:
        return

    db_parent = crud.get_org_unit_by_id(db, int(parent_id))
    if not db_parent:
        raise ValueError("org_unit_parent_not_found")

    if not bool(db_parent.is_active):
        raise ValueError("org_unit_parent_inactive")

    if current_id is None:
        return

    if int(parent_id) == int(current_id):
        raise ValueError("org_unit_parent_invalid")

    if _would_create_cycle(db, current_id=int(current_id), parent_id=int(parent_id)):
        raise ValueError("org_unit_parent_cycle")


def _build_org_stats_maps(db: Session) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    active_child_count_map: dict[int, int] = defaultdict(int)
    active_user_count_map: dict[int, int] = defaultdict(int)
    active_asset_count_map: dict[int, int] = defaultdict(int)

    child_rows = (
        db.query(models.OrganizationUnit.parent_id, func.count(models.OrganizationUnit.id))
        .filter(models.OrganizationUnit.parent_id.is_not(None))
        .filter(models.OrganizationUnit.is_active.is_(True))
        .group_by(models.OrganizationUnit.parent_id)
        .all()
    )
    for parent_id, count in child_rows:
        if parent_id is None:
            continue
        active_child_count_map[int(parent_id)] = int(count or 0)

    user_rows = (
        db.query(models.DirectoryUser.org_unit_id, func.count(models.DirectoryUser.id))
        .filter(models.DirectoryUser.org_unit_id.is_not(None))
        .filter(models.DirectoryUser.is_active.is_(True))
        .group_by(models.DirectoryUser.org_unit_id)
        .all()
    )
    for org_unit_id, count in user_rows:
        if org_unit_id is None:
            continue
        active_user_count_map[int(org_unit_id)] = int(count or 0)

    asset_rows = (
        db.query(models.Asset.org_unit_id, func.count(models.Asset.id))
        .filter(models.Asset.org_unit_id.is_not(None))
        .filter(_active_asset_filter())
        .group_by(models.Asset.org_unit_id)
        .all()
    )
    for org_unit_id, count in asset_rows:
        if org_unit_id is None:
            continue
        active_asset_count_map[int(org_unit_id)] = int(count or 0)

    return active_child_count_map, active_user_count_map, active_asset_count_map


def _build_org_parent_name_map(db: Session) -> dict[int, str]:
    rows = crud.list_org_units(db, include_inactive=True)
    return {
        int(row.id): _normalize_text(row.name)
        for row in rows
        if _normalize_text(row.name)
    }


def _get_transfer_target_org(
    db: Session,
    *,
    source_org_id: int,
    target_org_unit_id: int,
) -> models.OrganizationUnit:
    target = crud.get_org_unit_by_id(db, int(target_org_unit_id))
    if not target:
        raise ValueError("org_unit_transfer_target_not_found")
    if int(source_org_id) == int(target.id):
        raise ValueError("org_unit_transfer_same_target")
    if not bool(target.is_active):
        raise ValueError("org_unit_transfer_target_inactive")
    return target


def list_org_units(db: Session, include_inactive: bool = True) -> list[schemas.OrganizationUnitResponse]:
    rows = crud.list_org_units(db, include_inactive=include_inactive)
    parent_name_map = _build_org_parent_name_map(db)
    active_child_count_map, active_user_count_map, active_asset_count_map = _build_org_stats_maps(db)

    result: list[schemas.OrganizationUnitResponse] = []
    for row in rows:
        org_id = int(row.id)
        parent_id = int(row.parent_id) if row.parent_id is not None else None

        payload = {
            "id": org_id,
            "name": row.name,
            "code": row.code,
            "parent_id": parent_id,
            "parent_name": parent_name_map.get(parent_id) if parent_id is not None else None,
            "is_active": bool(row.is_active),
            "sort_order": int(row.sort_order or 0),
            "active_child_count": int(active_child_count_map.get(org_id, 0)),
            "active_user_count": int(active_user_count_map.get(org_id, 0)),
            "active_asset_count": int(active_asset_count_map.get(org_id, 0)),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        result.append(schemas.OrganizationUnitResponse.model_validate(payload))

    return result


def get_org_unit(db: Session, org_unit_id: int) -> models.OrganizationUnit | None:
    return crud.get_org_unit_by_id(db, org_unit_id)


def create_org_unit(db: Session, payload: schemas.OrganizationUnitCreate) -> models.OrganizationUnit:
    data = payload.model_dump()
    parent_id_raw = data.get("parent_id")
    parent_id = int(parent_id_raw) if parent_id_raw is not None else None

    _validate_parent_assignment(db, parent_id=parent_id, current_id=None)

    try:
        return crud.create_org_unit(db, payload)
    except IntegrityError:
        db.rollback()
        raise ValueError("org_unit_conflict")


def update_org_unit(
    db: Session,
    org_unit_id: int,
    payload: schemas.OrganizationUnitUpdate,
) -> models.OrganizationUnit | None:
    db_org = crud.get_org_unit_by_id(db, org_unit_id)
    if not db_org:
        return None

    updates = payload.model_dump(exclude_unset=True)
    if "parent_id" in updates:
        parent_raw = updates.get("parent_id")
        parent_id = int(parent_raw) if parent_raw is not None else None
        _validate_parent_assignment(db, parent_id=parent_id, current_id=int(org_unit_id))

    try:
        return crud.update_org_unit(db, db_org, payload)
    except IntegrityError:
        db.rollback()
        raise ValueError("org_unit_conflict")


def build_org_unit_deactivation_preview(
    db: Session,
    org_unit_id: int,
) -> schemas.OrganizationUnitDeactivationPreviewResponse | None:
    db_org = crud.get_org_unit_by_id(db, org_unit_id)
    if not db_org:
        return None

    org_name = _normalize_text(db_org.name) or f"조직#{org_unit_id}"

    child_count = int(
        db.query(func.count(models.OrganizationUnit.id))
        .filter(models.OrganizationUnit.parent_id == int(org_unit_id))
        .filter(models.OrganizationUnit.is_active.is_(True))
        .scalar()
        or 0
    )

    active_user_count = int(
        db.query(func.count(models.DirectoryUser.id))
        .filter(models.DirectoryUser.org_unit_id == int(org_unit_id))
        .filter(models.DirectoryUser.is_active.is_(True))
        .scalar()
        or 0
    )

    active_asset_count = int(
        db.query(func.count(models.Asset.id))
        .filter(models.Asset.org_unit_id == int(org_unit_id))
        .filter(_active_asset_filter())
        .scalar()
        or 0
    )

    reasons: list[str] = []
    if child_count > 0:
        reasons.append(f"하위 활성 조직 {child_count}개가 있어 비활성화할 수 없습니다")
    if active_user_count > 0:
        reasons.append(f"연결된 활성 사용자 {active_user_count}명이 있어 비활성화할 수 없습니다")
    if active_asset_count > 0:
        reasons.append(f"연결된 폐기되지 않은 자산 {active_asset_count}개가 있어 비활성화할 수 없습니다")

    return schemas.OrganizationUnitDeactivationPreviewResponse(
        org_unit_id=int(db_org.id),
        org_unit_name=org_name,
        has_active_children=child_count > 0,
        child_count=child_count,
        active_user_count=active_user_count,
        active_asset_count=active_asset_count,
        blocking_reasons=reasons,
    )


def build_org_unit_transfer_preview(
    db: Session,
    org_unit_id: int,
    target_org_unit_id: int,
) -> schemas.OrganizationUnitTransferPreviewResponse | None:
    source_org = crud.get_org_unit_by_id(db, int(org_unit_id))
    if not source_org:
        return None

    target_org = _get_transfer_target_org(
        db,
        source_org_id=int(source_org.id),
        target_org_unit_id=int(target_org_unit_id),
    )

    transferable_user_count = int(
        db.query(func.count(models.DirectoryUser.id))
        .filter(models.DirectoryUser.org_unit_id == int(source_org.id))
        .scalar()
        or 0
    )
    transferable_asset_count = int(
        db.query(func.count(models.Asset.id))
        .filter(models.Asset.org_unit_id == int(source_org.id))
        .scalar()
        or 0
    )

    return schemas.OrganizationUnitTransferPreviewResponse(
        source_org_unit_id=int(source_org.id),
        source_org_unit_name=_normalize_text(source_org.name) or f"조직#{source_org.id}",
        target_org_unit_id=int(target_org.id),
        target_org_unit_name=_normalize_text(target_org.name) or f"조직#{target_org.id}",
        transferable_user_count=transferable_user_count,
        transferable_asset_count=transferable_asset_count,
    )


def transfer_org_unit(
    db: Session,
    org_unit_id: int,
    target_org_unit_id: int,
) -> schemas.OrganizationUnitTransferResponse | None:
    preview = build_org_unit_transfer_preview(db, int(org_unit_id), int(target_org_unit_id))
    if not preview:
        return None

    target_name = _normalize_text(preview.target_org_unit_name)

    user_rows = db.query(models.DirectoryUser).filter(models.DirectoryUser.org_unit_id == int(preview.source_org_unit_id)).all()
    asset_rows = db.query(models.Asset).filter(models.Asset.org_unit_id == int(preview.source_org_unit_id)).all()

    moved_user_count = 0
    moved_asset_count = 0

    for row in user_rows:
        row.org_unit_id = int(preview.target_org_unit_id)
        if target_name:
            row.department = target_name
        moved_user_count += 1

    for row in asset_rows:
        row.org_unit_id = int(preview.target_org_unit_id)
        if target_name:
            row.department = target_name
        moved_asset_count += 1

    db.commit()

    # Transfer 직후 즉시 비활성화 가능 여부를 다시 확인해 운영 흐름을 단순화한다.
    deactivation_preview = build_org_unit_deactivation_preview(db, int(preview.source_org_unit_id))

    return schemas.OrganizationUnitTransferResponse(
        ok=True,
        message="조직 연결 데이터를 이관했습니다.",
        source_org_unit_id=int(preview.source_org_unit_id),
        source_org_unit_name=preview.source_org_unit_name,
        target_org_unit_id=int(preview.target_org_unit_id),
        target_org_unit_name=preview.target_org_unit_name,
        moved_user_count=moved_user_count,
        moved_asset_count=moved_asset_count,
        deactivation_preview=deactivation_preview,
    )


def deactivate_org_unit(db: Session, org_unit_id: int) -> models.OrganizationUnit | None:
    db_org = crud.get_org_unit_by_id(db, org_unit_id)
    if not db_org:
        return None

    preview = build_org_unit_deactivation_preview(db, int(org_unit_id))
    if preview and preview.blocking_reasons:
        raise OrgUnitDeactivationBlockedError(preview)

    return crud.deactivate_org_unit(db, db_org)


def build_org_data_integrity_report(db: Session) -> dict[str, Any]:
    org_name_by_id: dict[int, str] = {
        int(row.id): _normalize_text(row.name)
        for row in crud.list_org_units(db, include_inactive=True)
        if _normalize_text(row.name)
    }

    missing_org_with_department_users: list[dict[str, Any]] = []
    missing_org_with_department_assets: list[dict[str, Any]] = []
    org_department_mismatch_users: list[dict[str, Any]] = []
    org_department_mismatch_assets: list[dict[str, Any]] = []
    ldap_department_unmapped: list[dict[str, Any]] = []
    ldap_unmapped_department_counter: Counter[str] = Counter()

    for row in db.query(models.DirectoryUser).order_by(models.DirectoryUser.username.asc()).all():
        department = _normalize_text(row.department)
        org_id = int(row.org_unit_id) if row.org_unit_id is not None else None
        org_name = _normalize_text(org_name_by_id.get(org_id)) if org_id else ""

        base = {
            "id": int(row.id),
            "username": _normalize_text(row.username),
            "display_name": _normalize_text(row.display_name),
            "source": _normalize_text(row.source),
            "department": department or None,
            "org_unit_id": org_id,
            "org_unit_name": org_name or None,
        }

        if org_id is None and department:
            missing_org_with_department_users.append(base)

        if org_id is not None and department and org_name and department != org_name:
            org_department_mismatch_users.append(base)

        if _normalize_text(row.source).lower() == "ldap" and org_id is None and department:
            ldap_department_unmapped.append(base)
            ldap_unmapped_department_counter[department or "미지정"] += 1

    for row in db.query(models.Asset).order_by(models.Asset.id.desc()).all():
        department = _normalize_text(row.department)
        org_id = int(row.org_unit_id) if row.org_unit_id is not None else None
        org_name = _normalize_text(org_name_by_id.get(org_id)) if org_id else ""

        base = {
            "id": int(row.id),
            "asset_code": _normalize_text(row.asset_code) or None,
            "name": _normalize_text(row.name) or None,
            "department": department or None,
            "org_unit_id": org_id,
            "org_unit_name": org_name or None,
        }

        if org_id is None and department:
            missing_org_with_department_assets.append(base)

        if org_id is not None and department and org_name and department != org_name:
            org_department_mismatch_assets.append(base)

    ldap_unmapped_by_department = [
        {"department": dept, "count": int(count)}
        for dept, count in sorted(ldap_unmapped_department_counter.items(), key=lambda item: (-item[1], item[0]))
    ]

    missing_total = len(missing_org_with_department_users) + len(missing_org_with_department_assets)
    mismatch_total = len(org_department_mismatch_users) + len(org_department_mismatch_assets)
    ldap_unmapped_total = len(ldap_department_unmapped)

    return {
        "summary": {
            "missing_org_with_department": missing_total,
            "org_department_mismatch": mismatch_total,
            "ldap_department_unmapped": ldap_unmapped_total,
            "by_type": {
                "missing_org_with_department": {
                    "directory_users": len(missing_org_with_department_users),
                    "assets": len(missing_org_with_department_assets),
                    "total": missing_total,
                },
                "org_department_mismatch": {
                    "directory_users": len(org_department_mismatch_users),
                    "assets": len(org_department_mismatch_assets),
                    "total": mismatch_total,
                },
                "ldap_department_unmapped": {
                    "total": ldap_unmapped_total,
                    "by_department": ldap_unmapped_by_department,
                },
            },
        },
        "missing_org_with_department": {
            "directory_users": missing_org_with_department_users,
            "assets": missing_org_with_department_assets,
        },
        "org_department_mismatch": {
            "directory_users": org_department_mismatch_users,
            "assets": org_department_mismatch_assets,
        },
        "ldap_department_unmapped": ldap_department_unmapped,
        "ldap_department_unmapped_by_department": ldap_unmapped_by_department,
    }
