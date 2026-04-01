import base64
from io import BytesIO

import qrcode
from qrcode.image.svg import SvgPathImage
from sqlalchemy.orm import Session

from .. import crud, models
from . import branding_service


def _to_data_url(raw: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _build_qr_data_url(content: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=0,
    )
    qr.add_data(content)
    qr.make(fit=True)

    image = qr.make_image(image_factory=SvgPathImage)
    buffer = BytesIO()
    image.save(buffer)
    return _to_data_url(buffer.getvalue(), "image/svg+xml")


def _normalize_owner(value: str | None) -> str:
    return str(value or "").strip()


def _build_owner_display_name_map(db: Session, assets: list[models.Asset]) -> dict[str, str]:
    owner_keys = {
        _normalize_owner(asset.owner)
        for asset in assets
        if _normalize_owner(asset.owner) and _normalize_owner(asset.owner) not in {"미지정", "unassigned", "-"}
    }
    if not owner_keys:
        return {}

    rows = (
        db.query(models.DirectoryUser)
        .filter(models.DirectoryUser.username.in_(owner_keys))
        .all()
    )

    mapping: dict[str, str] = {}
    for row in rows:
        key = _normalize_owner(row.username)
        if not key:
            continue
        display_name = _normalize_owner(row.display_name)
        mapping[key] = display_name or key
    return mapping


def _resolve_owner_display_name(owner: str | None, display_name_map: dict[str, str]) -> str:
    owner_key = _normalize_owner(owner)
    if not owner_key or owner_key in {"미지정", "unassigned", "-"}:
        return "미지정"
    return display_name_map.get(owner_key, owner_key)


def _build_label_item(asset: models.Asset, owner_display_name: str) -> tuple[dict | None, dict | None]:
    asset_code = str(asset.asset_code or "").strip()
    asset_name = str(asset.name or "").strip() or f"asset#{asset.id}"

    if not asset_code:
        return None, {
            "asset_id": asset.id,
            "asset_name": asset_name,
            "reason": "asset_code_missing",
        }

    return {
        "asset_id": asset.id,
        "asset_name": asset_name,
        "asset_code": asset_code,
        "owner": owner_display_name,
        "purchase_date": asset.purchase_date,
        "rental_start_date": asset.rental_start_date,
        "rental_end_date": asset.rental_end_date,
        "qr_code_data_url": _build_qr_data_url(asset_code),
    }, None


def _labels_response_base(db: Session) -> dict:
    branding = branding_service.get_branding_settings(db)
    return {
        "branding_logo_path": str(branding.get("company_logo_path") or ""),
        "labels": [],
        "excluded": [],
    }


def get_asset_label_preview(db: Session, asset_id: int) -> dict:
    response = _labels_response_base(db)
    asset = crud.get_asset(db, asset_id)
    if not asset:
        response["excluded"].append(
            {
                "asset_id": asset_id,
                "asset_name": f"asset#{asset_id}",
                "reason": "asset_not_found",
            }
        )
        return response

    owner_map = _build_owner_display_name_map(db, [asset])
    owner_display_name = _resolve_owner_display_name(asset.owner, owner_map)

    item, excluded = _build_label_item(asset, owner_display_name)
    if item:
        response["labels"].append(item)
    if excluded:
        response["excluded"].append(excluded)
    return response


def get_assets_label_preview(db: Session, asset_ids: list[int]) -> dict:
    response = _labels_response_base(db)

    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in asset_ids:
        try:
            asset_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if asset_id <= 0 or asset_id in seen:
            continue
        seen.add(asset_id)
        normalized_ids.append(asset_id)

    if not normalized_ids:
        return response

    rows = (
        db.query(models.Asset)
        .filter(models.Asset.id.in_(normalized_ids))
        .all()
    )
    row_map = {int(row.id): row for row in rows}
    owner_map = _build_owner_display_name_map(db, rows)

    for asset_id in normalized_ids:
        row = row_map.get(asset_id)
        if not row:
            response["excluded"].append(
                {
                    "asset_id": asset_id,
                    "asset_name": f"asset#{asset_id}",
                    "reason": "asset_not_found",
                }
            )
            continue

        owner_display_name = _resolve_owner_display_name(row.owner, owner_map)
        item, excluded = _build_label_item(row, owner_display_name)
        if item:
            response["labels"].append(item)
        if excluded:
            response["excluded"].append(excluded)

    return response
