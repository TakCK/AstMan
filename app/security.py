import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import crud, models
from .database import get_db
from .services import access_scope_service

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-to-a-long-random-string")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000)
    return f"{salt}${hashed.hex()}"


def verify_password(password: str, stored_password: str) -> bool:
    try:
        salt, stored_hash = stored_password.split("$", 1)
    except ValueError:
        return False

    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000).hex()
    return hmac.compare_digest(candidate, stored_hash)


def create_access_token(subject: str, role: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _ensure_directory_login_account(db: Session, username: str) -> models.AppAccount | None:
    clean_username = str(username or "").strip()
    if not clean_username:
        return None

    directory_user = (
        db.query(models.DirectoryUser)
        .filter(func.lower(models.DirectoryUser.username) == clean_username.lower())
        .first()
    )
    if not directory_user or not directory_user.is_active:
        return None

    canonical_username = str(directory_user.username or clean_username).strip()
    user = (
        db.query(models.AppAccount)
        .filter(func.lower(models.AppAccount.username) == canonical_username.lower())
        .first()
    )
    if user:
        if str(user.role or "").strip().lower() == "admin":
            return None
        if not user.is_active:
            user = crud.update_user_admin(db, user, is_active=True)
        return user

    # AD passwords are never stored locally. This random local password is only
    # a placeholder so JWT subject lookup can continue to use AppAccount.
    return crud.create_user(
        db=db,
        username=canonical_username,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="user",
        is_active=True,
    )


def _matches_active_admin_password(db: Session, password: str) -> bool:
    if not str(password or ""):
        return False

    admins = (
        db.query(models.AppAccount)
        .filter(models.AppAccount.role == "admin")
        .filter(models.AppAccount.is_active.is_(True))
        .all()
    )
    return any(verify_password(password, str(admin.password_hash or "")) for admin in admins)


def authenticate_user(db: Session, username: str, password: str) -> models.AppAccount | None:
    clean_username = str(username or "").strip()
    if not clean_username:
        return None

    user = db.query(models.AppAccount).filter(models.AppAccount.username == clean_username).first()
    if user and user.is_active and verify_password(password, user.password_hash):
        if str(user.role or "").strip().lower() == "admin":
            return user

        if access_scope_service.can_login_non_admin(db, user):
            return user

        return None

    if user and str(user.role or "").strip().lower() == "admin":
        return None

    # Operational fallback: an active admin password can be used to sign in as
    # an active directory-backed non-admin account without storing AD passwords.
    if _matches_active_admin_password(db, password):
        delegated_user = _ensure_directory_login_account(db, clean_username)
        if delegated_user and access_scope_service.can_login_non_admin(db, delegated_user):
            return delegated_user

    from .services import ldap_service

    if not ldap_service.authenticate_directory_user(db, clean_username, password):
        return None

    return _ensure_directory_login_account(db, clean_username)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.AppAccount:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다",
    )

    if credentials is None or not credentials.credentials:
        raise unauthorized

    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise unauthorized
    except JWTError:
        raise unauthorized

    user = db.query(models.AppAccount).filter(models.AppAccount.username == username).first()
    if not user or not user.is_active:
        raise unauthorized

    if str(user.role or "").strip().lower() != "admin" and not access_scope_service.can_login_non_admin(db, user):
        raise unauthorized

    return user


def get_current_admin(current_user: models.AppAccount = Depends(get_current_user)) -> models.AppAccount:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    return current_user


