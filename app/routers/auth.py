from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import legacy_main as legacy, models, schemas, security
from ..database import get_db

router = APIRouter()


@router.post("/auth/login", response_model=schemas.TokenResponse, summary="로그인", tags=["인증"])
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    return legacy.login(payload, db)


@router.get("/me", response_model=schemas.UserResponse, summary="내 계정 조회", tags=["인증"])
def get_me(current_user: models.User = Depends(security.get_current_user)):
    return legacy.get_me(current_user)
