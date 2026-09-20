from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import models
import schemas
from auth import create_access_token, get_current_user, hash_password, require_role, verify_password
from database import get_db

router = APIRouter()


def _token_response(user: models.User) -> dict:
    return {
        "access_token": create_access_token(user.id, user.role),
        "token_type": "bearer",
        "user": schemas.UserOut.model_validate(user),
    }


@router.post("/register", response_model=schemas.TokenOut, status_code=201)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(409, "An account with this email already exists.")
    user = models.User(
        name=payload.name.strip(), email=payload.email, phone=payload.phone,
        password_hash=hash_password(payload.password), role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=schemas.TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username.strip().lower()).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    if not user.is_active:
        raise HTTPException(403, "This account has been suspended.")
    return _token_response(user)


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


# ---- admin -----------------------------------------------------------------
@router.get("/admin/list", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _: models.User = Depends(require_role("admin"))):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.post("/admin/{user_id}/toggle", response_model=schemas.UserOut)
def toggle_user(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_role("admin"))):
    target = db.get(models.User, user_id)
    if not target:
        raise HTTPException(404, "User not found.")
    if target.id == admin.id:
        raise HTTPException(400, "You cannot suspend your own account.")
    target.is_active = not target.is_active
    db.commit()
    db.refresh(target)
    return target
