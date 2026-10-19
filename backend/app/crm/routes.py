"""CRM feature routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.app.crm.metrics import get_business_advisor_insights, get_business_metrics
from backend.app.crm.risk import list_risk_snapshots, refresh_risk_snapshots
from backend.app.crm.schemas import RiskListResponse, RiskRefreshRequest, RiskRefreshResponse
from backend.auth import get_current_user, get_org_id_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm", tags=["crm"])

_pg_pool = None


def set_pg_pool(pool):
    """Called by frontend.py at startup to inject the shared connection pool."""
    global _pg_pool
    _pg_pool = pool


def _get_pool():
    if _pg_pool is None:
        raise RuntimeError("PostgreSQL pool not initialized.")
    return _pg_pool


@router.post("/risk/refresh", response_model=RiskRefreshResponse)
async def refresh_customer_risk(
    req: RiskRefreshRequest,
    user: dict = Depends(get_current_user),
):
    """Refresh explainable at-risk customer snapshots from the approved customer mapping."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    try:
        return await refresh_risk_snapshots(pool, org_id, req.limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Risk refresh failed")
        raise HTTPException(status_code=500, detail=f"Risk refresh failed: {exc}")


@router.get("/risk/customers", response_model=RiskListResponse)
async def get_customer_risk(user: dict = Depends(get_current_user)):
    """List latest risk snapshots for the current tenant."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    snapshots = await list_risk_snapshots(pool, org_id)
    return {"snapshots": snapshots, "total": len(snapshots)}


@router.get("/business-metrics")
async def get_tenant_business_metrics(user: dict = Depends(get_current_user)):
    """Return supported business metrics from the authenticated tenant's data."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    return await get_business_metrics(pool, org_id)


@router.get("/business-advisor/insights")
async def get_tenant_business_advisor_insights(user: dict = Depends(get_current_user)):
    """Return evidence-based customer insights for the authenticated tenant."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    return await get_business_advisor_insights(pool, org_id)


# ---------------------------------------------------------------------------
# Dashboard Metrics & Customer 360 endpoints
# ---------------------------------------------------------------------------

import json
from typing import Optional

async def _get_tenant_customers_data(pool, org_id: str) -> list[dict]:
    """Fetch unified tenant customer data from either connected Supabase or local CSV table."""
    mapping = None
    if pool:
        try:
            from backend.app.crm.risk import _approved_mapping
            mapping = await _approved_mapping(pool, org_id)
        except Exception:
            pass

    if mapping:
        from backend.encryption import decrypt_token
        from backend.app.crm.risk import _canonical_sources, _customer_value
        import psycopg
        from psycopg.rows import dict_row
        from psycopg import sql

        field_map = mapping.get("field_map", {})
        if isinstance(field_map, str):
            try:
                field_map = json.loads(field_map)
            except Exception:
                field_map = {}

        canonical_sources = _canonical_sources(field_map)
        source_columns = sorted(set(canonical_sources.values()))
        if not source_columns:
            return []

        readonly_uri = decrypt_token(mapping["encrypted_readonly_uri"])
        try:
            async with await psycopg.AsyncConnection.connect(
                readonly_uri,
                connect_timeout=8,
                autocommit=True,
                row_factory=dict_row,
            ) as ext_conn:
                await ext_conn.execute("SET default_transaction_read_only = on")
                query = sql.SQL("SELECT {} FROM {}.{} LIMIT 1000").format(
                    sql.SQL(", ").join(sql.Identifier(col) for col in source_columns),
                    sql.Identifier(mapping["schema_name"]),
                    sql.Identifier(mapping["table_name"]),
                )
                result = await ext_conn.execute(query)
                rows = [dict(row) for row in await result.fetchall()]

                customers = []
                for row in rows:
                    email_val = _customer_value(row, canonical_sources, "email") or ""
                    phone_val = _customer_value(row, canonical_sources, "phone") or ""
                    name_val = _customer_value(row, canonical_sources, "name") or "Unknown"
                    cust_id_val = _customer_value(row, canonical_sources, "customer_id")
                    
                    id_val = str(cust_id_val) if cust_id_val is not None else (email_val or phone_val or name_val)

                    customers.append({
                        "id": id_val,
                        "name": name_val,
                        "email": email_val,
                        "phone": phone_val,
                        "region": _customer_value(row, canonical_sources, "region") or "",
                        "total_spend": float(_customer_value(row, canonical_sources, "total_spend") or 0),
                        "churn_risk": float(_customer_value(row, canonical_sources, "churn_risk") or 0),
                        "feedback_score": float(_customer_value(row, canonical_sources, "feedback_score") or 0),
                        "last_purchase": str(_customer_value(row, canonical_sources, "last_purchase") or ""),
                    })
                return customers
        except Exception as e:
            logger.error(f"Failed to fetch external customers: {e}")
            return []
    if pool:
        try:
            async with pool.connection() as conn:
                result = await conn.execute(
                    """
                    SELECT customer_id, email, data, created_at
                    FROM public.customers
                    WHERE org_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1000
                    """,
                    (org_id,)
                )
            rows = await result.fetchall()
            customers = []
            for r in rows:
                data = r["data"]
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except Exception:
                        data = {}
                
                customers.append({
                    "id": str(r["customer_id"]),
                    "name": data.get("name") or data.get("first_name", "") or f"Customer #{r['customer_id']}",
                    "email": r["email"] or data.get("email") or "",
                    "phone": data.get("phone") or data.get("phone_number") or "",
                    "region": data.get("region") or data.get("city") or "",
                    "total_spend": float(data.get("total_spend") or data.get("ltv") or data.get("total_spent") or 0),
                    "churn_risk": float(data.get("churn_risk") or data.get("risk_score") or 0),
                    "feedback_score": float(data.get("feedback_score") or data.get("rating") or 0),
                    "last_purchase": str(data.get("last_purchase") or data.get("last_purchase_date") or ""),
                })

            if customers:
                return customers

            # Check public.crm table
            try:
                crm_res = await conn.execute(
                    """
                    SELECT customer_id, name, email, region, total_spend, churn_risk, feedback_score, last_purchase
                    FROM public.crm
                    WHERE org_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1000
                    """,
                    (org_id,)
                )
                crm_rows = await crm_res.fetchall()
                for r in crm_rows:
                    customers.append({
                        "id": str(r["customer_id"]),
                        "name": r["name"],
                        "email": r["email"] or "",
                        "phone": "",
                        "region": r["region"] or "",
                        "total_spend": float(r["total_spend"] or 0),
                        "churn_risk": float(r["churn_risk"] or 0),
                        "feedback_score": float(r["feedback_score"] or 0),
                        "last_purchase": str(r["last_purchase"] or ""),
                    })
            except Exception as e:
                logger.error(f"Failed to fetch public.crm customers: {e}")

            if customers:
                return customers
        except Exception as e:
            logger.error(f"Failed to fetch public.customers: {e}")

    # Return seed customer dataset if tenant DB has no records yet
    return [
        {"id": "cust_101", "name": "Alex Johnson", "email": "delivered@resend.dev", "phone": "+91-9876543210", "region": "Mumbai", "total_spend": 5250.0, "churn_risk": 0.12, "feedback_score": 4.8, "last_purchase": "2026-07-15"},
        {"id": "cust_102", "name": "Priya Sharma", "email": "delivered@resend.dev", "phone": "+91-9876543211", "region": "Delhi", "total_spend": 1890.0, "churn_risk": 0.87, "feedback_score": 2.1, "last_purchase": "2026-05-04"},
        {"id": "cust_103", "name": "Michael Chen", "email": "delivered@resend.dev", "phone": "+91-9876543212", "region": "Bengaluru", "total_spend": 1340.0, "churn_risk": 0.52, "feedback_score": 3.5, "last_purchase": "2026-06-08"},
        {"id": "cust_104", "name": "Sarah Miller", "email": "delivered@resend.dev", "phone": "+91-9876543213", "region": "Pune", "total_spend": 7100.0, "churn_risk": 0.08, "feedback_score": 4.9, "last_purchase": "2026-07-20"},
        {"id": "cust_105", "name": "David Smith", "email": "delivered@resend.dev", "phone": "+91-9876543214", "region": "Hyderabad", "total_spend": 2550.0, "churn_risk": 0.74, "feedback_score": 2.8, "last_purchase": "2026-05-19"},
        {"id": "cust_106", "name": "Ananya Roy", "email": "delivered@resend.dev", "phone": "+91-9876543215", "region": "Kolkata", "total_spend": 3400.0, "churn_risk": 0.25, "feedback_score": 4.2, "last_purchase": "2026-07-10"},
        {"id": "cust_107", "name": "Vikram Patel", "email": "delivered@resend.dev", "phone": "+91-9876543216", "region": "Ahmedabad", "total_spend": 1200.0, "churn_risk": 0.82, "feedback_score": 1.9, "last_purchase": "2026-04-28"},
        {"id": "cust_108", "name": "Neha Gupta", "email": "delivered@resend.dev", "phone": "+91-9876543217", "region": "Jaipur", "total_spend": 4150.0, "churn_risk": 0.18, "feedback_score": 4.6, "last_purchase": "2026-07-18"},
    ]


@router.get("/dashboard/metrics")
async def get_dashboard_metrics(user: dict = Depends(get_current_user)):
    """Fetch aggregated dynamic dashboard KPIs and segments splits for current tenant."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    
    customers = await _get_tenant_customers_data(pool, org_id)
    total_customers = len(customers)
    
    total_spend = sum(c["total_spend"] for c in customers)
    avg_spend = (total_spend / total_customers) if total_customers > 0 else 0
    
    at_risk_count = sum(1 for c in customers if c["churn_risk"] > 0.5)
    
    segments = {
        "champions": 0,
        "loyalists": 0,
        "at_risk": 0,
        "lost": 0,
        "new": 0
    }
    
    for c in customers:
        risk = c["churn_risk"]
        spend = c["total_spend"]
        if risk >= 0.8:
            segments["lost"] += 1
        elif risk >= 0.5:
            segments["at_risk"] += 1
        elif spend >= 5000 and risk < 0.2:
            segments["champions"] += 1
        elif spend >= 2000 and risk < 0.4:
            segments["loyalists"] += 1
        else:
            segments["new"] += 1
            
    recent_campaigns = []
    try:
        async with pool.connection() as conn:
            res = await conn.execute(
                """
                SELECT c.id, c.name, c.status, c.type, c.created_at,
                       COUNT(r.recipient_id) AS total_recipients,
                       COUNT(CASE WHEN r.status = 'sent' THEN 1 END) AS emails_sent
                FROM public.marketing_campaigns c
                LEFT JOIN public.campaign_recipients r ON r.campaign_id = c.id AND r.org_id = c.org_id
                WHERE c.org_id = %s
                GROUP BY c.id
                ORDER BY c.created_at DESC
                LIMIT 5
                """,
                (org_id,)
            )
            rows = await res.fetchall()
            for r in rows:
                recent_campaigns.append({
                    "id": str(r["id"]),
                    "name": r["name"],
                    "status": r["status"],
                    "type": r["type"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "total_recipients": int(r["total_recipients"] or 0),
                    "emails_sent": int(r["emails_sent"] or 0),
                })
    except Exception as e:
        logger.error(f"Failed to fetch recent campaigns for metrics: {e}")
        
    return {
        "total_customers": total_customers,
        "total_spend": round(total_spend, 2),
        "average_spend": round(avg_spend, 2),
        "at_risk_count": at_risk_count,
        "segments": segments,
        "recent_campaigns": recent_campaigns
    }


@router.get("/customers")
async def get_customers_list(
    search: str = "",
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user)
):
    """Search and paginate tenant customer lists (Customer 360)."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    
    customers = await _get_tenant_customers_data(pool, org_id)
    
    if search:
        search_lower = search.lower()
        customers = [
            c for c in customers
            if search_lower in c["name"].lower() or search_lower in c["email"].lower() or search_lower in c["phone"]
        ]
        
    total = len(customers)
    paginated = customers[offset : offset + limit]
    
    return {"customers": paginated, "total": total}


@router.get("/customers/{customer_id}")
async def get_customer_details(
    customer_id: str,
    user: dict = Depends(get_current_user)
):
    """Retrieve complete profile details and campaign emails history for Customer 360 views."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    
    customers = await _get_tenant_customers_data(pool, org_id)
    customer = next((c for c in customers if c["id"] == customer_id), None)
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    emails = []
    try:
        async with pool.connection() as conn:
            res = await conn.execute(
                """
                SELECT e.subject, e.body, e.sent_at, e.status, e.opened, c.name as campaign_name
                FROM public.campaigning_emails e
                JOIN public.marketing_campaigns c ON c.id = e.campaign_id
                WHERE e.org_id = %s AND e.email = %s
                ORDER BY e.sent_at DESC
                """,
                (org_id, customer["email"])
            )
            rows = await res.fetchall()
            for r in rows:
                emails.append({
                    "subject": r["subject"],
                    "body": r["body"],
                    "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
                    "status": r["status"],
                    "opened": r["opened"],
                    "campaign_name": r["campaign_name"]
                })
    except Exception as e:
        logger.error(f"Failed to fetch campaign emails for customer 360: {e}")
        
    return {
        "customer": customer,
        "emails": emails
    }
