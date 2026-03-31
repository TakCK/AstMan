from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import legacy_main as legacy, models, schemas, security
from ..database import get_db
from ..services import report_service

router = APIRouter()


@router.get("/health", summary="헬스 체크", tags=["대시보드"])
def health_check():
    return legacy.health_check()


@router.get("/dashboard/summary", response_model=schemas.DashboardSummaryResponse, summary="자산 현황 요약", tags=["대시보드"])
def dashboard_summary(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return legacy.dashboard_summary(db, _)


@router.get(
    "/dashboard/software-cost-summary",
    response_model=schemas.DashboardSoftwareCostSummaryResponse,
    summary="팀/부서별 소프트웨어 현재 비용 현황",
    tags=["대시보드"],
)
def dashboard_software_cost_summary(
    scope_filter: str = "all",
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return report_service.build_dashboard_software_cost_summary(db, scope_filter=scope_filter)


@router.post(
    "/dashboard/software-cost-snapshots",
    response_model=schemas.SoftwareCostSnapshotCreateResponse,
    summary="월별 소프트웨어 비용 스냅샷 생성",
    tags=["대시보드"],
)
def create_software_cost_snapshot(
    payload: schemas.SoftwareCostSnapshotCreateRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        return report_service.create_software_cost_snapshot(
            db,
            snapshot_month=payload.snapshot_month,
            scope_filter=payload.scope_filter,
            overwrite=payload.overwrite,
        )
    except ValueError as e:
        if str(e) == "snapshot_exists":
            raise HTTPException(status_code=409, detail="해당 월/범위 스냅샷이 이미 존재합니다. overwrite=true로 재생성하세요.")
        raise


@router.get(
    "/dashboard/software-cost-snapshots",
    response_model=schemas.SoftwareCostSnapshotListResponse,
    summary="월별 소프트웨어 비용 스냅샷 조회",
    tags=["대시보드"],
)
def list_software_cost_snapshots(
    scope_filter: str = "all",
    snapshot_month_from: date | None = None,
    snapshot_month_to: date | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    return report_service.list_software_cost_snapshots(
        db,
        scope_filter=scope_filter,
        snapshot_month_from=snapshot_month_from,
        snapshot_month_to=snapshot_month_to,
        limit=limit,
    )


@router.get("/dashboard/reports/general-licenses.xlsx", summary="일반 라이선스/구독 현황 보고서 다운로드", tags=["대시보드"])
def download_general_license_report(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_user),
):
    report_data = report_service.build_general_license_report_data(db)
    workbook = report_service.create_general_license_report_workbook(report_data)

    buffer = BytesIO()
    try:
        workbook.save(buffer)
    finally:
        workbook.close()

    buffer.seek(0)
    filename = f"general_license_report_{date.today().strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
