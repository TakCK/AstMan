from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..services import user_service

router = APIRouter()


@router.post("/users", response_model=schemas.UserResponse, status_code=201, summary="사용자 생성", tags=["사용자"])
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        return user_service.create_user(db, payload)
    except ValueError as e:
        if str(e) == "user_exists":
            raise HTTPException(status_code=409, detail="이미 존재하는 사용자명입니다")
        raise HTTPException(status_code=400, detail="사용자 생성 요청을 확인해주세요")


@router.get("/users", response_model=list[schemas.UserResponse], summary="사용자 목록 조회", tags=["사용자"])
def list_users(
    role: str | None = None,
    q: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        return user_service.list_users(db, role=role, q=q, limit=limit)
    except ValueError as e:
        if str(e) == "invalid_role":
            raise HTTPException(status_code=400, detail="role은 user 또는 admin 이어야 합니다")
        raise HTTPException(status_code=400, detail="요청 값을 확인해주세요")


@router.put("/users/{user_id}", response_model=schemas.UserResponse, summary="사용자 정보 수정", tags=["사용자"])
def update_user_admin(
    user_id: int,
    payload: schemas.UserAdminUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    try:
        updated = user_service.update_user_admin(db, user_id, payload)
    except ValueError as e:
        if str(e) == "empty_update":
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")
        raise HTTPException(status_code=400, detail="요청 값을 확인해주세요")

    if not updated:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    return updated
