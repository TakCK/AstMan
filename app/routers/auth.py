from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import access_scope_service

router = APIRouter()


@router.post("/auth/login", response_model=schemas.TokenResponse, summary="로그인", tags=["인증"])
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = security.authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")

    access_token = security.create_access_token(
        subject=user.username,
        role=user.role,
        expires_delta=timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return schemas.TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=security.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=schemas.UserResponse, summary="내 계정 조회", tags=["인증"])
def get_me(
    current_user: models.AppAccount = Depends(security.get_current_user),
    db: Session = Depends(get_db),
):
    scope = access_scope_service.build_user_access_scope(db, current_user)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at,
        "is_team_lead": bool(scope.is_team_lead and not scope.is_admin),
        "subordinate_count": len(scope.managed_usernames),
    }


