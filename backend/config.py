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
    # Opzionale: Redis (Render Redis, Upstash, ecc.) per cache JSON /auto-brain-public fuori dalla RAM del web service.
    REDIS_URL: str = ""
    
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
    # Origini extra per CORS (es. sito statico Render), separate da virgola.
    # Default: frontend Render; sovrascrivibile da env.
    CORS_EXTRA_ORIGINS: str = "https://crazy-brain-web.onrender.com"
    # Trusted hosts (CSV). In prod evita "*" (es. "api.crazy-brain.it,localhost,127.0.0.1,*.onrender.com")
    ALLOWED_HOSTS: str = "*"
    ENVIRONMENT: str = "production"

    # Notifiche segnali (Telegram / WhatsApp)
    NOTIFY_SIGNALS_ENABLED: bool = False
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""
    # Lista chat id separati da virgola (es. "12345678,-1001234567890")
    TELEGRAM_CHAT_IDS: str = ""
    TELEGRAM_WEBHOOK_SECRET_TOKEN: str = ""
    # Se true e TELEGRAM_WEBHOOK_SECRET_TOKEN è valorizzato: Telegram deve inviare
    # X-Telegram-Bot-Api-Secret-Token (setWebhook con secret_token). Se false, header
    # assente è accettato (utile se il webhook è stato registrato senza secret).
    TELEGRAM_WEBHOOK_STRICT_SECRET: bool = False
    # Soglia minima confidence per invio (0-1)
    NOTIFY_MIN_CONFIDENCE: float = 0.45
    # Solo per TELEGRAM_CHAT_IDS (broadcast .env): CSV segmenti da notificare; vuoto = tutti
    NOTIFY_BROADCAST_SEGMENTS: str = ""
    
    # Rate Limiting
    RATE_LIMIT_REGISTER: str = "5/minute"
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_API: str = "100/minute"
    
    # Trial
    TRIAL_DAYS: int = 2
    MAX_TRIAL_USERS: int = 10
    
    # Admin/VIP seed (solo se valorizzati in .env — niente password di default nel repo)
    ADMIN_EMAIL: str = "admin@crazy-brain.local"
    ADMIN_PASSWORD: str = ""
    # Opzionale: crea/aggiorna admin con login POST /api/auth/phone/login (numero + password).
    # Imposta su Render (non committare la password nel repo).
    ADMIN_PHONE_NUMBER: str = ""
    ADMIN_PHONE_PASSWORD: str = ""
    
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

# VIP seed opzionale: solo email presenti in questo dict, con password in chiaro SOLO in .env
# (es. export/import da variabile d'ambiente JSON in futuro). Repo pubblico: dict vuoto.
VIP_USERS: dict[str, str] = {}
