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
    get_db, User, PasswordResetToken, LoginAttempt, PhoneOtpToken,
    PhoneTelegramLinkToken, PhoneTelegramLink,
    get_user_by_email, get_user_by_id, get_user_by_phone
)
from security import (
    verify_password, get_password_hash, create_access_token, create_refresh_token,
    validate_password, get_client_ip, generate_password_reset_token, hash_token,
    limiter, get_current_user_id
)
from config import get_settings, VIP_USERS
from mailer import maybe_send_password_reset_email
from otp_sender import maybe_send_otp

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


class PasswordResetRequest(BaseModel):
    email: EmailStr

    @validator('email')
    def email_lowercase(cls, v):
        return v.lower()


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=16)
    new_password: str = Field(..., min_length=8)

class PhoneOtpRequest(BaseModel):
    phone_number: str = Field(..., min_length=6, max_length=32)

class PhoneOtpVerify(BaseModel):
    phone_number: str = Field(..., min_length=6, max_length=32)
    code: str = Field(..., min_length=4, max_length=12)

class PhonePasswordLogin(BaseModel):
    phone_number: str = Field(..., min_length=6, max_length=32)
    password: str = Field(..., min_length=8)

class PhoneOtpRegister(BaseModel):
    phone_number: str = Field(..., min_length=6, max_length=32)
    code: str = Field(..., min_length=4, max_length=12)
    password: str = Field(..., min_length=8)


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


# ================= PASSWORD RESET =================

async def _invalidate_existing_reset_tokens(db: AsyncSession, user_id: int) -> None:
    """Best-effort: marca come used i token precedenti per lo stesso utente."""
    try:
        result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used == False,
            )
        )
        tokens = list(result.scalars().all() or [])
        if not tokens:
            return
        for t in tokens:
            t.used = True
        await db.commit()
    except Exception:
        # Non bloccare il reset se questa pulizia fallisce.
        try:
            await db.rollback()
        except Exception:
            pass


@router.post("/forgot-password")
@router.post("/password-reset-request")
async def password_reset_request(
    request: Request,
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Richiesta reset password.
    Risposta sempre "ok" (anti user enumeration).
    """
    # Risposta generica sempre, anche se l'utente non esiste.
    ok_response = {"message": "Se l'account esiste, riceverai un'email con le istruzioni per il reset."}

    user = await get_user_by_email(db, payload.email)
    if not user:
        return ok_response

    # Invalida token precedenti per ridurre superfici di attacco.
    await _invalidate_existing_reset_tokens(db, user.id)

    raw_token = generate_password_reset_token()
    token_h = hash_token(raw_token)

    expires_at = datetime.utcnow() + timedelta(minutes=30)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token=token_h,
            expires_at=expires_at,
            used=False,
        )
    )
    await db.commit()

    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
    await maybe_send_password_reset_email(
        to_email=user.email,
        reset_link=reset_link,
        request_ip=get_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )

    return ok_response


@router.post("/password-reset-confirm")
async def password_reset_confirm(
    request: Request,
    payload: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Conferma reset password con token."""
    password_check = validate_password(payload.new_password)
    if not password_check["valid"]:
        raise HTTPException(status_code=400, detail=password_check["errors"])

    token_h = hash_token(payload.token)
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token_h)
    )
    prt = result.scalar_one_or_none()
    if not prt or prt.used or datetime.utcnow() >= prt.expires_at:
        raise HTTPException(status_code=400, detail="Token non valido o scaduto")

    user = await get_user_by_id(db, prt.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Account non valido")

    user.hashed_password = get_password_hash(payload.new_password)
    user.updated_at = datetime.utcnow()
    prt.used = True
    await db.commit()

    return {"message": "Password aggiornata con successo. Ora puoi effettuare il login."}


# ================= PHONE OTP LOGIN/REGISTER =================

def _normalize_phone(phone_number: str) -> str:
    # Minimal normalization: remove spaces and keep leading '+' if present.
    s = (phone_number or "").strip().replace(" ", "")
    return s


@router.post("/phone/request-otp")
@limiter.limit("10/minute")
async def phone_request_otp(
    request: Request,
    payload: PhoneOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    phone = _normalize_phone(payload.phone_number)
    if not phone:
        raise HTTPException(status_code=400, detail="Numero non valido")

    # Require Telegram link (free OTP delivery).
    res_link = await db.execute(
        PhoneTelegramLink.__table__.select().where(PhoneTelegramLink.phone_number == phone)
    )
    link_row = res_link.mappings().first()
    if not link_row:
        raise HTTPException(status_code=400, detail="Prima collega Telegram per ricevere OTP (pagina /connect o link telefono).")

    # Generate OTP code (6 digits)
    import secrets
    code = f"{secrets.randbelow(1000000):06d}"
    code_h = hash_token(code)

    expires_at = datetime.utcnow() + timedelta(minutes=5)

    # Invalidate previous active OTPs for this phone
    try:
        result = await db.execute(
            select(PhoneOtpToken).where(
                PhoneOtpToken.phone_number == phone,
                PhoneOtpToken.used == False,
            )
        )
        for t in list(result.scalars().all() or []):
            t.used = True
        await db.commit()
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    db.add(
        PhoneOtpToken(
            phone_number=phone,
            code_hash=code_h,
            expires_at=expires_at,
            used=False,
            attempts=0,
        )
    )
    await db.commit()

    await maybe_send_otp(phone, code)

    # Security-friendly response (never reveal if user exists).
    out = {"message": "Se il numero è valido, riceverai un codice OTP."}
    if settings.ENVIRONMENT == "development":
        out["debug_code"] = code
    return out


@router.post("/phone/telegram-link")
@limiter.limit("10/minute")
async def phone_telegram_link(
    request: Request,
    payload: PhoneOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Genera un link Telegram per collegare un numero PRIMA del login.
    Flusso:
    - inserisci numero
    - apri link t.me/<bot>?start=<token>
    - premi START
    - ora puoi richiedere OTP via Telegram
    """
    phone = _normalize_phone(payload.phone_number)
    if not phone:
        raise HTTPException(status_code=400, detail="Numero non valido")
    if not settings.TELEGRAM_BOT_USERNAME:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_USERNAME non configurato")

    raw = generate_secure_token(24)
    th = hash_token(raw)
    expires = datetime.utcnow() + timedelta(minutes=20)
    db.add(PhoneTelegramLinkToken(phone_number=phone, token_hash=th, expires_at=expires, used=False))
    await db.commit()

    link = f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={raw}"
    return {"connect_url": link, "expires_at": expires.isoformat()}


@router.post("/phone/verify-otp", response_model=TokenResponse)
@limiter.limit("10/minute")
async def phone_verify_otp(
    request: Request,
    payload: PhoneOtpVerify,
    db: AsyncSession = Depends(get_db),
):
    phone = _normalize_phone(payload.phone_number)
    code = (payload.code or "").strip()
    if not phone or not code:
        raise HTTPException(status_code=400, detail="Dati non validi")

    # Find latest OTP for phone (best-effort: most recent by id)
    result = await db.execute(
        select(PhoneOtpToken)
        .where(PhoneOtpToken.phone_number == phone)
        .order_by(PhoneOtpToken.id.desc())
        .limit(1)
    )
    otp = result.scalar_one_or_none()
    if not otp or not otp.is_valid():
        raise HTTPException(status_code=400, detail="OTP non valido o scaduto")

    otp.attempts = int(otp.attempts or 0) + 1
    if otp.attempts > 6:
        otp.used = True
        await db.commit()
        raise HTTPException(status_code=429, detail="Troppi tentativi OTP")

    if hash_token(code) != otp.code_hash:
        await db.commit()
        raise HTTPException(status_code=400, detail="OTP non valido")

    otp.used = True

    # Get or create user for this phone
    user = await get_user_by_phone(db, phone)
    if not user:
        # Create a deterministic placeholder email to keep schema intact.
        safe = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
        email = f"phone_{safe.replace('+','') }@phone.crazy-brain.it".lower()
        # Ensure uniqueness if phone digits collide
        suffix = 0
        while await get_user_by_email(db, email):
            suffix += 1
            email = f"phone_{safe.replace('+','')}_{suffix}@phone.crazy-brain.it".lower()

        # Random password (not used for login); still required by schema.
        import secrets
        rand_pwd = secrets.token_urlsafe(24)
        now = datetime.utcnow()
        user = User(
            email=email,
            hashed_password=get_password_hash(rand_pwd),
            phone_number=phone,
            role="user",
            is_active=True,
            is_verified=True,
            last_ip=get_client_ip(request),
            trial_start=now,
            trial_end=now + timedelta(days=settings.TRIAL_DAYS),
            is_trial_used=True,
            subscription_status="trial",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account disattivato")
        user.last_login = datetime.utcnow()
        user.last_ip = get_client_ip(request)
        await db.commit()

    return {
        "access_token": create_access_token({"sub": str(user.id), "role": user.role}),
        "refresh_token": create_refresh_token({"sub": str(user.id)}),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user.to_dict(),
    }


@router.post("/phone/register", response_model=TokenResponse)
@limiter.limit("10/minute")
async def phone_register_with_otp(
    request: Request,
    payload: PhoneOtpRegister,
    db: AsyncSession = Depends(get_db),
):
    """
    Flusso richiesto:
    - richiedi OTP
    - inserisci OTP + scegli password
    - account creato (o aggiornato) e login
    """
    phone = _normalize_phone(payload.phone_number)
    code = (payload.code or "").strip()
    if not phone or not code:
        raise HTTPException(status_code=400, detail="Dati non validi")

    password_check = validate_password(payload.password)
    if not password_check["valid"]:
        raise HTTPException(status_code=400, detail=password_check["errors"])

    result = await db.execute(
        select(PhoneOtpToken)
        .where(PhoneOtpToken.phone_number == phone)
        .order_by(PhoneOtpToken.id.desc())
        .limit(1)
    )
    otp = result.scalar_one_or_none()
    if not otp or not otp.is_valid():
        raise HTTPException(status_code=400, detail="OTP non valido o scaduto")
    otp.attempts = int(otp.attempts or 0) + 1
    if otp.attempts > 6:
        otp.used = True
        await db.commit()
        raise HTTPException(status_code=429, detail="Troppi tentativi OTP")
    if hash_token(code) != otp.code_hash:
        await db.commit()
        raise HTTPException(status_code=400, detail="OTP non valido")
    otp.used = True

    user = await get_user_by_phone(db, phone)
    now = datetime.utcnow()
    if not user:
        safe = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
        email = f"phone_{safe.replace('+','') }@phone.crazy-brain.it".lower()
        suffix = 0
        while await get_user_by_email(db, email):
            suffix += 1
            email = f"phone_{safe.replace('+','')}_{suffix}@phone.crazy-brain.it".lower()
        user = User(
            email=email,
            hashed_password=get_password_hash(payload.password),
            phone_number=phone,
            role="user",
            is_active=True,
            is_verified=True,
            last_ip=get_client_ip(request),
            trial_start=now,
            trial_end=now + timedelta(days=settings.TRIAL_DAYS),
            is_trial_used=True,
            subscription_status="trial",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account disattivato")
        user.hashed_password = get_password_hash(payload.password)
        user.last_login = now
        user.last_ip = get_client_ip(request)
        await db.commit()

    return {
        "access_token": create_access_token({"sub": str(user.id), "role": user.role}),
        "refresh_token": create_refresh_token({"sub": str(user.id)}),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user.to_dict(),
    }


@router.post("/phone/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def phone_login(
    request: Request,
    payload: PhonePasswordLogin,
    db: AsyncSession = Depends(get_db),
):
    phone = _normalize_phone(payload.phone_number)
    user = await get_user_by_phone(db, phone)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disattivato")
    user.last_login = datetime.utcnow()
    user.last_ip = get_client_ip(request)
    await db.commit()
    return {
        "access_token": create_access_token({"sub": str(user.id), "role": user.role}),
        "refresh_token": create_refresh_token({"sub": str(user.id)}),
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user.to_dict(),
    }


@router.post("/phone/password-reset-request")
@limiter.limit("10/minute")
async def phone_password_reset_request(
    request: Request,
    payload: PhoneOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    # reuse OTP request endpoint behavior
    return await phone_request_otp(request=request, payload=payload, db=db)


@router.post("/phone/password-reset-confirm")
@limiter.limit("10/minute")
async def phone_password_reset_confirm(
    request: Request,
    payload: PhoneOtpRegister,  # phone + code + password
    db: AsyncSession = Depends(get_db),
):
    # Same validation as register, but must already exist
    phone = _normalize_phone(payload.phone_number)
    user = await get_user_by_phone(db, phone)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    # Verify OTP and set password
    _ = await phone_register_with_otp(request=request, payload=payload, db=db)
    return {"message": "Password aggiornata. Ora puoi fare login con numero + password."}