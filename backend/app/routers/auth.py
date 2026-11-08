from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Users
from ..schemas import Token, UserLogin, UserMe, UserRegister
from ..security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _user_payload(user: Users) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at,
    }


def _token_payload(user: Users) -> dict:
    return {
        "access_token": create_access_token(user.username),
        "token_type": "bearer",
        "user": _user_payload(user),
    }


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """Register a new user and return an access token."""
    existing = (
        db.query(Users)
        .filter((Users.username == payload.username) | (Users.email == payload.email))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    user = Users(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )
    db.refresh(user)
    return _token_payload(user)


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """Authenticate with username or email and return an access token."""
    identifier = payload.username.strip()
    user = (
        db.query(Users)
        .filter((Users.username == identifier) | (Users.email == identifier))
        .first()
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return _token_payload(user)


@router.get("/me", response_model=UserMe)
def get_me(current_user: Users = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return _user_payload(current_user)


@router.post("/logout")
def logout(current_user: Users = Depends(get_current_user)):
    """Stateless logout acknowledgement.

    JWTs are not server-side revocable in this architecture; the client must
    discard the token. The endpoint exists so clients have a single place to
    call and so it can be extended to a denylist later.
    """
    return {"success": True, "message": "Logged out"}
