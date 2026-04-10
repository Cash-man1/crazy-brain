"""
Crazy Brain SaaS - Main Application
FastAPI backend con sicurezza enterprise-grade
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time
import logging
import sys
import asyncio

from config import get_settings
from database import init_db, AsyncSessionLocal, ensure_default_accounts
from security import limiter
from api_auth import router as auth_router
from api_stripe import router as stripe_router
from api_brain import router as brain_router
from api_brain import start_public_ingestion_loop, stop_public_ingestion_loop
from api_admin import router as admin_router
from api_chat import router as chat_router
from api_notify import router as notify_router
from config import VIP_USERS

settings = get_settings()

# Playwright su Windows richiede Proactor event loop per subprocess.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Crazy Brain SaaS...")
    
    await init_db()
    logger.info("Database initialized")

    async def _ensure_defaults_background() -> None:
        try:
            async with AsyncSessionLocal() as db:
                await ensure_default_accounts(
                    db,
                    admin_email=settings.ADMIN_EMAIL,
                    admin_password=settings.ADMIN_PASSWORD,
                    vip_users=VIP_USERS,
                )
            logger.info("Default accounts ensured")
        except Exception:
            logger.exception("Failed ensuring default accounts")

    # Do not block startup on default-account bootstrap; keeps Render port detection stable.
    asyncio.create_task(_ensure_defaults_background())

    logger.info("Application started successfully!")

    # Start live ingestion in background (Render/prod).
    try:
        start_public_ingestion_loop()
        logger.info("Public ingestion loop started")
    except Exception:
        logger.exception("Failed starting ingestion loop")
    
    yield
    
    logger.info("Shutting down...")
    try:
        await stop_public_ingestion_loop()
    except Exception:
        pass


app = FastAPI(
    title="Crazy Brain SaaS API",
    description="API per Crazy Time Analysis Tool - Sicurezza Enterprise",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan
)

app.state.limiter = limiter


# ================= SECURITY HEADERS =================

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://js.stripe.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src *; "
        "frame-src https://js.stripe.com https://hooks.stripe.com https://checkout.stripe.com; "
        "form-action 'self'; "
        "base-uri 'self';"
    )
    
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
        "magnetometer=(), microphone=(), payment=(), usb=()"
    )
    
    return response


# ================= CORS =================

def _split_csv(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]

cors_origins = [settings.FRONTEND_URL, "http://localhost:5173"]
cors_origins += _split_csv(getattr(settings, "CORS_EXTRA_ORIGINS", ""))
cors_origins = list(dict.fromkeys([o for o in cors_origins if o]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================= TRUSTED HOST =================

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_split_csv(getattr(settings, "ALLOWED_HOSTS", "*")) or ["*"]
)


# ================= LOGGING =================

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time.time()
    
    request_id = request.headers.get("X-Request-ID", "unknown")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} - "
        f"{process_time:.3f}s - {request_id}"
    )
    
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


# ================= ERROR HANDLERS =================

@app.exception_handler(429)
async def rate_limit_handler(request: Request, exc):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "Rate limit exceeded",
            "message": "Troppe richieste. Riprova più tardi.",
            "retry_after": 60
        },
        headers={"Retry-After": "60"}
    )


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    detail = getattr(exc, 'detail', {})
    
    if isinstance(detail, dict):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=detail
        )
    
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "message": "Accesso negato",
            "can_access": False
        }
    )


# ================= ROUTES =================

@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {
        "name": "Crazy Brain SaaS API",
        "version": "1.0.0",
        "status": "operational",
        "environment": settings.ENVIRONMENT
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "database": "connected",
            "api": "operational"
        }
    }


app.include_router(auth_router, prefix="/api")
app.include_router(stripe_router, prefix="/api")
app.include_router(brain_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(notify_router, prefix="/api")


# ================= START =================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
    )