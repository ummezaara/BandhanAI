"""Schema metadata cache helpers for tenant-owned data connections."""

from __future__ import annotations

import json
from typing import Any


def _parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def serialize_schema_metadata(row: dict | None) -> dict | None:
    """Convert a schema metadata DB row into an API/prompt-safe shape."""
    if not row:
        return None

    return {
        "metadata_id": str(row["metadata_id"]),
        "org_id": str(row["org_id"]),
        "connection_id": str(row["connection_id"]),
        "entity_map": _parse_json(row.get("entity_map"), {}),
        "column_catalog": _parse_json(row.get("column_catalog"), []),
        "join_paths": _parse_json(row.get("join_paths"), []),
        "table_catalog": _parse_json(row.get("table_catalog"), []),
        "confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
        "errors": _parse_json(row.get("errors"), []),
        "discovered_at": row["discovered_at"].isoformat() if row.get("discovered_at") else None,
    }


async def get_schema_metadata(pg_pool, org_id: str, connection_id: str) -> dict | None:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT *
            FROM public.schema_metadata_cache
            WHERE org_id = %s AND connection_id = %s
            """,
            (org_id, connection_id),
        )
        row = await result.fetchone()
    return serialize_schema_metadata(dict(row)) if row else None


async def get_latest_schema_metadata(pg_pool, org_id: str) -> dict | None:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT sm.*
            FROM public.schema_metadata_cache sm
            JOIN public.tenant_data_connections c
              ON c.connection_id = sm.connection_id
             AND c.org_id = sm.org_id
            WHERE sm.org_id = %s
              AND c.status = 'connected'
            ORDER BY sm.discovered_at DESC
            LIMIT 1
            """,
            (org_id,),
        )
        row = await result.fetchone()
    return serialize_schema_metadata(dict(row)) if row else None


async def upsert_schema_metadata(
    pg_pool,
    org_id: str,
    connection_id: str,
    entity_map: dict,
    column_catalog: list[dict],
    join_paths: list[dict],
    table_catalog: list[dict],
    confidence: float | None,
    errors: list[str] | None = None,
) -> dict:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            INSERT INTO public.schema_metadata_cache (
                org_id,
                connection_id,
                entity_map,
                column_catalog,
                join_paths,
                table_catalog,
                confidence,
                errors,
                discovered_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (org_id, connection_id)
            DO UPDATE SET
                entity_map = EXCLUDED.entity_map,
                column_catalog = EXCLUDED.column_catalog,
                join_paths = EXCLUDED.join_paths,
                table_catalog = EXCLUDED.table_catalog,
                confidence = EXCLUDED.confidence,
                errors = EXCLUDED.errors,
                discovered_at = now()
            RETURNING *
            """,
            (
                org_id,
                connection_id,
                json.dumps(entity_map),
                json.dumps(column_catalog, default=str),
                json.dumps(join_paths, default=str),
                json.dumps(table_catalog, default=str),
                confidence,
                json.dumps(errors or []),
            ),
        )
        row = await result.fetchone()
    return serialize_schema_metadata(dict(row))
