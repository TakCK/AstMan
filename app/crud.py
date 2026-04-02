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

EXCHANGE_RATE_SETTING_KEY = "exchange_rate"
DEFAULT_USD_KRW_RATE = 1350.0
USD_CURRENCY_KEYS = {"usd", "달러", "$", "us$", "dollar", "미국달러"}

LICENSE_SCOPE_ALIAS = {
    "필수": "필수",
    "required": "필수",
    "mandatory": "필수",
    "critical": "필수",
    "일반": "일반",
    "general": "일반",
}
DEFAULT_LICENSE_SCOPE = "일반"


def normalize_status(status: str | None) -> str:
    if not status:
        return DEFAULT_STATUS
    return STATUS_ALIAS.get(status, DEFAULT_STATUS)


def normalize_usage_type(usage_type: str | None) -> str:
    if not usage_type:
        return DEFAULT_USAGE_TYPE
    return USAGE_TYPE_ALIAS.get(usage_type, DEFAULT_USAGE_TYPE)

def normalize_license_scope(license_scope: str | None) -> str:
    text = str(license_scope or "").strip()
    if not text:
        return DEFAULT_LICENSE_SCOPE
    return LICENSE_SCOPE_ALIAS.get(text.lower(), LICENSE_SCOPE_ALIAS.get(text, DEFAULT_LICENSE_SCOPE))



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
    if directory_user:
        if directory_user.org_unit_id:
            org_name = _resolve_org_unit_name_by_id(db, directory_user.org_unit_id)
            if org_name:
                return org_name

        if directory_user.department:
            resolved = directory_user.department.strip()
            if resolved:
                return resolved

    fallback_text = (fallback or "").strip()
    return fallback_text or None


def _normalize_department_name(value: str | None) -> str:
    return str(value or "").strip()


def _resolve_org_unit_name_by_id(db: Session, org_unit_id: int | None) -> str | None:
    if not org_unit_id:
        return None
    row = get_org_unit_by_id(db, int(org_unit_id))
    if not row:
        return None
    name = str(row.name or "").strip()
    return name or None


def _guess_org_unit_id_by_department_name(db: Session, department: str | None) -> int | None:
    department_name = _normalize_department_name(department)
    if not department_name:
        return None

    row = get_org_unit_by_name(db, department_name)
    if not row:
        return None
    return int(row.id)


def _resolve_org_unit_id(
    db: Session,
    org_unit_id,
    department: str | None,
    *,
    strict: bool = False,
    auto_map_by_department: bool = True,
) -> int | None:
    raw = org_unit_id
    if raw not in (None, ""):
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            if strict:
                raise ValueError("org_unit_not_found")
            parsed = None

        if parsed:
            row = get_org_unit_by_id(db, parsed)
            if row:
                return int(row.id)
            if strict:
                raise ValueError("org_unit_not_found")

        if strict:
            raise ValueError("org_unit_not_found")

    if auto_map_by_department:
        return _guess_org_unit_id_by_department_name(db, department)

    return None


def _normalize_assignees(values: list[str] | None, *, allow_duplicates: bool = False) -> list[str]:
    result: list[str] = []
    for value in values or []:
        key = str(value or "").strip()
        if not key:
            continue
        if (not allow_duplicates) and key in result:
            continue
        result.append(key)
    return result


def _string_or_default(value, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _normalize_software_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("사용자별 시작일/만료일 형식이 올바르지 않습니다") from exc


def _normalize_assignee_details(values: list | None, default_purchase_model: str) -> list[dict[str, str | None]]:
    result: list[dict[str, str | None]] = []
    seen: set[str] = set()

    for raw in values or []:
        if isinstance(raw, schemas.SoftwareLicenseAssigneeDetail):
            item = raw.model_dump()
        elif isinstance(raw, dict):
            item = raw
        else:
            continue

        username = str(item.get("username") or "").strip()
        if not username or username in seen:
            continue

        start_date = _normalize_software_date(item.get("start_date"))
        end_date = _normalize_software_date(item.get("end_date"))

        if start_date and end_date and end_date < start_date:
            raise ValueError("사용자별 만료일은 시작일보다 빠를 수 없습니다")

        purchase_model = _string_or_default(item.get("purchase_model"), default_purchase_model)

        result.append(
            {
                "username": username,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "purchase_model": purchase_model,
            }
        )
        seen.add(username)

    return result


def _sync_software_assignees_and_details(
    *,
    assignees: list[str] | None,
    assignee_details: list | None,
    existing_assignees: list[str] | None,
    existing_assignee_details: list | None,
    default_purchase_model: str,
    default_start_date: date | None = None,
    default_end_date: date | None = None,
    allow_duplicates: bool = False,
) -> tuple[list[str], list[dict[str, str | None]]]:
    normalized_assignees = _normalize_assignees(
        assignees if assignees is not None else existing_assignees,
        allow_duplicates=allow_duplicates,
    )
    normalized_details = _normalize_assignee_details(
        assignee_details if assignee_details is not None else existing_assignee_details,
        default_purchase_model,
    )

    detail_map = {row["username"]: row for row in normalized_details}

    if assignees is None and assignee_details is not None:
        normalized_assignees = _normalize_assignees(
            [row["username"] for row in normalized_details],
            allow_duplicates=allow_duplicates,
        )

    default_start = _normalize_software_date(default_start_date) if default_start_date else None
    default_end = _normalize_software_date(default_end_date) if default_end_date else None

    unique_assignees = _normalize_assignees(normalized_assignees, allow_duplicates=False)

    merged_details: list[dict[str, str | None]] = []
    for username in unique_assignees:
        current = detail_map.get(username)
        if current:
            start_date = _normalize_software_date(current.get("start_date"))
            end_date = _normalize_software_date(current.get("end_date"))
            if start_date and end_date and end_date < start_date:
                raise ValueError("사용자별 만료일은 시작일보다 빠를 수 없습니다")

            merged_details.append(
                {
                    "username": username,
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "purchase_model": _string_or_default(current.get("purchase_model"), default_purchase_model),
                }
            )
        else:
            merged_details.append(
                {
                    "username": username,
                    "start_date": default_start.isoformat() if default_start else None,
                    "end_date": default_end.isoformat() if default_end else None,
                    "purchase_model": default_purchase_model,
                }
            )

    return normalized_assignees, merged_details

def _normalize_software_license_json_fields(db_row: models.SoftwareLicense) -> models.SoftwareLicense:
    allow_duplicates = bool(getattr(db_row, "allow_multiple_assignments", False))
    db_row.allow_multiple_assignments = allow_duplicates

    if not isinstance(db_row.assignees, list):
        db_row.assignees = []
    else:
        db_row.assignees = _normalize_assignees(db_row.assignees, allow_duplicates=allow_duplicates)

    if not isinstance(db_row.assignee_details, list):
        db_row.assignee_details = []

    db_row.license_scope = normalize_license_scope(getattr(db_row, "license_scope", None))

    return db_row

def _get_software_assignee_end_dates(db_row: models.SoftwareLicense) -> list[date]:
    _normalize_software_license_json_fields(db_row)

    default_end: date | None = None
    if db_row.end_date:
        try:
            default_end = _normalize_software_date(db_row.end_date)
        except ValueError:
            default_end = None

    detail_end_map: dict[str, date | None] = {}
    for raw in db_row.assignee_details or []:
        if isinstance(raw, schemas.SoftwareLicenseAssigneeDetail):
            item = raw.model_dump()
        elif isinstance(raw, dict):
            item = raw
        else:
            continue

        username = str(item.get("username") or "").strip()
        if not username or username in detail_end_map:
            continue

        try:
            detail_end_map[username] = _normalize_software_date(item.get("end_date"))
        except ValueError:
            detail_end_map[username] = None

    result: list[date] = []
    for raw_user in db_row.assignees or []:
        username = str(raw_user or "").strip()
        if not username:
            continue

        end_date = detail_end_map.get(username)
        if end_date is None:
            end_date = default_end

        if end_date:
            result.append(end_date)

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


def list_org_units(db: Session, include_inactive: bool = True) -> list[models.OrganizationUnit]:
    query = db.query(models.OrganizationUnit)
    if not include_inactive:
        query = query.filter(models.OrganizationUnit.is_active.is_(True))

    return query.order_by(models.OrganizationUnit.sort_order.asc(), models.OrganizationUnit.name.asc()).all()


def get_org_unit_by_id(db: Session, org_unit_id: int) -> models.OrganizationUnit | None:
    return db.query(models.OrganizationUnit).filter(models.OrganizationUnit.id == org_unit_id).first()


def get_org_unit_by_name(db: Session, name: str) -> models.OrganizationUnit | None:
    key = str(name or "").strip()
    if not key:
        return None
    return db.query(models.OrganizationUnit).filter(models.OrganizationUnit.name == key).first()


def create_org_unit(db: Session, payload: schemas.OrganizationUnitCreate) -> models.OrganizationUnit:
    data = payload.model_dump()
    name = str(data.get("name") or "").strip()
    code = str(data.get("code") or "").strip() or None
    parent_id = data.get("parent_id")
    sort_order = int(data.get("sort_order") or 0)

    if not name:
        raise ValueError("org_unit_name_required")

    if parent_id is not None and not get_org_unit_by_id(db, int(parent_id)):
        raise ValueError("org_unit_parent_not_found")

    row = models.OrganizationUnit(
        name=name,
        code=code,
        parent_id=int(parent_id) if parent_id is not None else None,
        is_active=True,
        sort_order=sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_org_unit(
    db: Session,
    db_org_unit: models.OrganizationUnit,
    payload: schemas.OrganizationUnitUpdate,
) -> models.OrganizationUnit:
    updates = payload.model_dump(exclude_unset=True)

    if "name" in updates:
        name = str(updates.get("name") or "").strip()
        if not name:
            raise ValueError("org_unit_name_required")
        db_org_unit.name = name

    if "code" in updates:
        db_org_unit.code = str(updates.get("code") or "").strip() or None

    if "parent_id" in updates:
        parent_id = updates.get("parent_id")
        if parent_id is not None:
            parent_id = int(parent_id)
            if parent_id == int(db_org_unit.id):
                raise ValueError("org_unit_parent_invalid")
            if not get_org_unit_by_id(db, parent_id):
                raise ValueError("org_unit_parent_not_found")
        db_org_unit.parent_id = parent_id

    if "is_active" in updates:
        db_org_unit.is_active = bool(updates.get("is_active"))

    if "sort_order" in updates and updates.get("sort_order") is not None:
        db_org_unit.sort_order = int(updates.get("sort_order") or 0)

    db.commit()
    db.refresh(db_org_unit)
    return db_org_unit


def deactivate_org_unit(db: Session, db_org_unit: models.OrganizationUnit) -> models.OrganizationUnit:
    db_org_unit.is_active = False
    db.commit()
    db.refresh(db_org_unit)
    return db_org_unit


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


def _parse_effective_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return date.fromisoformat(text)
            except ValueError:
                pass
    return date.today()


def _normalize_exchange_rate_payload(raw: dict | None) -> dict:
    payload = raw or {}

    rate_raw = payload.get("usd_krw", DEFAULT_USD_KRW_RATE)
    try:
        rate = float(rate_raw)
    except (TypeError, ValueError):
        rate = DEFAULT_USD_KRW_RATE

    if rate <= 0:
        rate = DEFAULT_USD_KRW_RATE

    effective_date = _parse_effective_date(payload.get("effective_date"))

    return {
        "usd_krw": round(rate, 4),
        "effective_date": effective_date.isoformat(),
    }


def get_exchange_rate_setting(db: Session) -> dict:
    normalized = _normalize_exchange_rate_payload(
        get_app_setting(
            db,
            EXCHANGE_RATE_SETTING_KEY,
            {
                "usd_krw": DEFAULT_USD_KRW_RATE,
                "effective_date": date.today().isoformat(),
            },
        )
    )
    return normalized


def set_exchange_rate_setting(db: Session, usd_krw: float, effective_date: date | None = None) -> dict:
    try:
        rate = float(usd_krw)
    except (TypeError, ValueError):
        rate = DEFAULT_USD_KRW_RATE

    if rate <= 0:
        rate = DEFAULT_USD_KRW_RATE

    payload = {
        "usd_krw": round(rate, 4),
        "effective_date": (effective_date or date.today()).isoformat(),
    }
    set_app_setting(db, EXCHANGE_RATE_SETTING_KEY, payload)
    return payload


def _is_usd_currency(currency: str | None) -> bool:
    key = str(currency or "").strip().lower()
    return key in USD_CURRENCY_KEYS


def _cost_to_krw(value: Decimal | float | int | None, currency: str | None, usd_krw_rate: float) -> float:
    amount = _to_positive_cost(value)
    if amount <= 0:
        return 0.0

    if _is_usd_currency(currency):
        return round(amount * float(usd_krw_rate), 2)

    return amount


def list_directory_users(
    db: Session,
    q: str | None = None,
    limit: int = 200,
    include_inactive: bool = False,
    org_unit_id: int | None = None,
) -> list[models.DirectoryUser]:
    query = db.query(models.DirectoryUser).outerjoin(
        models.OrganizationUnit,
        models.DirectoryUser.org_unit_id == models.OrganizationUnit.id,
    )

    if not include_inactive:
        query = query.filter(models.DirectoryUser.is_active.is_(True))

    if org_unit_id:
        query = query.filter(models.DirectoryUser.org_unit_id == int(org_unit_id))

    if q:
        keyword = f"%{q}%"
        query = query.filter(
            or_(
                models.DirectoryUser.username.ilike(keyword),
                models.DirectoryUser.display_name.ilike(keyword),
                models.DirectoryUser.email.ilike(keyword),
                models.DirectoryUser.department.ilike(keyword),
                models.OrganizationUnit.name.ilike(keyword),
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

    raw_department = (payload.department or "").strip() or None
    resolved_org_unit_id = _resolve_org_unit_id(
        db,
        payload.org_unit_id,
        raw_department,
        strict=payload.org_unit_id not in (None, ""),
        auto_map_by_department=True,
    )

    resolved_department = raw_department
    if not resolved_department and resolved_org_unit_id:
        resolved_department = _resolve_org_unit_name_by_id(db, resolved_org_unit_id)

    row = models.DirectoryUser(
        username=username,
        display_name=(payload.display_name or "").strip() or None,
        email=(payload.email or "").strip() or None,
        department=resolved_department,
        org_unit_id=resolved_org_unit_id,
        title=(payload.title or "").strip() or None,
        manager_dn=(payload.manager_dn or "").strip() or None,
        user_dn=(payload.user_dn or "").strip() or None,
        object_guid=(payload.object_guid or "").strip() or None,
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
    if "org_unit_id" in updates:
        db_user.org_unit_id = _resolve_org_unit_id(
            db,
            updates.get("org_unit_id"),
            db_user.department,
            strict=updates.get("org_unit_id") not in (None, ""),
            auto_map_by_department=False,
        )
    elif "department" in updates and not db_user.org_unit_id:
        db_user.org_unit_id = _resolve_org_unit_id(
            db,
            None,
            db_user.department,
            strict=False,
            auto_map_by_department=True,
        )

    if db_user.org_unit_id and not db_user.department:
        db_user.department = _resolve_org_unit_name_by_id(db, db_user.org_unit_id)

    if "title" in updates:
        db_user.title = (updates.get("title") or "").strip() or None
    if "manager_dn" in updates:
        db_user.manager_dn = (updates.get("manager_dn") or "").strip() or None
    if "user_dn" in updates:
        db_user.user_dn = (updates.get("user_dn") or "").strip() or None
    if "object_guid" in updates:
        db_user.object_guid = (updates.get("object_guid") or "").strip() or None
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

        department = (item.get("department") or "").strip() or None
        org_unit_id = _resolve_org_unit_id(
            db,
            item.get("org_unit_id"),
            department,
            strict=False,
            auto_map_by_department=True,
        )
        if not department and org_unit_id:
            department = _resolve_org_unit_name_by_id(db, org_unit_id)

        incoming[username] = {
            "username": username,
            "display_name": (item.get("display_name") or "").strip() or None,
            "email": (item.get("email") or "").strip() or None,
            "department": department,
            "org_unit_id": org_unit_id,
            "title": (item.get("title") or "").strip() or None,
            "manager_dn": (item.get("manager_dn") or "").strip() or None,
            "user_dn": (item.get("user_dn") or "").strip() or None,
            "object_guid": (item.get("object_guid") or "").strip() or None,
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
                org_unit_id=payload["org_unit_id"],
                title=payload["title"],
                manager_dn=payload["manager_dn"],
                user_dn=payload["user_dn"],
                object_guid=payload["object_guid"],
                is_active=True,
                source=source,
                synced_at=now,
            )
            db.add(row)
            created += 1
            continue

        changed = False
        for field in ["display_name", "email", "department", "org_unit_id", "title", "manager_dn", "user_dn", "object_guid"]:
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
        "org_unit_id": asset.org_unit_id,
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

    payload_org_unit_id = _resolve_org_unit_id(
        db,
        payload.get("org_unit_id"),
        payload.get("department"),
        strict=payload.get("org_unit_id") not in (None, ""),
        auto_map_by_department=True,
    )
    payload["org_unit_id"] = payload_org_unit_id

    if not payload.get("department") and payload_org_unit_id:
        payload["department"] = _resolve_org_unit_name_by_id(db, payload_org_unit_id)

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
    org_unit_id: int | None = None,
    q: str | None = None,
    exclude_disposed: bool = False,
    warranty_expiring_days: int | None = None,
    warranty_overdue: bool = False,
    rental_expiring_days: int | None = None,
):
    query = db.query(models.Asset).outerjoin(
        models.OrganizationUnit,
        models.Asset.org_unit_id == models.OrganizationUnit.id,
    )

    if status:
        normalized = normalize_status(status)
        query = query.filter(or_(models.Asset.status == normalized, models.Asset.status == status))

    if usage_type:
        query = query.filter(models.Asset.usage_type == normalize_usage_type(usage_type))

    if category:
        query = query.filter(models.Asset.category.ilike(f"%{category}%"))

    if department:
        query = query.filter(models.Asset.department.ilike(f"%{department}%"))

    if org_unit_id:
        query = query.filter(models.Asset.org_unit_id == int(org_unit_id))

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
                models.OrganizationUnit.name.ilike(keyword),
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

    if "org_unit_id" in updates:
        updates["org_unit_id"] = _resolve_org_unit_id(
            db,
            updates.get("org_unit_id"),
            updates.get("department"),
            strict=updates.get("org_unit_id") not in (None, ""),
            auto_map_by_department=False,
        )
    else:
        updates["org_unit_id"] = db_asset.org_unit_id
        if not updates["org_unit_id"]:
            updates["org_unit_id"] = _resolve_org_unit_id(
                db,
                None,
                updates.get("department"),
                strict=False,
                auto_map_by_department=True,
            )

    if not updates.get("department") and updates.get("org_unit_id"):
        updates["department"] = _resolve_org_unit_name_by_id(db, updates.get("org_unit_id"))

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

    resolved_department = _resolve_department_from_owner(db, payload.assignee, payload.department)
    resolved_org_unit_id = _resolve_org_unit_id(
        db,
        None,
        resolved_department,
        strict=False,
        auto_map_by_department=True,
    )
    if not resolved_department and resolved_org_unit_id:
        resolved_department = _resolve_org_unit_name_by_id(db, resolved_org_unit_id)

    updates = {
        "status": "사용중",
        "owner": payload.assignee,
        "department": resolved_department,
        "org_unit_id": resolved_org_unit_id,
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
        "org_unit_id": None,
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
    data["license_category"] = _string_or_default(data.get("license_category"), default="기타")
    data["license_scope"] = normalize_license_scope(data.get("license_scope"))
    data["subscription_type"] = _string_or_default(data.get("subscription_type"), default="연 구독")
    data["purchase_currency"] = _string_or_default(data.get("purchase_currency"), default="원")
    data["license_type"] = data["subscription_type"]
    data["allow_multiple_assignments"] = bool(data.get("allow_multiple_assignments", False))

    assignees, assignee_details = _sync_software_assignees_and_details(
        assignees=data.get("assignees"),
        assignee_details=data.get("assignee_details"),
        existing_assignees=None,
        existing_assignee_details=None,
        default_purchase_model=data["subscription_type"],
        default_start_date=data.get("start_date"),
        default_end_date=data.get("end_date"),
        allow_duplicates=bool(data.get("allow_multiple_assignments", False)),
    )
    data["assignees"] = assignees
    data["assignee_details"] = assignee_details

    total_quantity = int(data.get("total_quantity") or 1)
    if len(data["assignees"]) > total_quantity:
        raise ValueError("총 수량보다 할당 수량이 많을 수 없습니다")

    db_row = models.SoftwareLicense(**data)
    db.add(db_row)
    db.commit()
    db.refresh(db_row)
    return _normalize_software_license_json_fields(db_row)



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
                models.SoftwareLicense.license_category.ilike(keyword),
                models.SoftwareLicense.license_scope.ilike(keyword),
                models.SoftwareLicense.subscription_type.ilike(keyword),
                models.SoftwareLicense.vendor.ilike(keyword),
                models.SoftwareLicense.drafter.ilike(keyword),
            )
        )

    rows = query.order_by(models.SoftwareLicense.id.desc()).all()
    rows = [_normalize_software_license_json_fields(row) for row in rows]

    today = date.today()

    if expiring_days and expiring_days > 0:
        until = today + timedelta(days=expiring_days)
        rows = [
            row
            for row in rows
            if any(today <= end_date <= until for end_date in _get_software_assignee_end_dates(row))
        ]

    if expired_only:
        rows = [
            row
            for row in rows
            if any(end_date < today for end_date in _get_software_assignee_end_dates(row))
        ]

    safe_skip = max(0, int(skip or 0))
    safe_limit = max(1, int(limit or 200))
    return rows[safe_skip : safe_skip + safe_limit]



def get_software_license(db: Session, license_id: int) -> models.SoftwareLicense | None:
    row = db.query(models.SoftwareLicense).filter(models.SoftwareLicense.id == license_id).first()
    if not row:
        return None
    return _normalize_software_license_json_fields(row)



def update_software_license(
    db: Session,
    db_row: models.SoftwareLicense,
    payload: schemas.SoftwareLicenseUpdate,
) -> models.SoftwareLicense:
    updates = payload.model_dump(exclude_unset=True)

    if "license_category" in updates:
        updates["license_category"] = _string_or_default(updates.get("license_category"), default="기타")

    if "license_scope" in updates:
        updates["license_scope"] = normalize_license_scope(updates.get("license_scope"))

    if "subscription_type" in updates:
        updates["subscription_type"] = _string_or_default(updates.get("subscription_type"), default="연 구독")
        updates["license_type"] = updates["subscription_type"]

    if "purchase_currency" in updates:
        updates["purchase_currency"] = _string_or_default(updates.get("purchase_currency"), default="원")

    if "allow_multiple_assignments" in updates:
        updates["allow_multiple_assignments"] = bool(updates.get("allow_multiple_assignments"))

    next_subscription_type = updates.get("subscription_type") or db_row.subscription_type or "연 구독"
    next_start_date = updates.get("start_date", db_row.start_date)
    next_end_date = updates.get("end_date", db_row.end_date)
    next_allow_multiple_assignments = bool(updates.get("allow_multiple_assignments") if "allow_multiple_assignments" in updates else db_row.allow_multiple_assignments)

    next_assignees, next_assignee_details = _sync_software_assignees_and_details(
        assignees=updates.get("assignees") if "assignees" in updates else None,
        assignee_details=updates.get("assignee_details") if "assignee_details" in updates else None,
        existing_assignees=db_row.assignees,
        existing_assignee_details=db_row.assignee_details,
        default_purchase_model=next_subscription_type,
        default_start_date=next_start_date,
        default_end_date=next_end_date,
        allow_duplicates=next_allow_multiple_assignments,
    )

    if "assignees" in updates or "assignee_details" in updates or "subscription_type" in updates or "allow_multiple_assignments" in updates:
        updates["assignees"] = next_assignees
        updates["assignee_details"] = next_assignee_details

    next_total = int(updates.get("total_quantity") or db_row.total_quantity or 1)
    if len(next_assignees) > next_total:
        raise ValueError("총 수량보다 할당 수량이 많을 수 없습니다")

    for field, value in updates.items():
        setattr(db_row, field, value)

    db.commit()
    db.refresh(db_row)
    return _normalize_software_license_json_fields(db_row)



def delete_software_license(db: Session, db_row: models.SoftwareLicense):
    db.delete(db_row)
    db.commit()


def _normalize_cost_date(value: date | datetime | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _to_positive_cost(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0

    try:
        amount = float(value)
    except (TypeError, ValueError):
        return 0.0

    if amount <= 0:
        return 0.0

    return amount


def _month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _month_index_from_date(value: date) -> int:
    return _month_index(value.year, value.month)


def _month_key(month_index: int) -> str:
    year = month_index // 12
    month = month_index % 12 + 1
    return f"{year:04d}-{month:02d}"


def _month_label(month_index: int) -> str:
    year = month_index // 12
    month = month_index % 12 + 1
    return f"{str(year)[2:]}년 {month}월"


def _quarter_key(quarter_index: int) -> str:
    year = quarter_index // 4
    quarter = quarter_index % 4 + 1
    return f"{year:04d}-Q{quarter}"


def _quarter_label(quarter_index: int) -> str:
    year = quarter_index // 4
    quarter = quarter_index % 4 + 1
    return f"{str(year)[2:]}년 {quarter}Q"


def _period_key_label(period: str, index: int) -> tuple[str, str]:
    if period == "month":
        return _month_key(index), _month_label(index)
    if period == "quarter":
        return _quarter_key(index), _quarter_label(index)
    year = int(index)
    return f"{year:04d}", f"{year}년"


def _period_month_span(period: str, index: int) -> tuple[int, int]:
    if period == "month":
        return index, index
    if period == "quarter":
        year = index // 4
        quarter_zero_based = index % 4
        start_month = year * 12 + quarter_zero_based * 3
        return start_month, start_month + 2

    start_month = int(index) * 12
    return start_month, start_month + 11


def _period_index_from_month(period: str, month_index: int) -> int:
    if period == "month":
        return month_index
    if period == "quarter":
        return month_index // 3
    return month_index // 12


def _software_monthly_cost(subscription_type: str, amount: float) -> float:
    normalized = str(subscription_type or "월 구독").strip()
    if normalized == "연 구독":
        return amount / 12.0
    return amount


def _software_cost_in_month_span(
    subscription_type: str,
    amount: float,
    start_month_index: int,
    end_month_index: int,
    bucket_start_month_index: int,
    bucket_end_month_index: int,
) -> float:
    if bucket_end_month_index < start_month_index or bucket_start_month_index > end_month_index:
        return 0.0

    if subscription_type == "영구 구매":
        return amount if bucket_start_month_index <= start_month_index <= bucket_end_month_index else 0.0

    active_start = max(bucket_start_month_index, start_month_index)
    active_end = min(bucket_end_month_index, end_month_index)
    active_months = max(0, active_end - active_start + 1)
    if active_months <= 0:
        return 0.0

    monthly_cost = _software_monthly_cost(subscription_type, amount)
    return monthly_cost * active_months

def _build_hardware_history_points(
    hardware_events: list[tuple[date, float]],
    period: str,
    today: date,
) -> list[dict[str, str | float]]:
    current_month_index = _month_index_from_date(today)
    current_period_index = _period_index_from_month(period, current_month_index)

    period_cost_map: dict[int, float] = {}
    min_period_index = current_period_index

    for event_date, amount in hardware_events:
        month_index = _month_index_from_date(event_date)
        period_index = _period_index_from_month(period, month_index)
        period_cost_map[period_index] = period_cost_map.get(period_index, 0.0) + amount
        min_period_index = min(min_period_index, period_index)

    points: list[dict[str, str | float]] = []
    cumulative = 0.0

    for period_index in range(min_period_index, current_period_index + 1):
        period_cost = round(float(period_cost_map.get(period_index, 0.0)), 2)
        cumulative = round(cumulative + period_cost, 2)
        key, label = _period_key_label(period, period_index)
        points.append(
            {
                "key": key,
                "label": label,
                "period_cost": period_cost,
                "cumulative_cost": cumulative,
            }
        )

    return points


def _build_software_projection_points(
    software_rows: list[tuple[date | None, date | None, datetime, Decimal | float | int | None, str | None, str | None, str | None, int | None]],
    period: str,
    today: date,
    usd_krw_rate: float,
    license_scope_filter: str = "all",
) -> list[dict[str, str | float | bool]]:
    current_month_index = _month_index_from_date(today)
    current_period_index = _period_index_from_month(period, current_month_index)

    scope_filter_key = str(license_scope_filter or "all").strip().lower()
    if scope_filter_key not in {"all", "required", "general"}:
        scope_filter_key = "all"

    normalized_rows: list[dict[str, int | float | str]] = []
    for start_date, end_date, created_at, purchase_cost, purchase_currency, subscription_type, license_scope, total_quantity in software_rows:
        quantity = max(0, int(total_quantity or 0))
        if quantity <= 0:
            continue

        unit_amount = _cost_to_krw(purchase_cost, purchase_currency, usd_krw_rate)
        amount = round(unit_amount * quantity, 2)
        if amount <= 0:
            continue

        base_date = _normalize_cost_date(start_date) or _normalize_cost_date(created_at)
        if base_date is None:
            continue

        start_month_index = _month_index_from_date(base_date)
        end_base = _normalize_cost_date(end_date)
        end_month_index = _month_index_from_date(end_base) if end_base else (current_month_index + 120)

        normalized_rows.append(
            {
                "start_month_index": start_month_index,
                "end_month_index": end_month_index,
                "amount": amount,
                "subscription_type": str(subscription_type or "월 구독"),
                "license_scope": normalize_license_scope(license_scope),
            }
        )

    points: list[dict[str, str | float | bool]] = []
    for period_index in range(current_period_index - 3, current_period_index + 4):
        bucket_start_month_index, bucket_end_month_index = _period_month_span(period, period_index)
        total_cost = 0.0

        for row in normalized_rows:
            row_scope = str(row.get("license_scope") or DEFAULT_LICENSE_SCOPE).strip()
            if scope_filter_key == "required" and row_scope != "필수":
                continue
            if scope_filter_key == "general" and row_scope != "일반":
                continue

            total_cost += _software_cost_in_month_span(
                str(row["subscription_type"]),
                float(row["amount"]),
                int(row["start_month_index"]),
                int(row["end_month_index"]),
                bucket_start_month_index,
                bucket_end_month_index,
            )

        total_cost = round(total_cost, 2)
        is_forecast = period_index > current_period_index
        actual_cost = 0.0 if is_forecast else total_cost
        expected_cost = total_cost if is_forecast else 0.0
        key, label = _period_key_label(period, period_index)

        points.append(
            {
                "key": key,
                "label": label,
                "actual_cost": round(actual_cost, 2),
                "expected_cost": round(expected_cost, 2),
                "total_cost": total_cost,
                "is_forecast": is_forecast,
            }
        )

    return points

def _build_dashboard_cost_trends(db: Session, today: date, usd_krw_rate: float) -> dict[str, dict[str, list[dict[str, str | float | bool]] | dict[str, list[dict[str, str | float | bool]]]]]:
    hardware_rows = (
        db.query(models.Asset.purchase_date, models.Asset.created_at, models.Asset.purchase_cost)
        .filter(models.Asset.purchase_cost.is_not(None))
        .all()
    )
    hardware_events: list[tuple[date, float]] = []
    for purchase_date, created_at, purchase_cost in hardware_rows:
        amount = _to_positive_cost(purchase_cost)
        event_date = _normalize_cost_date(purchase_date) or _normalize_cost_date(created_at)
        if amount <= 0 or event_date is None:
            continue
        hardware_events.append((event_date, amount))

    software_rows = (
        db.query(
            models.SoftwareLicense.start_date,
            models.SoftwareLicense.end_date,
            models.SoftwareLicense.created_at,
            models.SoftwareLicense.purchase_cost,
            models.SoftwareLicense.purchase_currency,
            models.SoftwareLicense.subscription_type,
            models.SoftwareLicense.license_scope,
            models.SoftwareLicense.total_quantity,
        )
        .filter(models.SoftwareLicense.purchase_cost.is_not(None))
        .all()
    )

    trends: dict[str, dict[str, list[dict[str, str | float | bool]] | dict[str, list[dict[str, str | float | bool]]]]] = {}
    for period in ("month", "quarter", "year"):
        all_points = _build_software_projection_points(software_rows, period, today, usd_krw_rate, "all")
        required_points = _build_software_projection_points(software_rows, period, today, usd_krw_rate, "required")
        general_points = _build_software_projection_points(software_rows, period, today, usd_krw_rate, "general")

        trends[period] = {
            "hardware_history": _build_hardware_history_points(hardware_events, period, today),
            "software_projection": all_points,
            "software_projection_by_scope": {
                "all": all_points,
                "required": required_points,
                "general": general_points,
            },
        }

    return trends


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

    software_rows = db.query(models.SoftwareLicense).all()
    software_total = 0
    software_expiring_30d = 0
    software_expired = 0

    for sw_row in software_rows:
        total_quantity = int(sw_row.total_quantity or 0)
        if total_quantity > 0:
            software_total += total_quantity

        for end_date in _get_software_assignee_end_dates(sw_row):
            if today <= end_date <= upcoming:
                software_expiring_30d += 1
            elif end_date < today:
                software_expired += 1

    hardware_total = sum(status_counts[key] for key in status_keys if key != "폐기완료")
    exchange_rate_setting = get_exchange_rate_setting(db)
    usd_krw_rate = float(exchange_rate_setting.get("usd_krw") or DEFAULT_USD_KRW_RATE)
    cost_trends = _build_dashboard_cost_trends(db, today, usd_krw_rate)

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
        "cost_trends": cost_trends,
    }

































