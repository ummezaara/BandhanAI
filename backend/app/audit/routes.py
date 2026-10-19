"""HTTP routes for tenant audit logs."""

from fastapi import APIRouter, Depends, HTTPException
from backend.auth import get_current_user, get_org_id_for_user
import json

router = APIRouter(prefix="/audit", tags=["audit"])

_pg_pool = None

def set_pg_pool(pool):
    """Inject database connection pool."""
    global _pg_pool
    _pg_pool = pool

def _get_pool():
    if not _pg_pool:
        raise RuntimeError("Database pool not injected")
    return _pg_pool


@router.get("")
async def get_recent_audit_logs(user: dict = Depends(get_current_user)):
    """Retrieve recent security audit logs for current tenant."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    async with pool.connection() as conn:
        res = await conn.execute(
            """
            SELECT log_id, actor, action, details, created_at
            FROM public.audit_logs
            WHERE org_id = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (org_id,)
        )
        rows = await res.fetchall()
        
        logs = []
        for r in rows:
            details = r["details"]
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except Exception:
                    details = {}
            logs.append({
                "log_id": str(r["log_id"]),
                "actor": r["actor"],
                "action": r["action"],
                "details": details,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None
            })
        return {"logs": logs}
