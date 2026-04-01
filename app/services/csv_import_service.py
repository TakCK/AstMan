from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas


def _value_error_message(err: ValueError) -> str:
    if str(err) == "owner_required_for_in_use":
        return "??? ??? ????? ???? ???? ???"
    if str(err) == "rental_period_invalid":
        return "?? ????? ?? ?????? ?? ? ????"
    if str(err) == "category_immutable":
        return "????? ?? ?? ? ??? ? ????"
    return "?? ?? ??????"


def _decode_csv_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 파일 인코딩을 확인해주세요 (UTF-8 또는 CP949)")


def _normalize_csv_row(raw_row: dict) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (raw_row or {}).items():
        if key is None:
            continue
        key_text = str(key).strip().lower()
        if not key_text:
            continue
        normalized[key_text] = str(value or "").strip()
    return normalized


def _pick_csv_value(row: dict[str, str], aliases: list[str]) -> str:
    for alias in aliases:
        value = row.get(str(alias).strip().lower())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_csv_date(value: str, field_name: str):
    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"{field_name} 날짜 형식이 올바르지 않습니다 (예: 2026-03-27)")


def _parse_csv_float(value: str, field_name: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError as err:
        raise ValueError(f"{field_name} 숫자 형식이 올바르지 않습니다") from err


def _parse_csv_int(value: str, field_name: str, default: int = 1) -> int:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError as err:
        raise ValueError(f"{field_name} 정수 형식이 올바르지 않습니다") from err


def _normalize_import_kind(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"hw", "hardware", "하드웨어", "자산", "asset", "it_asset", "itasset"}:
        return "hw"
    if text in {"sw", "software", "소프트웨어", "license", "licence", "라이선스", "라이센스"}:
        return "sw"
    return ""


def _build_hw_asset_payload(row: dict[str, str]) -> schemas.AssetCreate:
    name = _pick_csv_value(row, ["자산명", "name", "asset_name"])
    category = _pick_csv_value(row, ["카테고리", "category"])

    if not name:
        raise ValueError("HW 자산명은 필수입니다")
    if not category:
        raise ValueError("HW 카테고리는 필수입니다")

    return schemas.AssetCreate(
        name=name,
        category=category,
        usage_type=_pick_csv_value(row, ["사용분류", "usage_type", "usage"]) or "기타장비",
        status=_pick_csv_value(row, ["상태", "status"]) or "대기",
        owner=_pick_csv_value(row, ["사용자", "owner", "assignee"]) or "미지정",
        manager=_pick_csv_value(row, ["담당자", "manager"]) or "미지정",
        department=_pick_csv_value(row, ["부서", "department"]) or None,
        location=_pick_csv_value(row, ["위치", "location"]) or "미지정",
        manufacturer=_pick_csv_value(row, ["제조사", "manufacturer"]) or None,
        model_name=_pick_csv_value(row, ["모델명", "model_name", "model"]) or None,
        serial_number=_pick_csv_value(row, ["시리얼번호", "serial_number", "serial"]) or None,
        asset_code=_pick_csv_value(row, ["자산코드", "asset_code"]) or None,
        vendor=_pick_csv_value(row, ["구매처", "vendor"]) or None,
        purchase_date=_parse_csv_date(_pick_csv_value(row, ["구매일", "purchase_date"]), "HW 구매일"),
        warranty_expiry=_parse_csv_date(_pick_csv_value(row, ["보증만료일", "warranty_expiry", "warranty"]), "HW 보증만료일"),
        purchase_cost=_parse_csv_float(_pick_csv_value(row, ["구매금액", "purchase_cost"]), "HW 구매금액"),
        rental_start_date=_parse_csv_date(_pick_csv_value(row, ["대여시작일", "대여시작일자", "rental_start_date"]), "HW 대여시작일"),
        rental_end_date=_parse_csv_date(_pick_csv_value(row, ["대여만료일", "대여만료일자", "rental_end_date"]), "HW 대여만료일"),
        notes=_pick_csv_value(row, ["메모", "notes", "비고"]) or None,
    )


def _build_sw_license_payload(row: dict[str, str]) -> schemas.SoftwareLicenseCreate:
    product_name = _pick_csv_value(row, ["라이선스명", "product_name", "software_name"])
    if not product_name:
        raise ValueError("SW 라이선스명은 필수입니다")

    total_quantity = _parse_csv_int(_pick_csv_value(row, ["총수량", "총 보유량", "total_quantity"]), "SW 총수량", default=1)
    if total_quantity < 1:
        raise ValueError("SW 총수량은 1 이상이어야 합니다")

    return schemas.SoftwareLicenseCreate(
        product_name=product_name,
        vendor=_pick_csv_value(row, ["공급사", "vendor", "구매처"]) or None,
        license_category=_pick_csv_value(row, ["라이선스구분", "sw구분", "license_category", "category"]) or "기타",
        license_scope=_pick_csv_value(row, ["라이선스성격", "성격", "license_scope", "scope", "필수여부"]) or "일반",
        subscription_type=_pick_csv_value(row, ["구독형태", "subscription_type", "purchase_model"]) or "연 구독",
        start_date=_parse_csv_date(_pick_csv_value(row, ["라이선스시작일", "시작일", "start_date"]), "SW 라이선스시작일"),
        end_date=_parse_csv_date(_pick_csv_value(row, ["라이선스만료일", "만료일", "end_date"]), "SW 라이선스만료일"),
        purchase_cost=_parse_csv_float(_pick_csv_value(row, ["라이선스구매비용", "구매비용", "purchase_cost"]), "SW 구매비용"),
        purchase_currency=_pick_csv_value(row, ["통화", "purchase_currency", "currency"]) or "원",
        total_quantity=total_quantity,
        assignees=[],
        assignee_details=[],
        drafter=_pick_csv_value(row, ["기안자", "drafter"]) or None,
        notes=_pick_csv_value(row, ["메모", "notes", "비고"]) or None,
    )

def _import_csv_rows(
    reader: csv.DictReader,
    db: Session,
    current_user: models.User,
    forced_kind: str | None = None,
) -> dict:
    total_rows = 0
    processed_rows = 0
    created_hardware = 0
    created_software = 0
    failed_rows = 0
    errors: list[dict[str, str | int | None]] = []

    for row_index, raw_row in enumerate(reader, start=2):
        row = _normalize_csv_row(raw_row)
        if not any(str(value or "").strip() for value in row.values()):
            continue

        total_rows += 1

        if forced_kind in {"hw", "sw"}:
            kind = forced_kind
        else:
            kind_raw = _pick_csv_value(row, ["자산유형", "type", "kind", "구분"])
            kind = _normalize_import_kind(kind_raw)

        kind_label = "HW" if kind == "hw" else "SW" if kind == "sw" else None

        if kind not in {"hw", "sw"}:
            failed_rows += 1
            errors.append({"row": row_index, "kind": None, "message": "자산유형은 HW 또는 SW로 입력해주세요"})
            continue

        try:
            if kind == "hw":
                payload = _build_hw_asset_payload(row)
                crud.create_asset(db, payload, actor=current_user)
                created_hardware += 1
            else:
                payload = _build_sw_license_payload(row)
                crud.create_software_license(db, payload)
                created_software += 1

            processed_rows += 1
        except IntegrityError:
            db.rollback()
            failed_rows += 1
            msg = "중복된 자산코드 또는 시리얼번호가 있습니다" if kind == "hw" else "중복 또는 제약조건 오류가 있습니다"
            errors.append({"row": row_index, "kind": kind_label, "message": msg})
        except ValueError as e:
            db.rollback()
            msg = _value_error_message(e) if kind == "hw" else str(e)
            errors.append({"row": row_index, "kind": kind_label, "message": msg})
            failed_rows += 1
        except Exception:
            db.rollback()
            failed_rows += 1
            errors.append({"row": row_index, "kind": kind_label, "message": "행 처리 중 알 수 없는 오류가 발생했습니다"})

    return {
        "ok": True,
        "total_rows": total_rows,
        "processed_rows": processed_rows,
        "created_hardware": created_hardware,
        "created_software": created_software,
        "failed_rows": failed_rows,
        "errors": errors,
    }

async def import_csv_upload(file: UploadFile, db: Session, current_user: models.User, forced_kind: str | None = None) -> dict:
    filename = (file.filename or "").strip().lower()
    if filename and not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV ??? ???? ? ????")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="???? ??? ?? ????")

    try:
        csv_text = _decode_csv_text(raw_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV ??? ?? ? ????")

    return _import_csv_rows(reader, db, current_user, forced_kind=forced_kind)
