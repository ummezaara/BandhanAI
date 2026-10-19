"""Customer table discovery for tenant-owned Supabase connections."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from backend.app.connections.service import _json_list
from backend.encryption import decrypt_token

logger = logging.getLogger(__name__)

EDITABLE_CUSTOMER_FIELDS = {
    "customer_id",
    "name",
    "email",
    "phone",
    "total_spend",
    "total_orders",
    "last_purchase",
    "churn_risk",
    "feedback_score",
}

CUSTOMER_FIELD_ALIASES: dict[str, set[str]] = {
    "customer_id": {"customer_id", "customerid", "client_id", "user_id", "account_id", "id"},
    "name": {"name", "full_name", "fullname", "customer_name", "display_name"},
    "first_name": {"first_name", "firstname", "given_name"},
    "last_name": {"last_name", "lastname", "surname", "family_name"},
    "email": {"email", "email_address", "emailaddress", "customer_email"},
    "phone": {"phone", "phone_number", "phonenumber", "mobile", "mobile_number", "contact_number"},
    "region": {"region", "city", "state", "country", "location", "address_city"},
    "last_purchase": {"last_purchase", "last_purchase_at", "last_order_at", "last_seen", "last_seen_at"},
    "total_spend": {"total_spend", "lifetime_value", "ltv", "total_revenue", "amount_spent"},
    "feedback_score": {"feedback_score", "rating", "satisfaction_score", "nps"},
    "churn_risk": {"churn_risk", "risk_score", "churn_score", "at_risk"},
    "created_at": {"created_at", "created", "joined_at", "signup_at", "registered_at"},
    "updated_at": {"updated_at", "modified_at"},
}

REQUIRED_CUSTOMER_FIELDS = {"email", "phone", "name"}
SENSITIVE_CANONICAL_FIELDS = {"email", "phone", "name", "first_name", "last_name"}


@dataclass
class TableCandidate:
    schema_name: str
    table_name: str
    columns: list[dict[str, Any]]
    row_estimate: int
    field_map: dict[str, dict[str, Any]]
    safe_preview: list[dict[str, Any]]
    confidence: float
    reasoning: str
    missing_fields: list[str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_identifier(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _canonical_for_column(column_name: str) -> tuple[str | None, float, str]:
    normalized = _normalize_identifier(column_name)
    compact = normalized.replace("_", "")

    for canonical, aliases in CUSTOMER_FIELD_ALIASES.items():
        if normalized in aliases or compact in aliases:
            return canonical, 0.95, f"Column name matches common {canonical} alias."

    if "email" in normalized:
        return "email", 0.9, "Column name contains email."
    if "phone" in normalized or "mobile" in normalized:
        return "phone", 0.85, "Column name contains phone/mobile."
    if normalized.endswith("_name") and "company" not in normalized:
        return "name", 0.72, "Column appears to contain a person/customer name."
    if "customer" in normalized and normalized.endswith("id"):
        return "customer_id", 0.78, "Column appears to identify a customer."

    return None, 0.0, ""


def _score_table(table_name: str, columns: list[dict[str, Any]], row_estimate: int) -> tuple[float, str, dict[str, dict[str, Any]], list[str]]:
    normalized_table = _normalize_identifier(table_name)
    score = 0.0
    reasons: list[str] = []
    field_map: dict[str, dict[str, Any]] = {}

    if any(token in normalized_table for token in ["customer", "customers", "client", "clients", "user", "users"]):
        score += 0.25
        reasons.append("table name looks customer-like")

    if row_estimate > 0:
        score += 0.05
        reasons.append("table has estimated rows")

    canonical_seen: set[str] = set()
    for col in columns:
        canonical, confidence, reason = _canonical_for_column(col["column_name"])
        if not canonical:
            continue
        if canonical in canonical_seen:
            continue
        canonical_seen.add(canonical)
        field_map[col["column_name"]] = {
            "source_column": col["column_name"],
            "canonical_field": canonical,
            "confidence": confidence,
            "reason": reason,
        }

        if canonical == "email":
            score += 0.3
            reasons.append("has email field")
        elif canonical == "phone":
            score += 0.18
            reasons.append("has phone field")
        elif canonical in {"name", "first_name", "last_name"}:
            score += 0.12
            reasons.append("has customer name field")
        elif canonical == "customer_id":
            score += 0.08
            reasons.append("has customer identifier")
        else:
            score += 0.03

    available = {v["canonical_field"] for v in field_map.values()}
    missing = sorted(REQUIRED_CUSTOMER_FIELDS - available)
    confidence = min(score, 0.99)

    if not reasons:
        reasons.append("no strong customer signals found")

    return confidence, "; ".join(dict.fromkeys(reasons)), field_map, missing


def _safe_value(value: Any, canonical_field: str | None) -> Any:
    if value is None:
        return None
    if canonical_field in SENSITIVE_CANONICAL_FIELDS:
        text = str(value)
        if canonical_field == "email" and "@" in text:
            name, domain = text.split("@", 1)
            return f"{name[:2]}***@{domain}"
        if canonical_field == "phone":
            return f"***{text[-4:]}" if len(text) >= 4 else "***"
        if canonical_field in {"name", "first_name", "last_name"}:
            return f"{text[:1]}***" if text else None
    return value


async def _fetch_connection(pg_pool, org_id: str, connection_id: str) -> dict:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT *
            FROM tenant_data_connections
            WHERE org_id = %s AND connection_id = %s AND status != 'disabled'
            """,
            (org_id, connection_id),
        )
        row = await result.fetchone()
    if not row:
        raise LookupError("Connection not found")
    return dict(row)


async def _load_table_catalog(ext_conn, allowed_schemas: list[str]) -> list[dict[str, Any]]:
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


async def _load_columns(ext_conn, schema_name: str, table_name: str) -> list[dict[str, Any]]:
    result = await ext_conn.execute(
        """
        SELECT column_name, data_type, is_nullable, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema_name, table_name),
    )
    return [dict(row) for row in await result.fetchall()]


async def _estimate_rows(ext_conn, schema_name: str, table_name: str) -> int:
    result = await ext_conn.execute(
        """
        SELECT COALESCE(c.reltuples::bigint, 0) AS row_estimate
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relname = %s
        """,
        (schema_name, table_name),
    )
    row = await result.fetchone()
    return int(row["row_estimate"] if row else 0)


async def _safe_sample(
    ext_conn,
    schema_name: str,
    table_name: str,
    field_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not field_map:
        return []

    source_columns = list(field_map.keys())[:8]
    query = sql.SQL("SELECT {} FROM {}.{} LIMIT 3").format(
        sql.SQL(", ").join(sql.Identifier(col) for col in source_columns),
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
    )
    result = await ext_conn.execute(query)
    rows = await result.fetchall()

    preview: list[dict[str, Any]] = []
    for row in rows:
        safe_row = {}
        for col in source_columns:
            canonical = field_map[col]["canonical_field"]
            safe_row[col] = _safe_value(row.get(col), canonical)
        preview.append(safe_row)
    return preview


def _serialize_mapping(row: dict) -> dict:
    def parse(value, default):
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return value

    return {
        "mapping_id": str(row["mapping_id"]),
        "org_id": str(row["org_id"]),
        "connection_id": str(row["connection_id"]),
        "schema_name": row["schema_name"],
        "table_name": row["table_name"],
        "status": row["status"],
        "field_map": parse(row["field_map"], {}),
        "confidence": float(row["confidence"] or 0),
        "reasoning": row.get("reasoning") or "",
        "safe_preview": parse(row.get("safe_preview"), []),
        "missing_fields": parse(row.get("missing_fields"), []),
        "approved_by": str(row["approved_by"]) if row.get("approved_by") else None,
        "approved_at": row["approved_at"].isoformat() if row.get("approved_at") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


async def _persist_candidates(pg_pool, org_id: str, connection_id: str, candidates: list[TableCandidate]) -> list[dict]:
    saved: list[dict] = []
    async with pg_pool.connection() as conn:
        await conn.execute(
            """
            UPDATE crm_customer_mappings
            SET status = 'superseded', updated_at = %s
            WHERE org_id = %s AND connection_id = %s AND status = 'draft'
            """,
            (_utcnow(), org_id, connection_id),
        )

        for candidate in candidates:
            result = await conn.execute(
                """
                INSERT INTO crm_customer_mappings (
                    org_id,
                    connection_id,
                    schema_name,
                    table_name,
                    status,
                    field_map,
                    confidence,
                    reasoning,
                    safe_preview,
                    missing_fields,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, 'draft', %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    org_id,
                    connection_id,
                    candidate.schema_name,
                    candidate.table_name,
                    json.dumps(candidate.field_map),
                    candidate.confidence,
                    candidate.reasoning,
                    json.dumps(candidate.safe_preview, default=str),
                    json.dumps(candidate.missing_fields),
                    _utcnow(),
                    _utcnow(),
                ),
            )
            saved.append(_serialize_mapping(dict(await result.fetchone())))
    return saved


async def discover_customer_tables(pg_pool, org_id: str, connection_id: str) -> dict:
    connection = await _fetch_connection(pg_pool, org_id, connection_id)
    allowed_schemas = _json_list(connection.get("allowed_schemas")) or [connection.get("default_schema", "public")]
    readonly_uri = decrypt_token(connection["encrypted_readonly_uri"])

    candidates: list[TableCandidate] = []
    async with await psycopg.AsyncConnection.connect(
        readonly_uri,
        connect_timeout=8,
        autocommit=True,
        row_factory=dict_row,
    ) as ext_conn:
        await ext_conn.execute("SET default_transaction_read_only = on")
        tables = await _load_table_catalog(ext_conn, allowed_schemas)

        for table in tables:
            schema_name = table["table_schema"]
            table_name = table["table_name"]
            columns = await _load_columns(ext_conn, schema_name, table_name)
            row_estimate = await _estimate_rows(ext_conn, schema_name, table_name)
            confidence, reasoning, field_map, missing = _score_table(table_name, columns, row_estimate)
            if confidence < 0.35:
                continue
            safe_preview = await _safe_sample(ext_conn, schema_name, table_name, field_map)
            candidates.append(
                TableCandidate(
                    schema_name=schema_name,
                    table_name=table_name,
                    columns=columns,
                    row_estimate=row_estimate,
                    field_map=field_map,
                    safe_preview=safe_preview,
                    confidence=round(confidence, 2),
                    reasoning=f"{reasoning}. Estimated rows: {row_estimate}.",
                    missing_fields=missing,
                )
            )

    candidates.sort(key=lambda item: item.confidence, reverse=True)
    saved = await _persist_candidates(pg_pool, org_id, connection_id, candidates[:5])
    return {"mapping": saved[0] if saved else None, "candidates": saved}


async def get_latest_customer_mapping(pg_pool, org_id: str, connection_id: str) -> dict | None:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT *
            FROM crm_customer_mappings
            WHERE org_id = %s
              AND connection_id = %s
              AND status IN ('approved', 'draft')
            ORDER BY
              CASE status WHEN 'approved' THEN 0 ELSE 1 END,
              created_at DESC
            LIMIT 1
            """,
            (org_id, connection_id),
        )
        row = await result.fetchone()
    return _serialize_mapping(dict(row)) if row else None


def _apply_field_assignments(
    field_map: dict,
    field_assignments: dict[str, str | None],
    available_columns: set[str],
) -> dict:
    updated = dict(field_map)
    requested_fields = {
        canonical_field
        for canonical_field in field_assignments.values()
        if canonical_field is not None
    }
    for source_column, field in list(updated.items()):
        if (
            isinstance(field, dict)
            and field.get("canonical_field") in requested_fields
            and source_column not in field_assignments
        ):
            updated.pop(source_column)

    for source_column, canonical_field in field_assignments.items():
        if source_column not in available_columns:
            raise ValueError(f"Source column is not present in the selected customer table: {source_column}")
        if canonical_field is None:
            updated.pop(source_column, None)
            continue
        if canonical_field not in EDITABLE_CUSTOMER_FIELDS:
            raise ValueError(f"Unsupported customer field: {canonical_field}")
        normalized_column = source_column.strip().lower().replace("-", "_").replace(" ", "_")
        if canonical_field == "last_purchase" and normalized_column in {"created_at", "updated_at"}:
            raise ValueError("created_at and updated_at cannot be assigned to last_purchase.")
        updated[source_column] = {
            "source_column": source_column,
            "canonical_field": canonical_field,
            "confidence": 1.0,
            "reason": "Explicitly assigned by the tenant.",
        }

    assigned_fields = [
        field.get("canonical_field")
        for field in updated.values()
        if isinstance(field, dict) and field.get("canonical_field") in EDITABLE_CUSTOMER_FIELDS
    ]
    if len(assigned_fields) != len(set(assigned_fields)):
        raise ValueError("Each editable CRM field can be assigned to only one source column.")
    return updated


async def update_customer_mapping_fields(
    pg_pool,
    org_id: str,
    mapping_id: str,
    field_assignments: dict[str, str | None],
) -> dict:
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                """
                SELECT m.*, sm.column_catalog
                FROM crm_customer_mappings m
                LEFT JOIN public.schema_metadata_cache sm
                  ON sm.org_id = m.org_id
                 AND sm.connection_id = m.connection_id
                WHERE m.org_id = %s
                  AND m.mapping_id = %s
                  AND m.status IN ('approved', 'draft')
                FOR UPDATE OF m
                """,
                (org_id, mapping_id),
            )
            row = await result.fetchone()
            if not row:
                raise LookupError("Mapping not found")

            serialized = _serialize_mapping(dict(row))
            column_catalog = row.get("column_catalog") or []
            if isinstance(column_catalog, str):
                column_catalog = json.loads(column_catalog)
            table_name = f"{serialized['schema_name']}.{serialized['table_name']}"
            available_columns = {
                column["column"]
                for column in column_catalog
                if column.get("table") == table_name
            }
            if not available_columns:
                raise ValueError("Refresh schema metadata before editing customer fields.")

            field_map = _apply_field_assignments(
                serialized["field_map"],
                field_assignments,
                available_columns,
            )
            update_result = await conn.execute(
                """
                UPDATE crm_customer_mappings
                SET field_map = %s, updated_at = %s
                WHERE org_id = %s AND mapping_id = %s
                RETURNING *
                """,
                (json.dumps(field_map), _utcnow(), org_id, mapping_id),
            )
            updated_row = await update_result.fetchone()
    return _serialize_mapping(dict(updated_row))


async def set_mapping_status(
    pg_pool,
    org_id: str,
    mapping_id: str,
    status: str,
    approved_by: str | None = None,
) -> dict:
    if status not in {"approved", "rejected"}:
        raise ValueError("Unsupported mapping status")

    async with pg_pool.connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                """
                SELECT connection_id
                FROM crm_customer_mappings
                WHERE org_id = %s AND mapping_id = %s
                """,
                (org_id, mapping_id),
            )
            existing = await result.fetchone()
            if not existing:
                raise LookupError("Mapping not found")

            if status == "approved":
                await conn.execute(
                    """
                    UPDATE crm_customer_mappings
                    SET status = 'superseded', updated_at = %s
                    WHERE org_id = %s
                      AND connection_id = %s
                      AND status = 'approved'
                      AND mapping_id != %s
                    """,
                    (_utcnow(), org_id, existing["connection_id"], mapping_id),
                )

            update_result = await conn.execute(
                """
                UPDATE crm_customer_mappings
                SET status = %s,
                    approved_by = CASE WHEN %s = 'approved' THEN %s ELSE approved_by END,
                    approved_at = CASE WHEN %s = 'approved' THEN %s ELSE approved_at END,
                    updated_at = %s
                WHERE org_id = %s AND mapping_id = %s
                RETURNING *
                """,
                (
                    status,
                    status,
                    approved_by,
                    status,
                    _utcnow(),
                    _utcnow(),
                    org_id,
                    mapping_id,
                ),
            )
            row = await update_result.fetchone()
    return _serialize_mapping(dict(row))
