"""Service logic for campaign CRUD, AI email generation, preview persistence, and batch sending."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq

from backend.app.connections.metadata import get_latest_schema_metadata
from backend.app.integrations.gmail import send_email

logger = logging.getLogger(__name__)


def _parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def serialize_recipient(row: dict) -> dict:
    return {
        "recipient_id": str(row["recipient_id"]),
        "campaign_id": str(row["campaign_id"]),
        "org_id": str(row["org_id"]),
        "customer_name": row.get("customer_name"),
        "customer_email": row["customer_email"],
        "subject": row.get("subject"),
        "body": row.get("body"),
        "recommended_products": _parse_json(row.get("recommended_products"), []),
        "status": row.get("status", "pending"),
        "sent_at": row["sent_at"].isoformat() if row.get("sent_at") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def serialize_campaign(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "org_id": str(row["org_id"]),
        "name": row["name"],
        "type": row.get("type", "marketing"),
        "description": row.get("description"),
        "status": row.get("status", "draft"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "total_recipients": int(row.get("total_recipients") or 0),
        "sent_recipients": int(row.get("sent_recipients") or 0),
        "pending_recipients": int(row.get("pending_recipients") or 0),
    }


# ============================================================================
# Campaign CRUD
# ============================================================================


async def list_campaigns(pg_pool, org_id: str) -> list[dict]:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT c.*,
                   COUNT(r.recipient_id) AS total_recipients,
                   COUNT(CASE WHEN r.status = 'sent' THEN 1 END) AS sent_recipients,
                   COUNT(CASE WHEN r.status IN ('pending', 'approved') THEN 1 END) AS pending_recipients
            FROM public.marketing_campaigns c
            LEFT JOIN public.campaign_recipients r ON r.campaign_id = c.id AND r.org_id = c.org_id
            WHERE c.org_id = %s
            GROUP BY c.id
            ORDER BY c.created_at DESC
            """,
            (org_id,),
        )
        rows = await result.fetchall()
    return [serialize_campaign(dict(row)) for row in rows]


async def create_campaign(
    pg_pool, org_id: str, name: str, campaign_type: str, description: str | None = None
) -> dict:
    allowed_types = [
        "loyalty",
        "referral",
        "re-engagement",
        "at risk",
        "new customer",
        "champion",
        "about to sleep",
        "lost",
        "potential loyalist",
    ]
    if campaign_type not in allowed_types:
        campaign_type = "re-engagement"

    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            INSERT INTO public.marketing_campaigns (name, type, description, status, org_id)
            VALUES (%s, %s, %s, 'draft', %s)
            RETURNING id, org_id, name, type, description, status, created_at
            """,
            (name, campaign_type, description, org_id),
        )
        row = dict(await result.fetchone())
        row["total_recipients"] = 0
        row["sent_recipients"] = 0
        row["pending_recipients"] = 0
    return serialize_campaign(row)


async def get_campaign(pg_pool, org_id: str, campaign_id: str) -> dict:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT c.*,
                   COUNT(r.recipient_id) AS total_recipients,
                   COUNT(CASE WHEN r.status = 'sent' THEN 1 END) AS sent_recipients,
                   COUNT(CASE WHEN r.status IN ('pending', 'approved') THEN 1 END) AS pending_recipients
            FROM public.marketing_campaigns c
            LEFT JOIN public.campaign_recipients r ON r.campaign_id = c.id AND r.org_id = c.org_id
            WHERE c.org_id = %s AND c.id = %s
            GROUP BY c.id
            """,
            (org_id, campaign_id),
        )
        row = await result.fetchone()
    if not row:
        raise LookupError(f"Campaign {campaign_id} not found")
    return serialize_campaign(dict(row))


async def delete_campaign(pg_pool, org_id: str, campaign_id: str) -> bool:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            "DELETE FROM public.marketing_campaigns WHERE org_id = %s AND id = %s RETURNING id",
            (org_id, campaign_id),
        )
        row = await result.fetchone()
    return bool(row)


# ============================================================================
# Recipient Management
# ============================================================================


async def list_recipients(pg_pool, org_id: str, campaign_id: str) -> list[dict]:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT *
            FROM public.campaign_recipients
            WHERE org_id = %s AND campaign_id = %s
            ORDER BY created_at DESC
            """,
            (org_id, campaign_id),
        )
        rows = await result.fetchall()
    return [serialize_recipient(dict(row)) for row in rows]


async def save_recipients(pg_pool, org_id: str, campaign_id: str, recipients: list[dict]) -> list[dict]:
    saved = []
    async with pg_pool.connection() as conn:
        for recipient in recipients:
            result = await conn.execute(
                """
                INSERT INTO public.campaign_recipients (
                    campaign_id,
                    org_id,
                    customer_name,
                    customer_email,
                    subject,
                    body,
                    recommended_products,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    campaign_id,
                    org_id,
                    recipient.get("customer_name"),
                    recipient["customer_email"],
                    recipient.get("subject"),
                    recipient.get("body"),
                    json.dumps(recipient.get("recommended_products") or []),
                    recipient.get("status", "pending"),
                ),
            )
            saved.append(serialize_recipient(dict(await result.fetchone())))
    return saved


async def update_recipient_status(
    pg_pool,
    org_id: str,
    recipient_id: str,
    status: str,
    subject: str | None = None,
    body: str | None = None,
) -> dict:
    async with pg_pool.connection() as conn:
        if subject or body:
            result = await conn.execute(
                """
                UPDATE public.campaign_recipients
                SET status = %s,
                    subject = COALESCE(%s, subject),
                    body = COALESCE(%s, body),
                    sent_at = CASE WHEN %s = 'sent' THEN now() ELSE sent_at END
                WHERE org_id = %s AND recipient_id = %s
                RETURNING *
                """,
                (status, subject, body, status, org_id, recipient_id),
            )
        else:
            result = await conn.execute(
                """
                UPDATE public.campaign_recipients
                SET status = %s,
                    sent_at = CASE WHEN %s = 'sent' THEN now() ELSE sent_at END
                WHERE org_id = %s AND recipient_id = %s
                RETURNING *
                """,
                (status, status, org_id, recipient_id),
            )
        row = await result.fetchone()
    if not row:
        raise LookupError("Campaign recipient not found")
    return serialize_recipient(dict(row))


# ============================================================================
# Target Audience & AI Email Generation
# ============================================================================


async def _fetch_target_customers(pg_pool, org_id: str, limit: int = 20) -> list[dict]:
    """Discover customer records from the tenant's data store (CSV JSONB customers, CRM table, or schema cache)."""
    customers = []

    # 1. Check public.customers (JSONB customers table uploaded via CSV)
    async with pg_pool.connection() as conn:
        res = await conn.execute(
            """
            SELECT customer_id, email, data
            FROM public.customers
            WHERE org_id = %s AND email IS NOT NULL AND email != ''
            LIMIT %s
            """,
            (org_id, limit),
        )
        rows = await res.fetchall()
        for r in rows:
            data = _parse_json(r["data"], {})
            name = data.get("name") or data.get("full_name") or f"Customer #{r['customer_id']}"
            customers.append(
                {
                    "customer_id": str(r["customer_id"]),
                    "name": name,
                    "email": r["email"],
                    "data": data,
                }
            )

    if customers:
        return customers

    # 2. Check public.crm table
    async with pg_pool.connection() as conn:
        res = await conn.execute(
            """
            SELECT customer_id, name, email, region, total_spend, product_category, churn_risk
            FROM public.crm
            WHERE org_id = %s AND email IS NOT NULL AND email != ''
            LIMIT %s
            """,
            (org_id, limit),
        )
        rows = await res.fetchall()
        for r in rows:
            customers.append(
                {
                    "customer_id": str(r["customer_id"]),
                    "name": r["name"],
                    "email": r["email"],
                    "data": {
                        "region": r["region"],
                        "total_spend": r["total_spend"],
                        "product_category": r["product_category"],
                        "churn_risk": r["churn_risk"],
                    },
                }
            )

    if customers:
        return customers

    # 3. Fallback: Return sample customer targets for demonstration if tenant DB has no records yet
    logger.info("No customers found in DB tables; returning seed customers for org_id=%s", org_id)
    return [
        {
            "customer_id": "cust_101",
            "name": "Alex Johnson",
            "email": "delivered@resend.dev",
            "data": {"segment": "VIP", "total_spend": 1250, "preferred_category": "Electronics"},
        },
        {
            "customer_id": "cust_102",
            "name": "Priya Sharma",
            "email": "delivered@resend.dev",
            "data": {"segment": "At-Risk", "total_spend": 890, "preferred_category": "Fashion"},
        },
        {
            "customer_id": "cust_103",
            "name": "Michael Chen",
            "email": "delivered@resend.dev",
            "data": {"segment": "New", "total_spend": 340, "preferred_category": "Home & Kitchen"},
        },
        {
            "customer_id": "cust_104",
            "name": "Sarah Miller",
            "email": "delivered@resend.dev",
            "data": {"segment": "Champion", "total_spend": 2100, "preferred_category": "Electronics"},
        },
        {
            "customer_id": "cust_105",
            "name": "David Smith",
            "email": "delivered@resend.dev",
            "data": {"segment": "Potential Loyalist", "total_spend": 550, "preferred_category": "Sports"},
        },
    ][:limit]


async def generate_campaign_recipients(
    pg_pool,
    org_id: str,
    campaign_id: str,
    target_prompt: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Generate personalized HTML campaign emails for target customers using LLM and save previews."""
    campaign = await get_campaign(pg_pool, org_id, campaign_id)
    customers = await _fetch_target_customers(pg_pool, org_id, limit=limit)

    if not customers:
        return []

    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)

    system_prompt = (
        "You are an expert CRM Marketing Copywriter for BandhanAI. "
        "Your task is to write a highly personalized, compelling, action-oriented HTML marketing email for a customer.\n\n"
        "Return ONLY a JSON object with exact keys:\n"
        '{"subject": "...", "body": "<div style=\'font-family: sans-serif;\'>...</div>"}\n\n'
        "Requirements:\n"
        "- The body MUST be clean, modern HTML with inline CSS styling (dark/gold luxury theme matching BandhanAI or vibrant brand tone).\n"
        "- Personalize using the customer's name and specific context/history.\n"
        "- Do not include markdown codeblocks inside JSON string values.\n"
    )

    generated_recipients = []

    for cust in customers:
        cust_name = cust["name"]
        cust_email = cust["email"]
        cust_context = json.dumps(cust.get("data") or {})

        prompt_msg = (
            f"Campaign Name: {campaign['name']}\n"
            f"Campaign Type: {campaign['type']}\n"
            f"Campaign Description: {campaign.get('description') or ''}\n"
            f"Target Strategy / Goal: {target_prompt or 'Drive engagement and offer personalized value'}\n\n"
            f"Customer Name: {cust_name}\n"
            f"Customer Email: {cust_email}\n"
            f"Customer Profile Data: {cust_context}\n\n"
            "Write the subject line and HTML email body for this customer now."
        )

        try:
            response = await llm.ainvoke([SystemMessage(content=system_prompt), prompt_msg])
            text_resp = response.content.strip()
            # Clean possible markdown wrapping ```json ... ```
            if text_resp.startswith("```"):
                lines = text_resp.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                text_resp = "\n".join(lines).strip()

            parsed = json.loads(text_resp)
            subject = parsed.get("subject", f"Special offer for {cust_name}")
            body = parsed.get("body", f"<p>Hi {cust_name}, check out our latest offers!</p>")
        except Exception as exc:
            logger.warning("LLM email generation fallback for %s: %s", cust_email, exc)
            subject = f"Exclusive {campaign['type'].title()} Offer for {cust_name}"
            body = (
                f"<div style='font-family: Arial, sans-serif; padding: 20px; color: #222;'>"
                f"<h2>Hello {cust_name},</h2>"
                f"<p>We value your partnership with us! Based on your history, we have selected exclusive offers just for you.</p>"
                f"<p><a href='#' style='background: #E8A020; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px;'>Explore Rewards</a></p>"
                f"<p>Best regards,<br>The BandhanAI Team</p>"
                f"</div>"
            )

        generated_recipients.append(
            {
                "customer_name": cust_name,
                "customer_email": cust_email,
                "subject": subject,
                "body": body,
                "recommended_products": [],
                "status": "pending",
            }
        )

    # Save to campaign_recipients table
    saved = await save_recipients(pg_pool, org_id, campaign_id, generated_recipients)
    return saved


# ============================================================================
# Batch Send Execution
# ============================================================================


async def send_campaign_batch(
    pg_pool,
    org_id: str,
    campaign_id: str,
    recipient_ids: list[str] | None = None,
) -> dict:
    """Batch send all pending/approved recipient emails for a campaign via Gmail API."""
    async with pg_pool.connection() as conn:
        if recipient_ids:
            res = await conn.execute(
                """
                SELECT *
                FROM public.campaign_recipients
                WHERE org_id = %s AND campaign_id = %s AND recipient_id = ANY(%s) AND status IN ('pending', 'approved')
                """,
                (org_id, campaign_id, recipient_ids),
            )
        else:
            res = await conn.execute(
                """
                SELECT *
                FROM public.campaign_recipients
                WHERE org_id = %s AND campaign_id = %s AND status IN ('pending', 'approved')
                """,
                (org_id, campaign_id),
            )
        rows = [dict(r) for r in await res.fetchall()]

    if not rows:
        return {
            "total": 0,
            "sent": 0,
            "failed": 0,
            "method": "none",
            "message": "No pending or approved recipients to send.",
            "details": [],
        }

    sent_count = 0
    failed_count = 0
    details = []

    for row in rows:
        r_id = str(row["recipient_id"])
        email = row["customer_email"]
        subject = row.get("subject") or "Exclusive Campaign Offer"
        body = row.get("body") or "<p>Thank you for being our valued customer.</p>"

        send_res = await send_email(
            pg_pool=pg_pool,
            org_id=org_id,
            to_email=email,
            subject=subject,
            body_html=body,
            campaign_id=campaign_id,
        )

        status_val = "sent" if send_res["success"] else "failed"
        await update_recipient_status(pg_pool, org_id, r_id, status=status_val)

        if send_res["success"]:
            sent_count += 1
        else:
            failed_count += 1

        details.append(
            {
                "recipient_id": r_id,
                "email": email,
                "status": status_val,
                "method": send_res["method"],
                "message": send_res["message"],
            }
        )

    # Update marketing_campaigns status to 'sent' or 'active'
    async with pg_pool.connection() as conn:
        await conn.execute(
            """
            UPDATE public.marketing_campaigns
            SET status = 'sent'
            WHERE org_id = %s AND id = %s
            """,
            (org_id, campaign_id),
        )

    primary_method = details[0]["method"] if details else "simulated"
    return {
        "total": len(rows),
        "sent": sent_count,
        "failed": failed_count,
        "method": primary_method,
        "message": f"Campaign batch execution complete: {sent_count} sent, {failed_count} failed via {primary_method}.",
        "details": details,
    }
