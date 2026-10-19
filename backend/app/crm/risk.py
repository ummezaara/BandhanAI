"""Explainable at-risk customer scoring for approved tenant customer mappings."""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from dateutil.parser import parse as parse_date

from backend.encryption import decrypt_token

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_json(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _serialize_snapshot(row: dict) -> dict:
    return {
        "snapshot_id": str(row["snapshot_id"]),
        "org_id": str(row["org_id"]),
        "connection_id": str(row["connection_id"]) if row.get("connection_id") else None,
        "mapping_id": str(row["mapping_id"]) if row.get("mapping_id") else None,
        "source_type": row.get("source_type", "connected"),
        "external_customer_id": row.get("external_customer_id"),
        "customer_label": row.get("customer_label"),
        "risk_level": row.get("risk_level", "unknown"),
        "risk_score": float(row["risk_score"]) if row.get("risk_score") is not None else None,
        "reasons": _parse_json(row.get("reasons"), []),
        "source_fields": _parse_json(row.get("source_fields"), {}),
        "computed_at": row["computed_at"].isoformat() if row.get("computed_at") else None,
    }


async def _approved_mapping(pg_pool, org_id: str) -> dict:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT
                m.*,
                c.encrypted_readonly_uri
            FROM crm_customer_mappings m
            JOIN tenant_data_connections c
              ON c.connection_id = m.connection_id
             AND c.org_id = m.org_id
            WHERE m.org_id = %s
              AND m.status = 'approved'
              AND c.status = 'connected'
            ORDER BY m.approved_at DESC NULLS LAST, m.updated_at DESC
            LIMIT 1
            """,
            (org_id,),
        )
        row = await result.fetchone()
    if not row:
        raise LookupError("No approved customer mapping found")
    return dict(row)


def _canonical_sources(field_map: dict) -> dict[str, str]:
    sources = {}
    for source_col, details in field_map.items():
        if isinstance(details, dict):
            canonical = details.get("canonical_field")
            if canonical and canonical not in sources:
                sources[canonical] = source_col
    return sources


def _is_usable_risk_mapping(mapping: dict) -> bool:
    table_name = str(mapping.get("table_name") or "").strip().lower()
    if table_name.startswith("loyalty_"):
        return False

    field_map = _parse_json(mapping.get("field_map"), {})
    if not isinstance(field_map, dict):
        return False
    canonical_sources = _canonical_sources(field_map)
    has_identity = any(
        canonical_sources.get(field)
        for field in ("customer_id", "email", "phone", "name")
    )
    has_risk_evidence = any(
        canonical_sources.get(field)
        for field in ("churn_risk", "last_purchase", "feedback_score")
    )
    return has_identity and has_risk_evidence


def _customer_value(row: dict, canonical_sources: dict[str, str], canonical: str):
    source = canonical_sources.get(canonical)
    return row.get(source) if source else None


def _days_since(value: Any) -> int | None:
    if not value:
        return None
    try:
        dt = parse_date(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (_utcnow() - dt).days
    except Exception:
        return None


def _float_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(str(value).replace(",", "").strip())
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _score_customer(row: dict, canonical_sources: dict[str, str]) -> tuple[str, float | None, list[str], dict[str, Any]]:
    reasons: list[str] = []
    score = 0.0
    source_fields: dict[str, Any] = {}

    explicit_risk = _float_value(_customer_value(row, canonical_sources, "churn_risk"))
    if explicit_risk is not None:
        normalized = explicit_risk if explicit_risk <= 1 else explicit_risk / 100
        score += min(max(normalized, 0), 1) * 0.7
        source_fields["churn_risk"] = explicit_risk
        reasons.append(f"Existing churn/risk field indicates {round(normalized * 100)}% risk.")

    last_purchase = _customer_value(row, canonical_sources, "last_purchase")
    days = _days_since(last_purchase)
    if days is not None:
        source_fields["last_purchase"] = str(last_purchase)
        if days >= 180:
            score += 0.65
            reasons.append(f"No purchase/activity for {days} days.")
        elif days >= 90:
            score += 0.42
            reasons.append(f"Last purchase/activity was {days} days ago.")
        elif days >= 45:
            score += 0.2
            reasons.append(f"Purchase/activity is becoming stale at {days} days.")

    feedback = _float_value(_customer_value(row, canonical_sources, "feedback_score"))
    if feedback is not None:
        source_fields["feedback_score"] = feedback
        if feedback <= 2:
            score += 0.35
            reasons.append("Feedback score is very low.")
        elif feedback <= 3:
            score += 0.18
            reasons.append("Feedback score is below healthy range.")

    if not reasons:
        return "unknown", None, ["Not enough approved customer fields to compute risk."], source_fields

    score = min(score, 1.0)
    if score >= 0.65:
        level = "high"
    elif score >= 0.35:
        level = "medium"
    else:
        level = "low"
    return level, round(score, 2), reasons, source_fields


async def _local_customer_rows(pg_pool, org_id: str, limit: int) -> list[dict]:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT customer_id, data
            FROM public.customers
            WHERE org_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (org_id, limit),
        )
        return [dict(row) for row in await result.fetchall()]


def _local_customer_values(row: dict) -> tuple[str | None, str | None, dict, dict[str, str]]:
    external_id = row.get("customer_id")
    if external_id is None or not str(external_id).strip():
        return None, None, {}, {}

    data = _parse_json(row.get("data"), {})
    data = data if isinstance(data, dict) else {}
    values: dict[str, Any] = {}
    for field in ("churn_risk", "feedback_score", "total_spend"):
        value = _float_value(data.get(field))
        if value is not None:
            values[field] = value

    last_purchase = data.get("last_purchase")
    if isinstance(last_purchase, (str, datetime)) and _days_since(last_purchase) is not None:
        values["last_purchase"] = str(last_purchase)

    name = data.get("name")
    label = str(name).strip() if name is not None and str(name).strip() else f"Customer {external_id}"
    canonical_sources = {
        field: field
        for field in ("churn_risk", "feedback_score", "last_purchase")
        if field in values
    }
    return str(external_id), label, values, canonical_sources


async def refresh_risk_snapshots(pg_pool, org_id: str, limit: int = 500) -> dict:
    snapshots = []
    try:
        mapping = await _approved_mapping(pg_pool, org_id)
    except LookupError:
        mapping = None
    except Exception as exc:
        logger.warning(
            "Risk refresh unavailable for org_id=%s: approved customer mapping lookup failed (%s)",
            org_id,
            type(exc).__name__,
        )
        raise ValueError(
            "Risk assessment unavailable: an approved customer mapping could not be loaded."
        ) from exc

    if mapping is not None and not _is_usable_risk_mapping(mapping):
        mapping = None

    source_type = "local"
    connection_id = None
    mapping_id = None
    if mapping is not None:
        source_type = "connected"
        connection_id = mapping["connection_id"]
        mapping_id = mapping["mapping_id"]
        try:
            field_map = _parse_json(mapping["field_map"], {})
            canonical_sources = _canonical_sources(field_map)
            source_columns = sorted(set(canonical_sources.values()))
        except Exception as exc:
            logger.warning(
                "Risk refresh unavailable for org_id=%s: approved mapping is invalid (%s)",
                org_id,
                type(exc).__name__,
            )
            raise ValueError(
                "Risk assessment unavailable: the approved customer mapping is invalid."
            ) from exc
        if not source_columns:
            raise ValueError("Risk assessment unavailable: the approved mapping has no usable customer fields.")

        try:
            readonly_uri = decrypt_token(mapping["encrypted_readonly_uri"])
            async with await psycopg.AsyncConnection.connect(
                readonly_uri,
                connect_timeout=8,
                autocommit=True,
                row_factory=dict_row,
            ) as ext_conn:
                await ext_conn.execute("SET default_transaction_read_only = on")
                query = sql.SQL("SELECT {} FROM {}.{} LIMIT {}").format(
                    sql.SQL(", ").join(sql.Identifier(col) for col in source_columns),
                    sql.Identifier(mapping["schema_name"]),
                    sql.Identifier(mapping["table_name"]),
                    sql.Literal(limit),
                )
                result = await ext_conn.execute(query)
                rows = [dict(row) for row in await result.fetchall()]

            for row in rows:
                external_id = (
                    _customer_value(row, canonical_sources, "customer_id")
                    or _customer_value(row, canonical_sources, "email")
                    or _customer_value(row, canonical_sources, "phone")
                    or _customer_value(row, canonical_sources, "name")
                )
                label = (
                    _customer_value(row, canonical_sources, "name")
                    or _customer_value(row, canonical_sources, "email")
                    or _customer_value(row, canonical_sources, "phone")
                    or str(external_id or "Unknown customer")
                )
                level, score, reasons, source_fields = _score_customer(row, canonical_sources)
                snapshots.append(
                    {
                        "external_customer_id": str(external_id) if external_id is not None else None,
                        "customer_label": str(label) if label is not None else None,
                        "risk_level": level,
                        "risk_score": score,
                        "reasons": reasons,
                        "source_fields": source_fields,
                    }
                )
        except Exception as exc:
            logger.warning(
                "Risk refresh unavailable for org_id=%s: connected customer data read failed (%s)",
                org_id,
                type(exc).__name__,
            )
            raise ValueError(
                "Risk assessment unavailable: connected customer data could not be read."
            ) from exc
    else:
        try:
            rows = await _local_customer_rows(pg_pool, org_id, limit)
        except Exception as exc:
            logger.warning(
                "Risk refresh unavailable for org_id=%s: local customer data read failed (%s)",
                org_id,
                type(exc).__name__,
            )
            raise ValueError(
                "Risk assessment unavailable: local tenant customer data could not be read."
            ) from exc

        for row in rows:
            external_id, label, customer_values, canonical_sources = _local_customer_values(row)
            if external_id is None:
                continue
            level, score, reasons, source_fields = _score_customer(
                customer_values, canonical_sources
            )
            total_spend = customer_values.get("total_spend")
            if total_spend is not None:
                source_fields["total_spend"] = total_spend
            snapshots.append(
                {
                    "external_customer_id": external_id,
                    "customer_label": label,
                    "risk_level": level,
                    "risk_score": score,
                    "reasons": reasons,
                    "source_fields": source_fields,
                }
            )

    if not snapshots:
        raise ValueError(
            "Risk assessment unavailable: the selected customer source returned no usable customer records; existing snapshots were preserved."
        )

    try:
        async with pg_pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM customer_risk_snapshots WHERE org_id = %s",
                    (org_id,),
                )
                for snapshot in snapshots:
                    await conn.execute(
                        """
                        INSERT INTO customer_risk_snapshots (
                            org_id,
                            connection_id,
                            mapping_id,
                            source_type,
                            external_customer_id,
                            customer_label,
                            risk_level,
                            risk_score,
                            reasons,
                            source_fields,
                            computed_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            org_id,
                            connection_id,
                            mapping_id,
                            source_type,
                            snapshot["external_customer_id"],
                            snapshot["customer_label"],
                            snapshot["risk_level"],
                            snapshot["risk_score"],
                            json.dumps(snapshot["reasons"]),
                            json.dumps(snapshot["source_fields"], default=str),
                            _utcnow(),
                        ),
                    )
    except Exception as exc:
        logger.error(
            "Failed to persist risk snapshots for org_id=%s (%s)",
            org_id,
            type(exc).__name__,
        )
        raise RuntimeError(
            "Risk assessment failed: snapshots could not be persisted."
        ) from exc

    counts = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for snapshot in snapshots:
        counts[snapshot["risk_level"]] += 1

    return {
        "refreshed": True,
        "total_scored": len(snapshots),
        "high_risk": counts["high"],
        "medium_risk": counts["medium"],
        "low_risk": counts["low"],
        "unknown": counts["unknown"],
    }


async def list_risk_snapshots(
    pg_pool, org_id: str, limit: int = 50, include_seed_fallback: bool = True
) -> list[dict]:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT *
            FROM customer_risk_snapshots
            WHERE org_id = %s
            ORDER BY
              CASE risk_level
                WHEN 'high' THEN 0
                WHEN 'medium' THEN 1
                WHEN 'low' THEN 2
                ELSE 3
              END,
              risk_score DESC NULLS LAST,
              computed_at DESC
            LIMIT %s
            """,
            (org_id, limit),
        )
        rows = await result.fetchall()
    if rows:
        return [_serialize_snapshot(dict(row)) for row in rows]
    if not include_seed_fallback:
        return []

    # Return seed fallback risk snapshots for display if tenant has not run a risk scan yet
    now_iso = datetime.now(timezone.utc).isoformat()
    return [
        {
            "snapshot_id": "seed-snap-1",
            "org_id": org_id,
            "connection_id": "seed",
            "mapping_id": "seed",
            "external_customer_id": "cust_102",
            "customer_label": "Priya Sharma",
            "risk_level": "high",
            "risk_score": 0.87,
            "reasons": ["No purchases in the last 78 days", "Feedback score dropped to 2.1/5", "Churn probability elevated"],
            "source_fields": {"city": "Delhi", "total_spend": 1890},
            "computed_at": now_iso,
        },
        {
            "snapshot_id": "seed-snap-2",
            "org_id": org_id,
            "connection_id": "seed",
            "mapping_id": "seed",
            "external_customer_id": "cust_107",
            "customer_label": "Vikram Patel",
            "risk_level": "high",
            "risk_score": 0.82,
            "reasons": ["Last order placed 85 days ago", "Low satisfaction score (1.9/5)", "Inactivity alert"],
            "source_fields": {"city": "Ahmedabad", "total_spend": 1200},
            "computed_at": now_iso,
        },
        {
            "snapshot_id": "seed-snap-3",
            "org_id": org_id,
            "connection_id": "seed",
            "mapping_id": "seed",
            "external_customer_id": "cust_105",
            "customer_label": "David Smith",
            "risk_level": "high",
            "risk_score": 0.74,
            "reasons": ["Last order placed 64 days ago", "Order frequency decreased by 40%"],
            "source_fields": {"city": "Hyderabad", "total_spend": 2550},
            "computed_at": now_iso,
        },
        {
            "snapshot_id": "seed-snap-4",
            "org_id": org_id,
            "connection_id": "seed",
            "mapping_id": "seed",
            "external_customer_id": "cust_103",
            "customer_label": "Michael Chen",
            "risk_level": "medium",
            "risk_score": 0.52,
            "reasons": ["Single order placed 45 days ago with no follow-up purchases"],
            "source_fields": {"city": "Bengaluru", "total_spend": 1340},
            "computed_at": now_iso,
        },
        {
            "snapshot_id": "seed-snap-5",
            "org_id": org_id,
            "connection_id": "seed",
            "mapping_id": "seed",
            "external_customer_id": "cust_101",
            "customer_label": "Alex Johnson",
            "risk_level": "low",
            "risk_score": 0.12,
            "reasons": ["High purchase frequency", "VIP tier status with high lifetime spend"],
            "source_fields": {"city": "Mumbai", "total_spend": 5250},
            "computed_at": now_iso,
        },
        {
            "snapshot_id": "seed-snap-6",
            "org_id": org_id,
            "connection_id": "seed",
            "mapping_id": "seed",
            "external_customer_id": "cust_104",
            "customer_label": "Sarah Miller",
            "risk_level": "low",
            "risk_score": 0.08,
            "reasons": ["Champion customer", "Active purchase history within last 5 days"],
            "source_fields": {"city": "Pune", "total_spend": 7100},
            "computed_at": now_iso,
        },
    ]
