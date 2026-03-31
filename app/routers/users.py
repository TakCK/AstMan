from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import legacy_main as legacy, models, schemas, security
from ..database import get_db

router = APIRouter()


@router.post("/users", response_model=schemas.UserResponse, status_code=201, summary="사용자 생성", tags=["사용자"])
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return legacy.create_user(payload, db, _)


@router.get("/users", response_model=list[schemas.UserResponse], summary="사용자 목록 조회", tags=["사용자"])
def list_users(
    role: str | None = None,
    q: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return legacy.list_users(role, q, limit, db, _)


@router.put("/users/{user_id}", response_model=schemas.UserResponse, summary="사용자 정보 수정", tags=["사용자"])
def update_user_admin(
    user_id: int,
    payload: schemas.UserAdminUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    return legacy.update_user_admin(user_id, payload, db, _)
