"""Stripe billing routes and tier management."""

from fastapi import APIRouter, Depends, HTTPException
from backend.auth import get_current_user, get_org_id_for_user

router = APIRouter(prefix="/billing", tags=["billing"])

_pg_pool = None

def set_pg_pool(pool):
    """Inject shared psycopg database pool."""
    global _pg_pool
    _pg_pool = pool

def _get_pool():
    if not _pg_pool:
        raise RuntimeError("Database pool not injected")
    return _pg_pool


@router.get("/status")
async def get_billing_status(user: dict = Depends(get_current_user)):
    """Retrieve subscription tier and usage limits for current tenant."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    async with pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT subscription_status, subscription_tier
            FROM public.tenants
            WHERE org_id = %s
            """,
            (org_id,)
        )
        row = await result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tenant details not found")
        
        # Mapped limits per subscription tier
        tier = row["subscription_tier"] or "free"
        limits = {
            "free": {"limit": 100, "features": ["CSV upload only", "1 Agent", "10 Campaigns/mo"]},
            "growth": {"limit": 5000, "features": ["Supabase Connect", "CSV upload", "5 Agents", "Unlimited Campaigns", "Gmail Outreach"]},
            "enterprise": {"limit": 100000, "features": ["All features", "Unlimited Agents", "Dedicated support", "Custom RLS"]},
        }
        
        return {
            "status": row["subscription_status"] or "active",
            "tier": tier,
            "features": limits.get(tier, limits["free"])["features"],
            "limit": limits.get(tier, limits["free"])["limit"]
        }


@router.post("/upgrade")
async def upgrade_billing_tier(req: dict, user: dict = Depends(get_current_user)):
    """Simulate upgrading the billing tier (SaaS Stripe prep integration)."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    tier = req.get("tier", "growth")
    if tier not in ["free", "growth", "enterprise"]:
        raise HTTPException(status_code=400, detail="Invalid subscription tier name")

    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE public.tenants
            SET subscription_tier = %s, subscription_status = 'active'
            WHERE org_id = %s
            """,
            (tier, org_id)
        )
        
    return {
        "success": True,
        "message": f"Successfully updated subscription tier to {tier}.",
        "tier": tier,
        "status": "active"
    }
