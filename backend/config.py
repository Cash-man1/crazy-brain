"""
Configurazione applicazione con sicurezza massima
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    """Configurazione sicura dell'applicazione"""
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./crazybrain.db"
    
    # Sicurezza JWT
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_MIN_32_CHARS"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_MONTHLY: str = ""
    STRIPE_PRICE_ANNUAL: str = ""
    
    # Email
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = ""
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_TLS: bool = True
    MAIL_SSL: bool = False
    
    # App
    APP_NAME: str = "Crazy Brain"
    APP_URL: str = "https://crazy-brain.it"
    FRONTEND_URL: str = "https://crazy-brain.it"
    ENVIRONMENT: str = "production"
    
    # Rate Limiting
    RATE_LIMIT_REGISTER: str = "5/minute"
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_API: str = "100/minute"
    
    # Trial
    TRIAL_DAYS: int = 2
    MAX_TRIAL_USERS: int = 10
    
    # Admin/VIP credentials (hashed in production)
    ADMIN_EMAIL: str = "admin@crazy-brain.local"
    ADMIN_PASSWORD: str = "ChangeMeNow1!"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Restituisce settings cached"""
    return Settings()


# Costanti sicurezza
PASSWORD_MIN_LENGTH = 8
PASSWORD_REQUIRE_NUMBER = True
PASSWORD_REQUIRE_SYMBOL = True
PASSWORD_REQUIRE_UPPERCASE = True

# Ruoli utente
class UserRole:
    USER = "user"
    VIP = "vip"
    ADMIN = "admin"

# Stati abbonamento
class SubscriptionStatus:
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    NONE = "none"

# VIP users predefiniti
VIP_USERS = {
    "vip1@gmail.com": "vip1-1234",
    "vip2@gmail.com": "vip2-1234",
    "vip3@gmail.com": "vip3-1234",
    "vip4@gmail.com": "vip4-1234",
    "vip5@gmail.com": "vip5-1234",
}
