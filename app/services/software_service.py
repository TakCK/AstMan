from sqlalchemy.orm import Session

from .. import crud, models, schemas

SOFTWARE_LICENSE_KEY_SETTING_PREFIX = "software_license_key"


def software_license_key_setting_key(license_id: int) -> str:
    return f"{SOFTWARE_LICENSE_KEY_SETTING_PREFIX}:{license_id}"


def get_exchange_rate_setting(db: Session) -> dict:
    return crud.get_exchange_rate_setting(db)


def set_exchange_rate_setting(db: Session, payload: schemas.ExchangeRateSettingUpdate) -> dict:
    return crud.set_exchange_rate_setting(db, payload.usd_krw, payload.effective_date)


def create_software_license(db: Session, payload: schemas.SoftwareLicenseCreate) -> models.SoftwareLicense:
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
) -> list[models.SoftwareLicense]:
    rows = crud.list_software_licenses(
        db,
        skip=max(0, skip),
        limit=max(1, min(limit, 5000)),
        q=q,
        expiring_days=expiring_days,
        expired_only=expired_only,
    )

    scope_raw = str(license_scope or "").strip()
    if scope_raw and scope_raw.lower() not in {"all", "전체"}:
        scope = crud.normalize_license_scope(scope_raw)
        rows = [row for row in rows if crud.normalize_license_scope(getattr(row, "license_scope", None)) == scope]

    return rows


def get_software_license(db: Session, license_id: int) -> models.SoftwareLicense | None:
    return crud.get_software_license(db, license_id)


def update_software_license(
    db: Session,
    license_id: int,
    payload: schemas.SoftwareLicenseUpdate,
) -> models.SoftwareLicense | None:
    db_row = crud.get_software_license(db, license_id)
    if not db_row:
        return None
    return crud.update_software_license(db, db_row, payload)


def delete_software_license(db: Session, license_id: int) -> bool:
    db_row = crud.get_software_license(db, license_id)
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
