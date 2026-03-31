from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models


def _to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(amount, 2)


def _to_krw_cost(
    value: Decimal | float | int | None,
    currency: str | None,
    usd_krw_rate: float,
) -> float:
    return round(float(crud._cost_to_krw(value, currency, usd_krw_rate)), 2)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_date_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return ""

    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return text


def _normalize_department(value: str | None) -> str:
    text = str(value or "").strip()
    return text or "미할당"


def _coerce_detail_item(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    model_dump = getattr(raw, "model_dump", None)
    if callable(model_dump):
        data = model_dump()
        if isinstance(data, dict):
            return data
    return {}


def _build_directory_user_maps(db: Session) -> tuple[dict[str, str], dict[str, str]]:
    department_map: dict[str, str] = {}
    display_name_map: dict[str, str] = {}

    rows = db.query(
        models.DirectoryUser.username,
        models.DirectoryUser.display_name,
        models.DirectoryUser.department,
    ).all()

    for username, display_name, department in rows:
        key = str(username or "").strip()
        if not key:
            continue

        display_text = str(display_name or "").strip() or key
        display_name_map[key] = display_text
        department_map[key] = _normalize_department(department)

    return department_map, display_name_map


def _extract_license_assignees(
    license_row: models.SoftwareLicense,
    department_map: dict[str, str],
    display_name_map: dict[str, str],
) -> list[dict[str, str]]:
    detail_map: dict[str, dict[str, Any]] = {}
    details = license_row.assignee_details if isinstance(license_row.assignee_details, list) else []

    for raw in details:
        item = _coerce_detail_item(raw)
        username = str(item.get("username") or "").strip()
        if not username or username in detail_map:
            continue
        detail_map[username] = item

    usernames: list[str] = []
    seen: set[str] = set()

    assignees = license_row.assignees if isinstance(license_row.assignees, list) else []
    for raw in assignees:
        username = str(raw or "").strip()
        if not username or username in seen:
            continue
        seen.add(username)
        usernames.append(username)

    for username in detail_map:
        if username in seen:
            continue
        seen.add(username)
        usernames.append(username)

    rows: list[dict[str, str]] = []
    default_start_date = _to_date_text(license_row.start_date)
    default_end_date = _to_date_text(license_row.end_date)

    for username in usernames:
        detail = detail_map.get(username, {})
        display_name = display_name_map.get(username, username)
        department = department_map.get(username, "미할당")
        start_date = _to_date_text(detail.get("start_date")) or default_start_date
        end_date = _to_date_text(detail.get("end_date")) or default_end_date

        rows.append(
            {
                "username": username,
                "display_name": display_name,
                "department": department,
                "start_date": start_date,
                "end_date": end_date,
            }
        )

    return rows


def _monthly_unit_cost(subscription_type: str, unit_cost_krw: float) -> float:
    if str(subscription_type or "").strip() == "연 구독":
        return round(unit_cost_krw / 12.0, 2)
    return round(unit_cost_krw, 2)


def _normalize_scope_filter(scope_filter: str | None) -> str:
    key = str(scope_filter or "").strip().lower()
    if key in {"required", "필수", "mandatory", "critical"}:
        return "required"
    if key in {"general", "일반"}:
        return "general"
    return "all"


def _match_scope_filter(scope_filter: str, normalized_scope: str) -> bool:
    if scope_filter == "required":
        return normalized_scope == "필수"
    if scope_filter == "general":
        return normalized_scope == "일반"
    return True


def build_dashboard_software_cost_summary(db: Session, scope_filter: str = "all") -> dict[str, Any]:
    normalized_filter = _normalize_scope_filter(scope_filter)

    department_map, display_name_map = _build_directory_user_maps(db)
    exchange_rate_setting = crud.get_exchange_rate_setting(db)
    usd_krw_rate = float(exchange_rate_setting.get("usd_krw") or crud.DEFAULT_USD_KRW_RATE)

    licenses = (
        db.query(models.SoftwareLicense)
        .order_by(models.SoftwareLicense.product_name.asc(), models.SoftwareLicense.id.asc())
        .all()
    )

    team_buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "users": set(),
            "assigned_license_count": 0,
            "monthly_cost": 0.0,
            "license_types": set(),
        }
    )

    overall_users: set[str] = set()
    overall_assigned_license_count = 0
    overall_monthly_cost = 0.0
    overall_license_types: set[int] = set()

    for license_row in licenses:
        normalized_scope = crud.normalize_license_scope(getattr(license_row, "license_scope", None))
        if not _match_scope_filter(normalized_filter, normalized_scope):
            continue

        unit_cost_krw = _to_krw_cost(
            license_row.purchase_cost,
            license_row.purchase_currency,
            usd_krw_rate,
        )
        if unit_cost_krw <= 0:
            continue

        monthly_unit_cost = _monthly_unit_cost(str(license_row.subscription_type or ""), unit_cost_krw)
        assignee_rows = _extract_license_assignees(license_row, department_map, display_name_map)
        if not assignee_rows:
            continue

        assignment_count_by_user: dict[str, int] = defaultdict(int)
        raw_assignees = [
            str(value or "").strip()
            for value in (license_row.assignees if isinstance(license_row.assignees, list) else [])
            if str(value or "").strip()
        ]
        for username in raw_assignees:
            assignment_count_by_user[username] += 1

        if not assignment_count_by_user:
            for row in assignee_rows:
                username = str(row.get("username") or "").strip()
                if username:
                    assignment_count_by_user[username] += 1

        if not assignment_count_by_user:
            continue

        team_by_user: dict[str, str] = {}
        for row in assignee_rows:
            username = str(row.get("username") or "").strip()
            if not username:
                continue
            team_by_user[username] = _normalize_department(row.get("department"))

        license_id = _to_int(getattr(license_row, "id", 0), default=0)

        for username, seat_count in assignment_count_by_user.items():
            count = max(0, _to_int(seat_count, default=0))
            if count <= 0:
                continue

            team_name = _normalize_department(team_by_user.get(username) or department_map.get(username))
            bucket = team_buckets[team_name]
            bucket["users"].add(username)
            bucket["assigned_license_count"] += count
            bucket["monthly_cost"] += float(monthly_unit_cost) * float(count)
            if license_id > 0:
                bucket["license_types"].add(license_id)
                overall_license_types.add(license_id)

            overall_users.add(username)
            overall_assigned_license_count += count
            overall_monthly_cost += float(monthly_unit_cost) * float(count)

    team_summary = [
        {
            "team_name": team_name,
            "user_count": len(bucket["users"]),
            "assigned_license_count": _to_int(bucket["assigned_license_count"]),
            "monthly_cost": round(_to_float(bucket["monthly_cost"]), 2),
            "yearly_cost": round(_to_float(bucket["monthly_cost"]) * 12.0, 2),
            "license_type_count": len(bucket["license_types"]),
        }
        for team_name, bucket in team_buckets.items()
    ]
    team_summary.sort(key=lambda row: (-float(row["monthly_cost"]), row["team_name"]))

    overall_summary = {
        "team_count": len(team_summary),
        "user_count": len(overall_users),
        "assigned_license_count": overall_assigned_license_count,
        "monthly_cost": round(overall_monthly_cost, 2),
        "yearly_cost": round(overall_monthly_cost * 12.0, 2),
        "license_type_count": len(overall_license_types),
    }

    return {
        "scope_filter": normalized_filter,
        "overall_summary": overall_summary,
        "team_summary": team_summary,
    }


def _normalize_snapshot_month(value: date | None) -> date:
    target = value or date.today()
    return date(target.year, target.month, 1)


def create_software_cost_snapshot(
    db: Session,
    *,
    snapshot_month: date | None = None,
    scope_filter: str = "all",
    overwrite: bool = False,
) -> dict[str, Any]:
    month = _normalize_snapshot_month(snapshot_month)
    normalized_filter = _normalize_scope_filter(scope_filter)

    existing_query = db.query(models.SoftwareCostSnapshot).filter(
        models.SoftwareCostSnapshot.snapshot_month == month,
        models.SoftwareCostSnapshot.scope == normalized_filter,
    )
    has_existing = existing_query.first() is not None
    overwritten = False

    if has_existing and not overwrite:
        raise ValueError("snapshot_exists")

    if has_existing and overwrite:
        existing_query.delete(synchronize_session=False)
        overwritten = True

    summary = build_dashboard_software_cost_summary(db, scope_filter=normalized_filter)
    team_summary = summary.get("team_summary") if isinstance(summary, dict) else []
    team_rows = team_summary if isinstance(team_summary, list) else []

    rows_to_create: list[models.SoftwareCostSnapshot] = []
    for row in team_rows:
        if not isinstance(row, dict):
            continue
        team_name = _normalize_department(str(row.get("team_name") or ""))
        user_count = _to_int(row.get("user_count"), default=0)
        license_count = _to_int(row.get("assigned_license_count"), default=0)
        monthly_cost = _to_float(row.get("monthly_cost"))
        annual_cost = _to_float(row.get("yearly_cost"))

        rows_to_create.append(
            models.SoftwareCostSnapshot(
                snapshot_month=month,
                team_name=team_name,
                scope=normalized_filter,
                user_count=max(0, user_count),
                license_count=max(0, license_count),
                monthly_cost=monthly_cost,
                annual_cost=annual_cost,
            )
        )

    if rows_to_create:
        db.add_all(rows_to_create)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("snapshot_exists")

    rows = (
        db.query(models.SoftwareCostSnapshot)
        .filter(
            models.SoftwareCostSnapshot.snapshot_month == month,
            models.SoftwareCostSnapshot.scope == normalized_filter,
        )
        .order_by(models.SoftwareCostSnapshot.monthly_cost.desc(), models.SoftwareCostSnapshot.team_name.asc())
        .all()
    )

    return {
        "snapshot_month": month,
        "scope_filter": normalized_filter,
        "overwritten": overwritten,
        "created_count": len(rows),
        "rows": rows,
    }


def list_software_cost_snapshots(
    db: Session,
    *,
    scope_filter: str = "all",
    snapshot_month_from: date | None = None,
    snapshot_month_to: date | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    normalized_filter = _normalize_scope_filter(scope_filter)
    safe_limit = max(1, min(limit, 5000))

    query = db.query(models.SoftwareCostSnapshot)
    if normalized_filter != "all":
        query = query.filter(models.SoftwareCostSnapshot.scope == normalized_filter)

    month_from = _normalize_snapshot_month(snapshot_month_from) if snapshot_month_from else None
    month_to = _normalize_snapshot_month(snapshot_month_to) if snapshot_month_to else None

    if month_from:
        query = query.filter(models.SoftwareCostSnapshot.snapshot_month >= month_from)
    if month_to:
        query = query.filter(models.SoftwareCostSnapshot.snapshot_month <= month_to)

    total = query.count()
    rows = (
        query.order_by(
            models.SoftwareCostSnapshot.snapshot_month.desc(),
            models.SoftwareCostSnapshot.monthly_cost.desc(),
            models.SoftwareCostSnapshot.team_name.asc(),
            models.SoftwareCostSnapshot.id.asc(),
        )
        .limit(safe_limit)
        .all()
    )

    return {
        "scope_filter": normalized_filter,
        "snapshot_month_from": month_from,
        "snapshot_month_to": month_to,
        "total": total,
        "rows": rows,
    }


def build_general_license_report_data(db: Session) -> dict[str, Any]:
    department_map, display_name_map = _build_directory_user_maps(db)
    exchange_rate_setting = crud.get_exchange_rate_setting(db)
    usd_krw_rate = float(exchange_rate_setting.get("usd_krw") or crud.DEFAULT_USD_KRW_RATE)

    general_licenses = [
        row
        for row in db.query(models.SoftwareLicense).order_by(models.SoftwareLicense.product_name.asc(), models.SoftwareLicense.id.asc()).all()
        if crud.normalize_license_scope(getattr(row, "license_scope", None)) == "일반"
    ]

    team_buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"users": set(), "assigned_quantity": 0, "monthly_cost": 0.0}
    )
    license_summary: list[dict[str, Any]] = []
    user_detail: list[dict[str, Any]] = []
    all_assigned_users: set[str] = set()

    total_cost = 0.0
    total_license_quantity = 0

    for license_row in general_licenses:
        license_id = int(license_row.id)
        product_name = str(license_row.product_name or "(이름없음)").strip() or "(이름없음)"
        total_quantity = max(0, _to_int(license_row.total_quantity, default=0))

        unit_cost_krw = _to_krw_cost(license_row.purchase_cost, license_row.purchase_currency, usd_krw_rate)
        total_period_cost = round(unit_cost_krw * total_quantity, 2)
        total_cost += total_period_cost
        total_license_quantity += total_quantity

        subscription_type = str(license_row.subscription_type or "").strip()
        monthly_unit_cost = _monthly_unit_cost(subscription_type, unit_cost_krw)

        assignee_rows = _extract_license_assignees(license_row, department_map, display_name_map)

        raw_assignees = [
            str(value or "").strip()
            for value in (license_row.assignees if isinstance(license_row.assignees, list) else [])
            if str(value or "").strip()
        ]

        assignment_count_by_user: dict[str, int] = defaultdict(int)
        for username in raw_assignees:
            assignment_count_by_user[username] += 1

        if not assignment_count_by_user and assignee_rows:
            for row in assignee_rows:
                username = str(row.get("username") or "").strip()
                if username:
                    assignment_count_by_user[username] += 1

        unique_assigned_users: set[str] = set(assignment_count_by_user.keys())
        for row in assignee_rows:
            username = str(row.get("username") or "").strip()
            if username:
                unique_assigned_users.add(username)
        all_assigned_users.update(unique_assigned_users)

        team_users_map: dict[str, set[str]] = defaultdict(set)
        for username in unique_assigned_users:
            team = department_map.get(username, "미할당")
            team_users_map[team].add(username)

        team_assignment_counts: dict[str, int] = defaultdict(int)
        for username, count in assignment_count_by_user.items():
            team = department_map.get(username, "미할당")
            team_assignment_counts[team] += int(count)

        if team_assignment_counts:
            for team_name, seat_count in team_assignment_counts.items():
                bucket = team_buckets[team_name]
                bucket["users"].update(team_users_map.get(team_name, set()))
                bucket["assigned_quantity"] += int(seat_count)
                bucket["monthly_cost"] += float(monthly_unit_cost) * float(seat_count)

        teams_for_license = sorted(team_users_map.keys()) if team_users_map else ["미할당"]

        license_summary.append(
            {
                "license_name": product_name,
                "team": ", ".join(teams_for_license),
                "quantity": total_quantity,
                "user_count": len(unique_assigned_users),
                "cost": total_period_cost,
                "end_date": _to_date_text(license_row.end_date),
            }
        )

        for row in assignee_rows:
            username = str(row.get("username") or "").strip()
            owned_quantity = max(1, int(assignment_count_by_user.get(username, 1)))
            user_detail.append(
                {
                    "user": row["display_name"],
                    "team": _normalize_department(row.get("department")),
                    "license_name": product_name,
                    "unit_cost": unit_cost_krw,
                    "owned_quantity": owned_quantity,
                    "start_date": row.get("start_date") or "",
                    "end_date": row.get("end_date") or "",
                    "review_status": "",
                    "note": "",
                }
            )

    team_summary = [
        {
            "team_name": team_name,
            "user_count": len(bucket["users"]),
            "license_count": int(bucket["assigned_quantity"]),
            "monthly_cost": round(float(bucket["monthly_cost"]), 2),
        }
        for team_name, bucket in team_buckets.items()
    ]
    team_summary.sort(key=lambda row: row["team_name"])

    license_summary.sort(key=lambda row: (row["license_name"], row["team"]))
    user_detail.sort(key=lambda row: (row["team"], row["user"], row["license_name"]))

    summary = {
        "기준일": date.today().isoformat(),
        "총 비용": round(total_cost, 2),
        "총 사용자 수": len(all_assigned_users),
        "총 라이선스 수": total_license_quantity,
    }

    return {
        "summary": summary,
        "team_summary": team_summary,
        "license_summary": license_summary,
        "user_detail": user_detail,
    }


def _apply_header_style(ws) -> None:
    for cell in ws[1]:
        cell.font = Font(bold=True)


def _apply_cost_number_formats(ws) -> None:
    cost_columns: list[int] = []
    for col_idx, cell in enumerate(ws[1], start=1):
        header = str(cell.value or "")
        if "비용" in header:
            cost_columns.append(col_idx)

    for col_idx in cost_columns:
        for row_idx in range(2, ws.max_row + 1):
            target = ws.cell(row=row_idx, column=col_idx)
            if isinstance(target.value, (int, float)):
                target.number_format = "#,##0.00"


def _apply_summary_value_cost_formats(ws) -> None:
    for row_idx in range(2, ws.max_row + 1):
        label = str(ws.cell(row=row_idx, column=1).value or "")
        value_cell = ws.cell(row=row_idx, column=2)
        if "비용" in label and isinstance(value_cell.value, (int, float)):
            value_cell.number_format = "#,##0.00"


def _adjust_column_widths(ws, min_width: int = 10, max_width: int = 48) -> None:
    for column_cells in ws.columns:
        max_length = 0
        column_index = column_cells[0].column
        for cell in column_cells:
            text = "" if cell.value is None else str(cell.value)
            max_length = max(max_length, len(text))
        width = min(max(max_length + 2, min_width), max_width)
        ws.column_dimensions[get_column_letter(column_index)].width = width


def create_general_license_report_workbook(report_data: dict[str, Any]) -> Workbook:
    wb = Workbook()

    ws_summary = wb.active
    ws_summary.title = "Summary"
    ws_summary.append(["항목", "값"])
    summary = report_data.get("summary") or {}
    ws_summary.append(["기준일", summary.get("기준일", "")])
    ws_summary.append(["총 비용(원화 환산, 1인 단가 * 총 보유 수량 기준)", summary.get("총 비용", 0)])
    ws_summary.append(["총 사용자 수", summary.get("총 사용자 수", 0)])
    ws_summary.append(["총 라이선스 수", summary.get("총 라이선스 수", 0)])
    ws_summary.freeze_panes = "A2"
    _apply_header_style(ws_summary)
    _apply_cost_number_formats(ws_summary)
    _apply_summary_value_cost_formats(ws_summary)
    _adjust_column_widths(ws_summary)

    ws_team = wb.create_sheet("Team Summary")
    ws_team.append(["팀명", "사용자 수", "라이선스 수", "월 비용"])
    for row in report_data.get("team_summary") or []:
        ws_team.append(
            [
                row.get("team_name", "미할당"),
                row.get("user_count", 0),
                row.get("license_count", 0),
                row.get("monthly_cost", 0),
            ]
        )
    ws_team.freeze_panes = "A2"
    _apply_header_style(ws_team)
    _apply_cost_number_formats(ws_team)
    _adjust_column_widths(ws_team)

    ws_license = wb.create_sheet("License Summary")
    ws_license.append(["라이선스명", "팀", "수량", "사용자 수", "비용", "만료일"])
    for row in report_data.get("license_summary") or []:
        ws_license.append(
            [
                row.get("license_name", ""),
                row.get("team", ""),
                row.get("quantity", 0),
                row.get("user_count", 0),
                row.get("cost", 0),
                row.get("end_date", ""),
            ]
        )
    ws_license.freeze_panes = "A2"
    _apply_header_style(ws_license)
    _apply_cost_number_formats(ws_license)
    _adjust_column_widths(ws_license)

    ws_user = wb.create_sheet("User Detail")
    ws_user.append(["사용자", "팀", "라이선스", "단위비용", "보유수량", "시작일", "종료일", "검토상태", "비고"])
    for row in report_data.get("user_detail") or []:
        ws_user.append(
            [
                row.get("user", ""),
                row.get("team", "미할당"),
                row.get("license_name", ""),
                row.get("unit_cost", 0),
                row.get("owned_quantity", 0),
                row.get("start_date", ""),
                row.get("end_date", ""),
                row.get("review_status", ""),
                row.get("note", ""),
            ]
        )
    ws_user.freeze_panes = "A2"
    _apply_header_style(ws_user)
    _apply_cost_number_formats(ws_user)
    _adjust_column_widths(ws_user)

    return wb

