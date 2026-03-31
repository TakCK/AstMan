from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import branding_service, system_info_service

router = APIRouter()


@router.get("/settings/branding", response_model=schemas.BrandingSettingsResponse, summary="브랜딩 설정 조회", tags=["설정"])
def get_branding_settings(
    db: Session = Depends(get_db),
):
    return branding_service.get_branding_settings(db)


@router.put("/settings/branding", response_model=schemas.BrandingSettingsResponse, summary="브랜딩 설정 저장", tags=["설정"])
def set_branding_settings(
    payload: schemas.BrandingSettingsUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return branding_service.set_branding_settings(db, payload.model_dump())


@router.post("/settings/branding/logo", response_model=schemas.BrandingSettingsResponse, summary="브랜딩 로고 업로드", tags=["설정"])
async def upload_branding_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return await branding_service.save_branding_logo(db, file)


@router.get("/settings/system-info", response_model=schemas.SystemInfoResponse, summary="시스템 정보 조회", tags=["설정"])
def get_system_info(
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return system_info_service.get_system_info(db)
