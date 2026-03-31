from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends
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
