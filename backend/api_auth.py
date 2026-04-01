"""
API Autenticazione - Sicurezza massima (FIX DEFINITIVO)
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional

from database import (
    get_db, User, PasswordResetToken, LoginAttempt, 
    get_user_by_email, get_user_by_id
)
from security import (
    verify_password, get_password_hash, create_access_token, create_refresh_token,
    validate_password, get_client_ip,
    limiter, get_current_user_id
)
from config import get_settings, VIP_USERS

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()

TRIAL_LIMIT = settings.MAX_TRIAL_USERS


# ================= SCHEMAS =================

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)

    @validator('email')
    def email_lowercase(cls, v):
        return v.lower()


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @validator('email')
    def email_lowercase(cls, v):
        return v.lower()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


# ================= HELPERS =================

async def log_login_attempt(db: AsyncSession, email: Optional[str], ip: str, user_agent: str, success: bool):
    attempt = LoginAttempt(
        email=email,
        ip_address=ip,
        user_agent=user_agent,
        success=success
    )
    db.add(attempt)
    await db.commit()


async def check_rate_limit_ip(db: AsyncSession, ip: str, max_attempts: int = 10, window_minutes: int = 15):
    cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)

    result = await db.execute(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.ip_address == ip,
            LoginAttempt.success == False,
            LoginAttempt.created_at > cutoff
        )
    )

    return (result.scalar() or 0) < max_attempts


# ================= ROUTES =================

@router.post("/register", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
async def register(
    request: Request,
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    password_check = validate_password(user_data.password)
    if not password_check["valid"]:
        raise HTTPException(status_code=400, detail=password_check["errors"])

    existing_user = await get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email già registrata")

    is_vip = user_data.email in VIP_USERS
    ip = get_client_ip(request)

    result_global = await db.execute(
        select(func.count(User.id)).where(User.is_trial_used == True)
    )
    total_trials = result_global.scalar() or 0

    can_have_trial = (
        total_trials < TRIAL_LIMIT and
        not is_vip
    )

    now = datetime.utcnow()

    new_user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        role="vip" if is_vip else "user",
        is_active=True,
        is_verified=True,

        # 🔥 CRITICO
        last_ip=ip,

        trial_start=now if can_have_trial else None,
        trial_end=now + timedelta(days=settings.TRIAL_DAYS) if can_have_trial else None,
        is_trial_used=can_have_trial,
        subscription_status="trial" if can_have_trial else "none",
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return {
        "access_token": create_access_token({"sub": str(new_user.id), "role": new_user.role}),
        "refresh_token": create_refresh_token({"sub": str(new_user.id)}),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": new_user.to_dict()
    }


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(
    request: Request,
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")

    allowed = await check_rate_limit_ip(db, ip)
    if not allowed:
        raise HTTPException(status_code=429, detail="Troppi tentativi")

    user = await get_user_by_email(db, credentials.email)

    if not user or not verify_password(credentials.password, user.hashed_password):
        await log_login_attempt(db, credentials.email, ip, user_agent, False)
        raise HTTPException(status_code=401, detail="Credenziali non valide")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disattivato")

    user.last_login = datetime.utcnow()
    user.last_ip = ip
    await db.commit()

    await log_login_attempt(db, credentials.email, ip, user_agent, True)

    return {
        "access_token": create_access_token({"sub": str(user.id), "role": user.role}),
        "refresh_token": create_refresh_token({"sub": str(user.id)}),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user.to_dict()
    }


# 🔥 FIX REFRESH LOGIN
@router.get("/me")
async def get_me(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    user = await get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user.to_dict()