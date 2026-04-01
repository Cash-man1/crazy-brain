"""
API Stripe - Pagamenti e Webhook
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from pydantic import BaseModel
import stripe
import json

from database import get_db, User, AuditLog, get_user_by_id
from security import get_current_user_id, get_client_ip, verify_webhook_signature
from config import get_settings

router = APIRouter(prefix="/stripe", tags=["Stripe Payments"])
settings = get_settings()

# Configura Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


# ============================================================================
# SCHEMAS
# ============================================================================

class CheckoutSessionRequest(BaseModel):
    price_type: str  # "monthly" o "annual"


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str


class PortalSessionResponse(BaseModel):
    portal_url: str


class SubscriptionStatusResponse(BaseModel):
    status: str
    current_period_end: datetime = None
    cancel_at_period_end: bool = False


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def log_audit(db: AsyncSession, user_id: int, action: str, resource: str, details: str = None, ip: str = None):
    """Logga azione audit"""
    audit = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        details=details,
        ip_address=ip
    )
    db.add(audit)
    await db.commit()


def get_price_id(price_type: str) -> str:
    """Restituisce price ID Stripe"""
    if price_type == "monthly":
        return settings.STRIPE_PRICE_MONTHLY
    elif price_type == "annual":
        return settings.STRIPE_PRICE_ANNUAL
    raise ValueError(f"Tipo prezzo non valido: {price_type}")


# ============================================================================
# ROUTES - CHECKOUT
# ============================================================================

@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: Request,
    checkout_data: CheckoutSessionRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Crea sessione checkout Stripe"""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    # Crea o recupera customer Stripe
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": str(user.id), "user_uuid": user.uuid}
        )
        user.stripe_customer_id = customer.id
        await db.commit()
    
    try:
        price_id = get_price_id(checkout_data.price_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Crea sessione checkout
    try:
        checkout_session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=f"{settings.FRONTEND_URL}/dashboard?payment=success",
            cancel_url=f"{settings.FRONTEND_URL}/dashboard?payment=cancelled",
            metadata={
                "user_id": str(user.id),
                "price_type": checkout_data.price_type
            }
        )
        
        await log_audit(
            db, user_id, "CHECKOUT_CREATED", "stripe",
            f"Session {checkout_session.id}, type: {checkout_data.price_type}",
            get_client_ip(request)
        )
        
        return {
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id
        }
        
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/create-portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Crea sessione portal Stripe per gestione abbonamento"""
    user = await get_user_by_id(db, user_id)
    if not user or not user.stripe_customer_id:
        raise HTTPException(status_code=404, detail="Customer Stripe non trovato")
    
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=f"{settings.FRONTEND_URL}/dashboard"
        )
        
        return {"portal_url": portal_session.url}
        
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/subscription-status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Restituisce stato abbonamento"""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    return {
        "status": user.subscription_status,
        "current_period_end": user.subscription_current_period_end,
        "cancel_at_period_end": user.subscription_cancel_at_period_end
    }


# ============================================================================
# WEBHOOK
# ============================================================================

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """
    Webhook Stripe per eventi pagamento.
    CRITICO: Verifica firma webhook per sicurezza.
    """
    payload = await request.body()
    
    # Verifica firma webhook
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Payload non valido")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Firma webhook non valida")
    
    event_type = event["type"]
    data = event["data"]["object"]
    
    # Gestione eventi
    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(db, data)
    
    elif event_type == "invoice.payment_succeeded":
        await _handle_payment_succeeded(db, data)
    
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(db, data)
    
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(db, data)
    
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(db, data)
    
    return {"status": "success"}


async def _handle_checkout_completed(db: AsyncSession, data: dict):
    """Gestisce completamento checkout"""
    user_id = int(data.get("metadata", {}).get("user_id", 0))
    if not user_id:
        return
    
    user = await get_user_by_id(db, user_id)
    if not user:
        return
    
    # Aggiorna customer ID se necessario
    if data.get("customer") and not user.stripe_customer_id:
        user.stripe_customer_id = data["customer"]
    
    await log_audit(
        db, user_id, "CHECKOUT_COMPLETED", "stripe",
        f"Session {data.get('id')}"
    )
    await db.commit()


async def _handle_payment_succeeded(db: AsyncSession, data: dict):
    """Gestisce pagamento riuscito"""
    subscription_id = data.get("subscription")
    if not subscription_id:
        return
    
    # Trova utente per subscription ID
    result = await db.execute(
        select(User).where(User.stripe_subscription_id == subscription_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        # Prova a trovare per customer ID
        customer_id = data.get("customer")
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        user = result.scalar_one_or_none()
    
    if user:
        user.subscription_status = "active"
        user.stripe_subscription_id = subscription_id
        await db.commit()
        
        await log_audit(
            db, user.id, "PAYMENT_SUCCEEDED", "stripe",
            f"Invoice {data.get('id')}"
        )


async def _handle_payment_failed(db: AsyncSession, data: dict):
    """Gestisce pagamento fallito"""
    customer_id = data.get("customer")
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        await log_audit(
            db, user.id, "PAYMENT_FAILED", "stripe",
            f"Invoice {data.get('id')}"
        )


async def _handle_subscription_updated(db: AsyncSession, data: dict):
    """Gestisce aggiornamento abbonamento"""
    subscription_id = data.get("id")
    customer_id = data.get("customer")
    
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        user.stripe_subscription_id = subscription_id
        user.subscription_status = data.get("status", "active")
        
        # Aggiorna periodo
        if data.get("current_period_start"):
            user.subscription_current_period_start = datetime.fromtimestamp(
                data["current_period_start"]
            )
        if data.get("current_period_end"):
            user.subscription_current_period_end = datetime.fromtimestamp(
                data["current_period_end"]
            )
        
        user.subscription_cancel_at_period_end = data.get("cancel_at_period_end", False)
        
        await db.commit()
        
        await log_audit(
            db, user.id, "SUBSCRIPTION_UPDATED", "stripe",
            f"Status: {data.get('status')}"
        )


async def _handle_subscription_deleted(db: AsyncSession, data: dict):
    """Gestisce cancellazione abbonamento"""
    subscription_id = data.get("id")
    
    result = await db.execute(
        select(User).where(User.stripe_subscription_id == subscription_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        user.subscription_status = "cancelled"
        await db.commit()
        
        await log_audit(
            db, user.id, "SUBSCRIPTION_CANCELLED", "stripe",
            f"Subscription {subscription_id}"
        )
