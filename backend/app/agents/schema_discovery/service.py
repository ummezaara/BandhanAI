"""Schema discovery workflow for tenant-owned Postgres databases."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from backend.app.agents.schema_discovery.classifier import (
    canonical_column_name,
    classify_tables,
)
from backend.app.connections.metadata import upsert_schema_metadata
from backend.app.connections.service import _json_list
from backend.encryption import decrypt_token


async def run_schema_discovery(pg_pool, org_id: str, connection_id: str) -> dict:
    connection = await _fetch_connection(pg_pool, org_id, connection_id)
    allowed_schemas = _json_list(connection.get("allowed_schemas")) or [connection.get("default_schema", "public")]
    readonly_uri = decrypt_token(connection["encrypted_readonly_uri"])
    errors: list[str] = []

    async with await psycopg.AsyncConnection.connect(
        readonly_uri,
        connect_timeout=8,
        autocommit=True,
        row_factory=dict_row,
    ) as ext_conn:
        await ext_conn.execute("SET default_transaction_read_only = on")
        tables = await _load_tables(ext_conn, allowed_schemas)
        raw_columns = await _load_columns(ext_conn, allowed_schemas)
        foreign_keys = await _load_foreign_keys(ext_conn, allowed_schemas)
        row_estimates = await _load_row_estimates(ext_conn, allowed_schemas)

    table_catalog = _build_table_catalog(tables, raw_columns, row_estimates)
    column_catalog = _build_column_catalog(raw_columns)
    join_paths = _build_join_paths(foreign_keys)
    entity_map, confidence = classify_tables(table_catalog, column_catalog, join_paths)

    if not table_catalog:
        errors.append("No tables or views were found in the allowed schemas.")
    if not entity_map:
        errors.append("No CRM-like entities could be confidently classified.")

    return await upsert_schema_metadata(
        pg_pool=pg_pool,
        org_id=org_id,
        connection_id=connection_id,
        entity_map=entity_map,
        column_catalog=column_catalog,
        join_paths=join_paths,
        table_catalog=table_catalog,
        confidence=confidence,
        errors=errors,
    )


async def _fetch_connection(pg_pool, org_id: str, connection_id: str) -> dict:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT *
            FROM public.tenant_data_connections
            WHERE org_id = %s AND connection_id = %s AND status != 'disabled'
            """,
            (org_id, connection_id),
        )
        row = await result.fetchone()
    if not row:
        raise LookupError("Connection not found")
    return dict(row)


async def _load_tables(ext_conn, allowed_schemas: list[str]) -> list[dict]:
    result = await ext_conn.execute(
        """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = ANY(%s)
          AND table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY table_schema, table_name
        """,
        (allowed_schemas,),
    )
    return [dict(row) for row in await result.fetchall()]


async def _load_columns(ext_conn, allowed_schemas: list[str]) -> list[dict]:
    result = await ext_conn.execute(
        """
        SELECT table_schema, table_name, column_name, data_type, is_nullable, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = ANY(%s)
        ORDER BY table_schema, table_name, ordinal_position
        """,
        (allowed_schemas,),
    )
    return [dict(row) for row in await result.fetchall()]


async def _load_foreign_keys(ext_conn, allowed_schemas: list[str]) -> list[dict]:
    result = await ext_conn.execute(
        """
        SELECT
            tc.table_schema AS from_schema,
            tc.table_name AS from_table,
            kcu.column_name AS from_column,
            ccu.table_schema AS to_schema,
            ccu.table_name AS to_table,
            ccu.column_name AS to_column,
            tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = ANY(%s)
        ORDER BY tc.table_schema, tc.table_name, kcu.column_name
        """,
        (allowed_schemas,),
    )
    return [dict(row) for row in await result.fetchall()]


async def _load_row_estimates(ext_conn, allowed_schemas: list[str]) -> dict[str, int]:
    result = await ext_conn.execute(
        """
        SELECT n.nspname AS schema_name, c.relname AS table_name, COALESCE(c.reltuples::bigint, 0) AS row_estimate
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = ANY(%s)
          AND c.relkind IN ('r', 'v', 'm')
        """,
        (allowed_schemas,),
    )
    rows = await result.fetchall()
    return {f"{row['schema_name']}.{row['table_name']}": int(row["row_estimate"] or 0) for row in rows}


def _build_table_catalog(tables: list[dict], columns: list[dict], row_estimates: dict[str, int]) -> list[dict]:
    column_counts: dict[str, int] = {}
    for col in columns:
        table_key = f"{col['table_schema']}.{col['table_name']}"
        column_counts[table_key] = column_counts.get(table_key, 0) + 1

    return [
        {
            "schema": table["table_schema"],
            "name": table["table_name"],
            "table": f"{table['table_schema']}.{table['table_name']}",
            "type": table["table_type"],
            "row_estimate": row_estimates.get(f"{table['table_schema']}.{table['table_name']}", 0),
            "column_count": column_counts.get(f"{table['table_schema']}.{table['table_name']}", 0),
        }
        for table in tables
    ]


def _build_column_catalog(columns: list[dict]) -> list[dict]:
    catalog = []
    for col in columns:
        catalog.append(
            {
                "schema": col["table_schema"],
                "table_name": col["table_name"],
                "table": f"{col['table_schema']}.{col['table_name']}",
                "column": col["column_name"],
                "data_type": col["data_type"],
                "is_nullable": col["is_nullable"],
                "ordinal_position": col["ordinal_position"],
                "canonical_name": canonical_column_name(col["column_name"]),
            }
        )
    return catalog


def _build_join_paths(foreign_keys: list[dict]) -> list[dict]:
    return [
        {
            "from_table": f"{fk['from_schema']}.{fk['from_table']}",
            "from_col": fk["from_column"],
            "to_table": f"{fk['to_schema']}.{fk['to_table']}",
            "to_col": fk["to_column"],
            "constraint_name": fk["constraint_name"],
        }
        for fk in foreign_keys
    ]
