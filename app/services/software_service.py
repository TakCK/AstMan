from sqlalchemy.orm import Session

from .. import crud, models, schemas
from . import access_scope_service

SOFTWARE_LICENSE_KEY_SETTING_PREFIX = "software_license_key"


def software_license_key_setting_key(license_id: int) -> str:
    return f"{SOFTWARE_LICENSE_KEY_SETTING_PREFIX}:{license_id}"


def _allowed_usernames(access_scope: access_scope_service.UserAccessScope | None) -> set[str] | None:
    if not access_scope or access_scope.is_admin:
        return None
    return access_scope.subordinate_usernames


def _write_allowed_usernames(access_scope: access_scope_service.UserAccessScope | None) -> set[str] | None:
    if not access_scope:
        return set()
    if access_scope.is_admin:
        return None
    if access_scope.is_team_lead:
        return set(access_scope.managed_usernames or set())
    return set()


def _detail_to_dict(raw) -> dict:
    if isinstance(raw, schemas.SoftwareLicenseAssigneeDetail):
        return raw.model_dump()
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _detail_username(raw) -> str:
    return str(_detail_to_dict(raw).get("username") or "").strip()


def _assignee_usernames_from_payload(payload: schemas.SoftwareLicenseCreate | schemas.SoftwareLicenseUpdate) -> set[str]:
    values = payload.model_dump(exclude_unset=True)
    usernames = {str(value or "").strip() for value in values.get("assignees") or [] if str(value or "").strip()}
    usernames.update(_detail_username(item) for item in values.get("assignee_details") or [])
    usernames.discard("")
    return usernames


def _validate_manager_payload_users(
    payload: schemas.SoftwareLicenseCreate | schemas.SoftwareLicenseUpdate,
    allowed_usernames: set[str] | None,
    *,
    require_assignment: bool = False,
) -> None:
    if allowed_usernames is None:
        return
    if not allowed_usernames:
        raise ValueError("software_write_forbidden")

    payload_usernames = _assignee_usernames_from_payload(payload)
    if require_assignment and not payload_usernames:
        raise ValueError("team_assignment_required")
    if any(username not in allowed_usernames for username in payload_usernames):
        raise ValueError("assignee_scope_forbidden")


def _license_has_no_assignees(row: models.SoftwareLicense) -> bool:
    return not [str(value or "").strip() for value in (row.assignees or []) if str(value or "").strip()]


def _license_has_allowed_assignee(row: models.SoftwareLicense, allowed_usernames: set[str]) -> bool:
    return any(str(value or "").strip() in allowed_usernames for value in (row.assignees or []))


def _merge_manager_assignment_update(
    db_row: models.SoftwareLicense,
    payload: schemas.SoftwareLicenseUpdate,
    allowed_usernames: set[str],
) -> schemas.SoftwareLicenseUpdate:
    updates = payload.model_dump(exclude_unset=True)
    allowed_update_fields = {"assignees", "assignee_details", "allow_multiple_assignments"}
    disallowed = set(updates) - allowed_update_fields
    if disallowed:
        raise ValueError("software_update_forbidden")

    requested_assignees = [
        str(value or "").strip()
        for value in updates.get("assignees", db_row.assignees or [])
        if str(value or "").strip()
    ]
    requested_details = [_detail_to_dict(item) for item in updates.get("assignee_details", db_row.assignee_details or [])]

    outside_assignees = [
        str(username or "").strip()
        for username in (db_row.assignees or [])
        if str(username or "").strip() and str(username or "").strip() not in allowed_usernames
    ]
    managed_assignees = [username for username in requested_assignees if username in allowed_usernames]

    existing_outside_details = [
        _detail_to_dict(item)
        for item in (db_row.assignee_details or [])
        if _detail_username(item) and _detail_username(item) not in allowed_usernames
    ]
    managed_details = [item for item in requested_details if _detail_username(item) in allowed_usernames]

    return schemas.SoftwareLicenseUpdate(
        allow_multiple_assignments=True if updates.get("allow_multiple_assignments") is True else bool(db_row.allow_multiple_assignments),
        assignees=outside_assignees + managed_assignees,
        assignee_details=existing_outside_details + managed_details,
    )


def get_exchange_rate_setting(db: Session) -> dict:
    return crud.get_exchange_rate_setting(db)


def set_exchange_rate_setting(db: Session, payload: schemas.ExchangeRateSettingUpdate) -> dict:
    return crud.set_exchange_rate_setting(db, payload.usd_krw, payload.effective_date)


def create_software_license(
    db: Session,
    payload: schemas.SoftwareLicenseCreate,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> models.SoftwareLicense:
    allowed_write = _write_allowed_usernames(access_scope)
    _validate_manager_payload_users(payload, allowed_write, require_assignment=False)
    return crud.create_software_license(db, payload)


def list_software_licenses(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 200,
    q: str | None = None,
    expiring_days: int | None = None,
    expired_only: bool = False,
    license_scope: str | None = None,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> list[models.SoftwareLicense]:
    if access_scope and access_scope.is_team_lead and not access_scope.is_admin:
        rows = crud.list_software_licenses(
            db,
            skip=0,
            limit=5000,
            q=q,
            expiring_days=expiring_days,
            expired_only=expired_only,
            allowed_assignee_usernames=None,
        )
        managed = set(access_scope.managed_usernames or set())
        rows = [row for row in rows if _license_has_no_assignees(row) or _license_has_allowed_assignee(row, managed)]
        rows = rows[max(0, skip) : max(0, skip) + max(1, min(limit, 5000))]
    else:
        rows = crud.list_software_licenses(
            db,
            skip=max(0, skip),
            limit=max(1, min(limit, 5000)),
            q=q,
            expiring_days=expiring_days,
            expired_only=expired_only,
            allowed_assignee_usernames=_allowed_usernames(access_scope),
        )

    scope_raw = str(license_scope or "").strip()
    if scope_raw and scope_raw.lower() not in {"all", "전체"}:
        scope = crud.normalize_license_scope(scope_raw)
        rows = [row for row in rows if crud.normalize_license_scope(getattr(row, "license_scope", None)) == scope]

    return rows


def get_software_license(
    db: Session,
    license_id: int,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> models.SoftwareLicense | None:
    if access_scope and access_scope.is_team_lead and not access_scope.is_admin:
        row = crud.get_software_license(db, license_id)
        if not row:
            return None
        managed = set(access_scope.managed_usernames or set())
        if _license_has_no_assignees(row) or _license_has_allowed_assignee(row, managed):
            return row
        return None

    return crud.get_software_license(
        db,
        license_id,
        allowed_assignee_usernames=_allowed_usernames(access_scope),
    )


def update_software_license(
    db: Session,
    license_id: int,
    payload: schemas.SoftwareLicenseUpdate,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> models.SoftwareLicense | None:
    allowed_write = _write_allowed_usernames(access_scope)
    if allowed_write is not None:
        if not allowed_write:
            raise ValueError("software_write_forbidden")
        db_row = crud.get_software_license(db, license_id)
        if not db_row:
            return None
        if not (_license_has_no_assignees(db_row) or _license_has_allowed_assignee(db_row, allowed_write)):
            return None
        payload = _merge_manager_assignment_update(db_row, payload, allowed_write)
    else:
        db_row = get_software_license(db, license_id, access_scope=access_scope)

    if not db_row:
        return None
    return crud.update_software_license(db, db_row, payload)


def delete_software_license(
    db: Session,
    license_id: int,
    *,
    access_scope: access_scope_service.UserAccessScope | None = None,
) -> bool:
    db_row = get_software_license(db, license_id, access_scope=access_scope)
    if not db_row:
        return False
    crud.delete_software_license(db, db_row)
    return True


def get_software_license_key(db: Session, license_id: int) -> dict | None:
    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        return None

    key = software_license_key_setting_key(license_id)
    payload = crud.get_app_setting(db, key, {})
    license_key = str(payload.get("license_key") or "")

    return {
        "license_id": license_id,
        "license_key": license_key,
        "has_license_key": bool(license_key.strip()),
    }


def set_software_license_key(
    db: Session,
    license_id: int,
    payload: schemas.SoftwareLicenseKeyUpdate,
) -> dict | None:
    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        return None

    key = software_license_key_setting_key(license_id)
    license_key = str(payload.license_key or "")
    crud.set_app_setting(db, key, {"license_key": license_key})
    return get_software_license_key(db, license_id)


def list_assignment_memos(
    db: Session,
    license_id: int,
    username: str,
    *,
    access_scope: access_scope_service.UserAccessScope | None,
) -> list[models.SoftwareLicenseAssignmentMemo] | None:
    user_key = str(username or "").strip()
    if not user_key:
        raise ValueError("username_required")

    allowed_write = _write_allowed_usernames(access_scope)
    if allowed_write is not None and user_key not in allowed_write:
        raise ValueError("assignee_scope_forbidden")

    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        return None
    if allowed_write is not None and not (_license_has_no_assignees(db_row) or _license_has_allowed_assignee(db_row, allowed_write)):
        return None

    return (
        db.query(models.SoftwareLicenseAssignmentMemo)
        .filter(models.SoftwareLicenseAssignmentMemo.license_id == license_id)
        .filter(models.SoftwareLicenseAssignmentMemo.username == user_key)
        .order_by(models.SoftwareLicenseAssignmentMemo.id.asc())
        .all()
    )


def add_assignment_memo(
    db: Session,
    license_id: int,
    payload: schemas.SoftwareAssignmentMemoCreate,
    actor: models.AppAccount,
    *,
    access_scope: access_scope_service.UserAccessScope | None,
) -> models.SoftwareLicenseAssignmentMemo | None:
    user_key = str(payload.username or "").strip()
    memo_text = str(payload.memo or "").strip()
    if not user_key or not memo_text:
        raise ValueError("memo_required")

    allowed_write = _write_allowed_usernames(access_scope)
    if allowed_write is not None and user_key not in allowed_write:
        raise ValueError("assignee_scope_forbidden")

    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        return None
    if allowed_write is not None and not (_license_has_no_assignees(db_row) or _license_has_allowed_assignee(db_row, allowed_write)):
        return None

    memo = models.SoftwareLicenseAssignmentMemo(
        license_id=license_id,
        username=user_key,
        memo=memo_text,
        actor_user_id=getattr(actor, "id", None),
        actor_username=str(getattr(actor, "username", "") or ""),
    )
    db.add(memo)
    db.commit()
    db.refresh(memo)
    return memo

