"""Service functions for tenant audit logs."""

import json
import logging

logger = logging.getLogger(__name__)


async def insert_audit_action(conn, org_id: str, actor: str, action: str, details: dict | None = None):
    """Write an audit event using the caller's connection and transaction."""
    await conn.execute(
        """
        INSERT INTO public.audit_logs (org_id, actor, action, details)
        VALUES (%s, %s, %s, %s)
        """,
        (org_id, actor, action, json.dumps(details or {})),
    )


async def log_audit_action(pool, org_id: str, actor: str, action: str, details: dict = None):
    """Insert a security/action log into audit logs table."""
    try:
        async with pool.connection() as conn:
            await insert_audit_action(conn, org_id, actor, action, details)
    except Exception as e:
        logger.error(f"Failed to write audit log [{action}]: {e}")
