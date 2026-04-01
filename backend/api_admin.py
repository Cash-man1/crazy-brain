"""
Admin API: stats e gestione utenti.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, get_db, get_user_by_id
from security import get_current_user_id

router = APIRouter(prefix="/admin", tags=["Admin"])


async def require_admin(user_id: int, db: AsyncSession) -> User:
    user = await get_user_by_id(db, user_id)
    if not user or user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accesso admin richiesto",
        )
    return user


@router.get("/stats")
async def get_admin_stats(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await require_admin(user_id, db)

    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    vip_users = (
        await db.execute(select(func.count(User.id)).where(User.role == "vip"))
    ).scalar() or 0
    active_trials = (
        await db.execute(
            select(func.count(User.id)).where(
                User.subscription_status == "trial",
                User.is_active == True,
            )
        )
    ).scalar() or 0
    paid_users = (
        await db.execute(
            select(func.count(User.id)).where(
                User.subscription_status == "active",
                User.role == "user",
            )
        )
    ).scalar() or 0

    return {
        "total_users": total_users,
        "vip_users": vip_users,
        "active_trials": active_trials,
        "paid_users": paid_users,
    }


@router.get("/users")
async def list_users(
    limit: int = 100,
    offset: int = 0,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await require_admin(user_id, db)

    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()
    return {
        "users": [u.to_dict() for u in users],
        "limit": limit,
        "offset": offset,
    }
