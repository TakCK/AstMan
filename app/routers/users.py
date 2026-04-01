from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas, security
from ..database import get_db

router = APIRouter()


@router.post("/users", response_model=schemas.UserResponse, status_code=201, summary="사용자 생성", tags=["사용자"])
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    if crud.get_user_by_username(db, payload.username):
        raise HTTPException(status_code=409, detail="이미 존재하는 사용자명입니다")

    try:
        return crud.create_user(
            db=db,
            username=payload.username,
            password_hash=security.hash_password(payload.password),
            role=payload.role,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 존재하는 사용자명입니다")


@router.get("/users", response_model=list[schemas.UserResponse], summary="사용자 목록 조회", tags=["사용자"])
def list_users(
    role: str | None = None,
    q: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    if role and role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="role은 user 또는 admin 이어야 합니다")

    safe_limit = max(1, min(limit, 500))
    return crud.list_users(db, role=role, q=q, limit=safe_limit)


@router.put("/users/{user_id}", response_model=schemas.UserResponse, summary="사용자 정보 수정", tags=["사용자"])
def update_user_admin(
    user_id: int,
    payload: schemas.UserAdminUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(security.get_current_admin),
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    password_hash = None
    if updates.get("password"):
        password_hash = security.hash_password(updates["password"])

    return crud.update_user_admin(
        db,
        db_user,
        is_active=updates.get("is_active"),
        password_hash=password_hash,
    )
