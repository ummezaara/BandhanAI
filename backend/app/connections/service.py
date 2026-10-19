"""Service layer for tenant-owned Supabase connections."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from backend.app.connections.schemas import ConnectionHealth
from backend.encryption import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            return []
    return []


def serialize_connection(row: dict) -> dict:
    """Convert a DB row into a safe API shape with no credentials."""
    return {
        "connection_id": str(row["connection_id"]),
        "org_id": str(row["org_id"]),
        "provider": row.get("provider", "supabase"),
        "display_name": row.get("display_name", ""),
        "project_url": row.get("project_url"),
        "default_schema": row.get("default_schema", "public"),
        "allowed_schemas": _json_list(row.get("allowed_schemas")),
        "allowed_tables": _json_list(row.get("allowed_tables")),
        "status": row.get("status", "pending"),
        "last_health_check_at": row["last_health_check_at"].isoformat()
        if row.get("last_health_check_at")
        else None,
        "last_error": row.get("last_error"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def validate_connection_uri(readonly_uri: str) -> list[str]:
    """Return warnings for suspicious connection strings."""
    parsed = urlparse(readonly_uri)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("Connection string must start with postgres:// or postgresql://")

    if not parsed.hostname:
        raise ValueError("Connection string is missing a database host")

    warnings: list[str] = []
    username = (parsed.username or "").lower()
    if username in {"postgres", "supabase_admin"} or "service_role" in username:
        warnings.append(
            "This looks like a privileged database user. Create a dedicated read-only role before production use."
        )
    if not parsed.password:
        warnings.append("Connection string does not include a password.")
    if parsed.hostname and "supabase" not in parsed.hostname.lower():
        warnings.append("Host does not look like a Supabase host; continuing as a Postgres-compatible connection.")
    return warnings


async def test_supabase_connection(readonly_uri: str, default_schema: str = "public") -> ConnectionHealth:
    """Validate that a tenant external DB is reachable and readable."""
    warnings = validate_connection_uri(readonly_uri)

    try:
        async with await psycopg.AsyncConnection.connect(
            readonly_uri,
            connect_timeout=8,
            autocommit=True,
            row_factory=dict_row,
        ) as conn:
            await conn.execute("SET default_transaction_read_only = on")
            info_result = await conn.execute(
                """
                SELECT
                    current_user AS current_user,
                    current_database() AS database,
                    has_schema_privilege(current_user, %s, 'USAGE') AS can_use_schema,
                    has_schema_privilege(current_user, %s, 'CREATE') AS can_create_in_schema
                """,
                (default_schema, default_schema),
            )
            info = await info_result.fetchone()

            if not info or not info["can_use_schema"]:
                return ConnectionHealth(
                    ok=False,
                    status="failed",
                    message=f"Connected, but user cannot use schema '{default_schema}'.",
                    database=info.get("database") if info else None,
                    current_user=info.get("current_user") if info else None,
                    default_schema=default_schema,
                    warnings=warnings,
                )

            count_result = await conn.execute(
                """
                SELECT COUNT(*) AS table_count
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type IN ('BASE TABLE', 'VIEW')
                """,
                (default_schema,),
            )
            count_row = await count_result.fetchone()

            if info.get("can_create_in_schema"):
                warnings.append(
                    f"User has CREATE privilege on schema '{default_schema}'. Prefer a stricter read-only role."
                )

            return ConnectionHealth(
                ok=True,
                status="connected",
                message="Connection verified with read access.",
                database=info["database"],
                current_user=info["current_user"],
                default_schema=default_schema,
                table_count=int(count_row["table_count"] if count_row else 0),
                warnings=warnings,
            )
    except Exception as exc:
        logger.warning("Tenant Supabase connection test failed: %s", exc)
        return ConnectionHealth(
            ok=False,
            status="failed",
            message=str(exc),
            default_schema=default_schema,
            warnings=warnings,
        )


async def list_connections(pg_pool, org_id: str) -> list[dict]:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT *
            FROM tenant_data_connections
            WHERE org_id = %s
            ORDER BY created_at DESC
            """,
            (org_id,),
        )
        rows = await result.fetchall()
    return [serialize_connection(dict(row)) for row in rows]


async def save_connection(
    pg_pool,
    org_id: str,
    display_name: str,
    readonly_uri: str,
    project_url: str | None,
    default_schema: str,
    allowed_schemas: list[str],
    allowed_tables: list[str],
) -> tuple[dict, ConnectionHealth]:
    health = await test_supabase_connection(readonly_uri, default_schema)
    encrypted_uri = encrypt_token(readonly_uri)
    now = _utcnow()

    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            INSERT INTO tenant_data_connections (
                org_id,
                provider,
                display_name,
                project_url,
                encrypted_readonly_uri,
                default_schema,
                allowed_schemas,
                allowed_tables,
                status,
                last_health_check_at,
                last_error,
                created_at,
                updated_at
            )
            VALUES (%s, 'supabase', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                org_id,
                display_name,
                project_url,
                encrypted_uri,
                default_schema,
                json.dumps(allowed_schemas or ["public"]),
                json.dumps(allowed_tables or []),
                health.status,
                now,
                None if health.ok else health.message,
                now,
                now,
            ),
        )
        row = await result.fetchone()

    return serialize_connection(dict(row)), health


async def delete_connection(pg_pool, org_id: str, connection_id: str) -> bool:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            DELETE FROM tenant_data_connections
            WHERE org_id = %s AND connection_id = %s
            RETURNING connection_id
            """,
            (org_id, connection_id),
        )
        row = await result.fetchone()
    return bool(row)


async def health_check_connection(pg_pool, org_id: str, connection_id: str) -> ConnectionHealth:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT encrypted_readonly_uri, default_schema
            FROM tenant_data_connections
            WHERE org_id = %s AND connection_id = %s
            """,
            (org_id, connection_id),
        )
        row = await result.fetchone()

    if not row:
        raise LookupError("Connection not found")

    readonly_uri = decrypt_token(row["encrypted_readonly_uri"])
    health = await test_supabase_connection(readonly_uri, row["default_schema"])

    async with pg_pool.connection() as conn:
        await conn.execute(
            """
            UPDATE tenant_data_connections
            SET status = %s,
                last_health_check_at = %s,
                last_error = %s,
                updated_at = %s
            WHERE org_id = %s AND connection_id = %s
            """,
            (
                health.status,
                _utcnow(),
                None if health.ok else health.message,
                _utcnow(),
                org_id,
                connection_id,
            ),
        )

    return health
