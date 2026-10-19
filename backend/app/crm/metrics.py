"""Tenant-scoped business metrics from stored or approved customer data."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from math import isfinite

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from backend.app.crm.risk import _approved_mapping, _canonical_sources, list_risk_snapshots
from backend.encryption import decrypt_token


def _parse_json(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _number(value) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value).replace(",", "").strip())
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _finite_float(value: Decimal) -> float | None:
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return None
    return converted if isfinite(converted) else None


def _metric(value, available: bool, reason: str | None = None) -> dict:
    return {"value": value, "available": available, "reason": reason}


def calculate_business_metrics(
    customers: list[dict],
    available_fields: set[str],
    data_available: bool = True,
) -> dict:
    """Calculate metrics only when the source schema and records support them."""
    count = len(customers)
    metrics = {
        "customer_count": _metric(
            count if data_available else None,
            data_available,
            None if data_available else "No tenant customer data is available.",
        ),
        "total_recorded_spend": _metric(None, False, "Total spend is not mapped in the customer data."),
        "average_customer_spend": _metric(None, False, "Total spend is not mapped in the customer data."),
        "at_risk_customer_count": _metric(None, False, "Churn risk is not mapped in the customer data."),
    }

    if not data_available:
        unavailable_reason = "No tenant customer data is available."
        metrics["total_recorded_spend"] = _metric(None, False, unavailable_reason)
        metrics["average_customer_spend"] = _metric(None, False, unavailable_reason)
        metrics["at_risk_customer_count"] = _metric(None, False, unavailable_reason)
        return metrics

    if "total_spend" in available_fields:
        spend_values = [
            value
            for customer in customers
            if (value := _number(customer.get("total_spend"))) is not None
        ]
        if spend_values:
            total_spend = sum(spend_values, Decimal(0))
            total_float = _finite_float(total_spend)
            average_float = _finite_float(total_spend / len(spend_values))
            if total_float is None or average_float is None:
                reason = "Recorded spend values exceed the supported numeric range."
                metrics["total_recorded_spend"] = _metric(None, False, reason)
                metrics["average_customer_spend"] = _metric(None, False, reason)
            else:
                ignored_reason = (
                    None
                    if len(spend_values) == count
                    else "Missing, invalid, or non-finite spend values were excluded."
                )
                metrics["total_recorded_spend"] = _metric(
                    total_float, True, ignored_reason
                )
                metrics["average_customer_spend"] = _metric(
                    average_float, True, ignored_reason
                )
        else:
            reason = "No valid recorded spend values are available."
            metrics["total_recorded_spend"] = _metric(None, False, reason)
            metrics["average_customer_spend"] = _metric(None, False, reason)

    if "churn_risk" in available_fields:
        risk_values = [
            value
            for customer in customers
            if (value := _number(customer.get("churn_risk"))) is not None
        ]
        if not risk_values:
            metrics["at_risk_customer_count"] = _metric(
                None, False, "No valid recorded churn-risk values are available."
            )
        else:
            metrics["at_risk_customer_count"] = _metric(
                sum(value > Decimal("0.5") for value in risk_values),
                True,
                None
                if len(risk_values) == count
                else "Missing, invalid, or non-finite churn-risk values were excluded.",
            )

    return metrics


async def _local_customer_data(
    pg_pool, org_id: str
) -> tuple[list[dict], set[str], bool]:
    async with pg_pool.connection() as conn:
        customer_result = await conn.execute(
            "SELECT data FROM public.customers WHERE org_id = %s ORDER BY created_at DESC",
            (org_id,),
        )
        customer_rows = await customer_result.fetchall()

        if customer_rows:
            customers = []
            supported = set()
            for row in customer_rows:
                data = _parse_json(row["data"], {})
                data = data if isinstance(data, dict) else {}
                spend_field = next(
                    (field for field in ("total_spend", "ltv", "total_spent") if field in data),
                    None,
                )
                risk_field = next(
                    (field for field in ("churn_risk", "risk_score") if field in data),
                    None,
                )
                if spend_field:
                    supported.add("total_spend")
                if risk_field:
                    supported.add("churn_risk")
                customers.append({
                    "total_spend": data.get(spend_field) if spend_field else None,
                    "churn_risk": data.get(risk_field) if risk_field else None,
                })
            return customers, supported, True

        crm_result = await conn.execute(
            """
            SELECT total_spend, churn_risk
            FROM public.crm
            WHERE org_id = %s
            """,
            (org_id,),
        )
        crm_rows = await crm_result.fetchall()
        if crm_rows:
            return [
                {"total_spend": row["total_spend"], "churn_risk": row["churn_risk"]}
                for row in crm_rows
            ], {"total_spend", "churn_risk"}, True

    return [], set(), False


async def _connected_customer_data(mapping: dict) -> tuple[list[dict], set[str], bool]:
    field_map = _parse_json(mapping.get("field_map"), {})
    canonical_sources = _canonical_sources(field_map)
    source_columns = sorted({
        canonical_sources[field]
        for field in ("total_spend", "churn_risk")
        if field in canonical_sources
    })
    selected_columns = (
        sql.SQL(", ").join(sql.Identifier(column) for column in source_columns)
        if source_columns
        else sql.SQL("1")
    )
    query = sql.SQL("SELECT {} FROM {}.{}").format(
        selected_columns,
        sql.Identifier(mapping["schema_name"]),
        sql.Identifier(mapping["table_name"]),
    )

    async with await psycopg.AsyncConnection.connect(
        decrypt_token(mapping["encrypted_readonly_uri"]),
        connect_timeout=8,
        autocommit=True,
        row_factory=dict_row,
    ) as conn:
        await conn.execute("SET default_transaction_read_only = on")
        result = await conn.execute(query)
        rows = [dict(row) for row in await result.fetchall()]

    customers = [
        {
            "total_spend": row.get(canonical_sources.get("total_spend")),
            "churn_risk": row.get(canonical_sources.get("churn_risk")),
        }
        for row in rows
    ]
    return customers, set(canonical_sources), True


async def _recorded_loyalty_purchase_spend(pg_pool, org_id: str) -> dict:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT COUNT(*) AS qualifying_purchases,
                   SUM(e.purchase_amount) AS total_spend
            FROM public.loyalty_purchase_events e
            JOIN public.loyalty_customer_accounts a
              ON a.org_id = e.org_id
             AND a.loyalty_customer_id = e.loyalty_customer_id
            WHERE e.org_id = %s
              AND e.is_verified = TRUE
              AND e.is_demo = FALSE
              AND a.is_demo = FALSE
            """,
            (org_id,),
        )
        row = await result.fetchone()

    if not row or row["qualifying_purchases"] == 0:
        return _metric(
            None,
            False,
            "No verified live loyalty purchase records are available for this tenant.",
        )
    return _metric(float(row["total_spend"]), True)


async def get_business_metrics(pg_pool, org_id: str) -> dict:
    """Calculate customer metrics from this tenant's approved or stored data."""
    try:
        mapping = await _approved_mapping(pg_pool, org_id)
    except LookupError:
        customers, fields, data_available = await _local_customer_data(pg_pool, org_id)
    else:
        customers, fields, data_available = await _connected_customer_data(mapping)

    customer_metrics = calculate_business_metrics(customers, fields, data_available)
    customer_metrics["recorded_loyalty_purchase_spend"] = (
        await _recorded_loyalty_purchase_spend(pg_pool, org_id)
    )
    return {
        "source": "tenant_customer_data",
        "metrics": customer_metrics,
    }


def build_business_advisor_insights(metrics_response: dict, risk_snapshots: list[dict]) -> dict:
    """Build concise evidence-based insights from tenant metrics and persisted risk snapshots."""
    metrics = metrics_response["metrics"]
    unavailable = {
        name: value["reason"]
        for name, value in metrics.items()
        if not value["available"]
    }

    summary_parts = []
    customer_count = metrics["customer_count"]
    if customer_count["available"]:
        summary_parts.append(f"Customer records: {customer_count['value']}.")
    at_risk = metrics["at_risk_customer_count"]
    if at_risk["available"]:
        summary_parts.append(f"Customers above the recorded risk threshold: {at_risk['value']}.")
    spend = metrics["total_recorded_spend"]
    if spend["available"]:
        summary_parts.append(f"Total recorded customer spend: {spend['value']:.2f}.")
    loyalty_spend = metrics.get("recorded_loyalty_purchase_spend")
    if loyalty_spend and loyalty_spend["available"]:
        summary_parts.append(
            f"Recorded loyalty purchase spend: {loyalty_spend['value']:.2f}."
        )
    if not summary_parts:
        summary_parts.append("No supported customer business metrics are currently available.")

    counts = {
        level: sum(snapshot["risk_level"] == level for snapshot in risk_snapshots)
        for level in ("high", "medium", "low", "unknown")
    }
    recommendations = []
    if risk_snapshots:
        if counts["high"]:
            recommendations.append({
                "recommendation": "Review the persisted high-risk customer assessments and validate their evidence before outreach.",
                "evidence": f"{counts['high']} high-risk assessment(s) among the latest persisted snapshots.",
            })
        if counts["medium"]:
            recommendations.append({
                "recommendation": "Review medium-risk assessments for customers who may need follow-up.",
                "evidence": f"{counts['medium']} medium-risk assessment(s) among the latest persisted snapshots.",
            })
    else:
        recommendations.append({
            "recommendation": "Refresh the tenant's customer risk assessment after confirming customer data and mappings are current.",
            "evidence": "No persisted risk snapshots are available for this tenant.",
        })

    return {
        "source": metrics_response["source"],
        "metrics": metrics,
        "risk_classifications": {
            "available": bool(risk_snapshots),
            "scope": "latest_persisted_snapshots",
            "counts": counts if risk_snapshots else None,
            "reason": None if risk_snapshots else "No persisted risk snapshots are available for this tenant.",
        },
        "summary": " ".join(summary_parts),
        "recommendations": recommendations,
        "unavailable_metrics": unavailable,
    }


async def get_business_advisor_insights(pg_pool, org_id: str) -> dict:
    metrics_response = await get_business_metrics(pg_pool, org_id)
    risk_snapshots = await list_risk_snapshots(
        pg_pool, org_id, include_seed_fallback=False
    )
    return build_business_advisor_insights(metrics_response, risk_snapshots)
