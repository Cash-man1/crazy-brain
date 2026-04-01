"""
Sicurezza: autenticazione, password, JWT, rate limiting
"""
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import re
import secrets
import hashlib
import hmac
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import get_settings, PASSWORD_MIN_LENGTH, PASSWORD_REQUIRE_NUMBER, PASSWORD_REQUIRE_SYMBOL, PASSWORD_REQUIRE_UPPERCASE

settings = get_settings()

# Password hashing con bcrypt
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12  # Cost factor 12 per sicurezza
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Security scheme
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica password con bcrypt"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash password con bcrypt"""
    return pwd_context.hash(password)


def validate_password(password: str) -> Dict[str, Any]:
    """
    Valida password secondo policy sicurezza
    """
    errors = []
    
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Password deve essere di almeno {PASSWORD_MIN_LENGTH} caratteri")
    
    if PASSWORD_REQUIRE_NUMBER and not re.search(r'\d', password):
        errors.append("Password deve contenere almeno un numero")
    
    if PASSWORD_REQUIRE_SYMBOL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password deve contenere almeno un simbolo (!@#$%^&*...)")
    
    if PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
        errors.append("Password deve contenere almeno una lettera maiuscola")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Crea JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Crea JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict]:
    """Decodifica e valida JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def generate_secure_token(length: int = 32) -> str:
    """Genera token sicuro casuale"""
    return secrets.token_urlsafe(length)


def generate_password_reset_token() -> str:
    """Genera token per reset password"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash token per storage sicuro"""
    return hashlib.sha256(token.encode()).hexdigest()


def sanitize_input(text: str) -> str:
    """Sanitizza input per prevenire XSS"""
    if not text:
        return ""
    # Rimuovi tag HTML
    text = re.sub(r'<[^>]+>', '', text)
    # Escape caratteri speciali
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#x27;')
    return text.strip()


def get_client_ip(request: Request) -> str:
    """Estrae IP client da request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verifica firma webhook Stripe"""
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


async def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """Dependency per ottenere user_id da JWT"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token mancante",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(credentials.credentials)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token non valido o scaduto",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token type non valido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token senza user_id",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return int(user_id)


class SecurityHeaders:
    """Middleware per aggiungere header di sicurezza"""
    
    @staticmethod
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        
        # Prevenire clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Prevenire MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # XSS Protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Strict Transport Security (HTTPS only)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://js.stripe.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self' https://api.stripe.com; "
            "frame-src https://js.stripe.com https://hooks.stripe.com;"
        )
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions Policy
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        return response


# Rate limit key functions
def get_rate_limit_key(request: Request) -> str:
    """Chiave per rate limiting per IP + endpoint"""
    ip = get_client_ip(request)
    endpoint = request.url.path
    return f"{ip}:{endpoint}"


def get_auth_rate_limit_key(request: Request) -> str:
    """Chiave per rate limiting auth per IP"""
    return get_client_ip(request)
