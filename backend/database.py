from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, select, func
from datetime import datetime, timedelta
from typing import Optional
import uuid

from config import get_settings
from security import get_password_hash

settings = get_settings()

# 🔥 FIX POSTGRES ASYNC
DATABASE_URL = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# Engine async
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base model
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    role = Column(String(20), default="user")
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    trial_start = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    is_trial_used = Column(Boolean, default=False)
    
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    subscription_status = Column(String(50), default="none")
    subscription_current_period_start = Column(DateTime, nullable=True)
    subscription_current_period_end = Column(DateTime, nullable=True)
    subscription_cancel_at_period_end = Column(Boolean, default=False)
    
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    last_ip = Column(String(45), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "uuid": self.uuid,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "subscription_status": self.subscription_status,
            "trial_start": self.trial_start.isoformat() if self.trial_start else None,
            "trial_end": self.trial_end.isoformat() if self.trial_end else None,
        }

    def is_trial_active(self) -> bool:
        if not self.trial_start or not self.trial_end:
            return False
        return datetime.utcnow() < self.trial_end and self.subscription_status == "trial"

    def is_subscription_active(self) -> bool:
        if self.role in ["admin", "vip"]:
            return True
        if self.subscription_status == "active":
            return True
        return self.is_trial_active()

    def can_access_tool(self) -> bool:
        if self.role in ["admin", "vip"]:
            return True
        if not self.is_active:
            return False
        return self.is_subscription_active()


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    token = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def is_valid(self) -> bool:
        return not self.used and datetime.utcnow() < self.expires_at


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(Text, nullable=True)
    success = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String(100), nullable=False)
    resource = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ================= HELPERS =================

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def count_trial_users(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(User.id)).where(User.is_trial_used == True)
    )
    return result.scalar() or 0


async def ensure_default_accounts(
    db: AsyncSession,
    admin_email: str,
    admin_password: str,
    vip_users: dict[str, str]
):
    """Create admin/VIP lifetime accounts if they do not exist."""
    admin = await get_user_by_email(db, admin_email)
    if not admin:
        db.add(
            User(
                email=admin_email.lower(),
                hashed_password=get_password_hash(admin_password),
                role="admin",
                is_active=True,
                is_verified=True,
                subscription_status="active",
                is_trial_used=False,
            )
        )

    for email, password in vip_users.items():
        vip = await get_user_by_email(db, email.lower())
        if vip:
            continue

        db.add(
            User(
                email=email.lower(),
                hashed_password=get_password_hash(password),
                role="vip",
                is_active=True,
                is_verified=True,
                subscription_status="active",
                is_trial_used=False,
            )
        )

    await db.commit()