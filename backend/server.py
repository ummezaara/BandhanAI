"""
Custom MCP Marketing Server for BandhanAI.

Exposes two tools over stdio transport:
    - create_campaign: Create a new marketing campaign (scoped by org_id)
    - send_campaign_email: Record a campaign email send (scoped by org_id)

The ORG_ID is passed as an environment variable by the dynamic MCP config builder,
ensuring all database operations are scoped to the calling tenant.
"""

from mcp.server.fastmcp import FastMCP
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
import os
import pandas as pd
from dotenv import load_dotenv
from uuid import UUID
import json

load_dotenv()

# ----------------------------
# DB Session
# ----------------------------

engine = create_engine(url=os.getenv("SUPABASE_URI"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Tenant scoping — ORG_ID is injected via MCP server env config
ORG_ID = os.getenv("ORG_ID")

mcp = FastMCP("marketing")


@mcp.tool()
async def create_campaign(
    name: str,
    type: str,
    description: str = None,
    status: str = 'draft'
) -> str:
    """Create a marketing campaign.
    
    Args:
        name: The campaign name.
        type: Campaign type - must be one of: loyalty, referral, re-engagement,
              at risk, new customer, champion, about to sleep, lost, potential loyalist.
        description: Optional campaign description.
        status: Campaign status (default: 'draft').
    
    Returns:
        str: The UUID of the newly created campaign.
    """
    allowed_types = [
        'loyalty', 'referral', 're-engagement', 'at risk', 'new customer',
        'champion', 'about to sleep', 'lost', 'potential loyalist'
    ]
    if type not in allowed_types:
        raise ValueError(f"Invalid campaign type: {type}. Must be one of {allowed_types}")

    if not ORG_ID:
        raise RuntimeError("ORG_ID environment variable not set. Cannot create campaign without tenant context.")

    with SessionLocal() as session:
        result = session.execute(
            text(
                """
                INSERT INTO marketing_campaigns (name, type, description, status, org_id)
                VALUES (:name, :type, :description, :status, :org_id)
                RETURNING id
                """
            ),
            {
                "name": name,
                "type": type,
                "description": description,
                "status": status,
                "org_id": ORG_ID,
            },
        )
        session.commit()
        return str(result.fetchone()[0])


@mcp.tool()
async def send_campaign_email(
    campaign_id: str,
    customer_id: int,
    subject: str,
    body: str,
    status: str = 'sent',
    opened: bool = False
) -> str:
    """Record a campaign email send.
    
    This tool records the email in the campaigning_emails table. The actual
    email delivery is handled separately via the Gmail MCP server (GMAIL_SEND_EMAIL).
    
    Args:
        campaign_id: UUID of the campaign this email belongs to.
        customer_id: The customer ID to send the email to.
        subject: Email subject line.
        body: Email body content (HTML).
        status: Email status (default: 'sent').
        opened: Whether the email has been opened (default: False).
    
    Returns:
        str: Success message with subject and customer ID.
    """
    allowed_statuses = [
        'sent', 'failed', 'queued', 'opened', 'bounced', 'delivered', 'clicked', 'unsubscribed'
    ]
    if status not in allowed_statuses:
        raise ValueError(f"Invalid email status: {status}. Must be one of {allowed_statuses}")

    if not ORG_ID:
        raise RuntimeError("ORG_ID environment variable not set. Cannot send email without tenant context.")

    with SessionLocal() as session:
        # Look up the customer's email address, scoped to the tenant
        email_result = session.execute(
            text("SELECT email FROM crm WHERE customer_id = :customer_id AND org_id = :org_id"),
            {"customer_id": customer_id, "org_id": ORG_ID}
        ).fetchone()
        
        # Fallback: check the JSONB customers table if not found in crm
        if not email_result:
            email_result = session.execute(
                text("SELECT email FROM customers WHERE customer_id = :customer_id AND org_id = :org_id"),
                {"customer_id": customer_id, "org_id": ORG_ID}
            ).fetchone()
        
        email = email_result[0] if email_result else None

        # Check external Supabase connection mapping if email is still not resolved
        if not email:
            try:
                mapping_row = session.execute(
                    text(
                        """
                        SELECT m.*, c.encrypted_readonly_uri
                        FROM crm_customer_mappings m
                        JOIN tenant_data_connections c
                          ON c.connection_id = m.connection_id
                         AND c.org_id = m.org_id
                        WHERE m.org_id = :org_id AND m.status = 'approved' AND c.status = 'connected'
                        ORDER BY m.approved_at DESC NULLS LAST, m.updated_at DESC
                        LIMIT 1
                        """
                    ),
                    {"org_id": ORG_ID}
                ).fetchone()

                if mapping_row:
                    from backend.encryption import decrypt_token
                    import json

                    mapping_dict = dict(mapping_row._mapping)
                    field_map = mapping_dict.get("field_map", {})
                    if isinstance(field_map, str):
                        try:
                            field_map = json.loads(field_map)
                        except Exception:
                            field_map = {}

                    email_col = None
                    cust_id_col = None
                    for source_col, details in field_map.items():
                        if isinstance(details, dict):
                            canonical = details.get("canonical_field")
                            if canonical == "email":
                                email_col = source_col
                            elif canonical == "customer_id":
                                cust_id_col = source_col

                    if email_col:
                        readonly_uri = decrypt_token(mapping_dict["encrypted_readonly_uri"])
                        import psycopg

                        with psycopg.connect(readonly_uri) as ext_conn:
                            with ext_conn.cursor() as ext_cur:
                                from psycopg import sql
                                query_col = cust_id_col if cust_id_col else email_col
                                ext_cur.execute(
                                    sql.SQL("SELECT {} FROM {}.{} WHERE {} = %s LIMIT 1").format(
                                        sql.Identifier(email_col),
                                        sql.Identifier(mapping_dict["schema_name"]),
                                        sql.Identifier(mapping_dict["table_name"]),
                                        sql.Identifier(query_col)
                                    ),
                                    (str(customer_id),)
                                )
                                ext_row = ext_cur.fetchone()
                                if ext_row:
                                    email = ext_row[0]
            except Exception as e:
                logger.error(f"Failed to query external customer email: {e}")

        if not email:
            raise ValueError(f"No customer email resolved for ID: {customer_id}")

        # Send actual email via Google API if user's Gmail is integrated
        gmail_sent = False
        try:
            integration_row = session.execute(
                text("SELECT gmail_access_token, gmail_refresh_token FROM integrations WHERE org_id = :org_id"),
                {"org_id": ORG_ID}
            ).fetchone()

            if integration_row and integration_row[0]:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                from email.mime.text import MIMEText
                import base64
                from backend.encryption import decrypt_token

                access_token = decrypt_token(integration_row[0])
                refresh_token = decrypt_token(integration_row[1]) if integration_row[1] else None

                creds = Credentials(
                    token=access_token,
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
                    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
                )

                # Send Gmail message
                gmail_service = build('gmail', 'v1', credentials=creds)
                mime_msg = MIMEText(body, 'html')
                mime_msg['to'] = email
                mime_msg['subject'] = subject
                raw_message = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode('utf-8')

                gmail_service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
                gmail_sent = True
                logger.info(f"Successfully sent campaign email via Gmail API to {email}")
        except Exception as e:
            logger.error(f"Failed to send actual Gmail: {e}")

        final_status = "sent" if (status == "sent" or gmail_sent) else status
        session.execute(
            text(
                """
                INSERT INTO campaigning_emails (campaign_id, customer_id, email, subject, body, status, opened, org_id)
                VALUES (:campaign_id, :customer_id, :email, :subject, :body, :status, :opened, :org_id)
                """
            ),
            {
                "campaign_id": campaign_id,
                "customer_id": customer_id,
                "email": email,
                "subject": subject,
                "body": body,
                "status": final_status,
                "opened": opened,
                "org_id": ORG_ID,
            },
        )

        # Write audit log record
        session.execute(
            text(
                """
                INSERT INTO audit_logs (org_id, actor, action, details)
                VALUES (:org_id, :actor, :action, :details)
                """
            ),
            {
                "org_id": ORG_ID,
                "actor": "agent",
                "action": "campaign_email_send",
                "details": json.dumps({
                    "campaign_id": str(campaign_id),
                    "customer_id": customer_id,
                    "email": email,
                    "subject": subject,
                    "gmail_sent": gmail_sent
                })
            }
        )
        session.commit()

    send_method = "Gmail API" if gmail_sent else "recorded"
    return f"Successfully sent <{subject}> to customer <{customer_id}> ({email}) via {send_method}!"


@mcp.tool()
async def get_at_risk_customers(limit: int = 20, risk_level: str = "high") -> str:
    """List computed at-risk customer snapshots for this tenant.

    Args:
        limit: Maximum number of snapshots to return.
        risk_level: Filter by high, medium, low, unknown, or all.

    Returns:
        JSON string containing risk snapshots with explanations.
    """
    if not ORG_ID:
        raise RuntimeError("ORG_ID environment variable not set. Cannot read risk snapshots without tenant context.")

    allowed_levels = {"high", "medium", "low", "unknown", "all"}
    if risk_level not in allowed_levels:
        raise ValueError(f"Invalid risk_level: {risk_level}. Must be one of {sorted(allowed_levels)}")

    limit = max(1, min(int(limit), 100))
    with SessionLocal() as session:
        if risk_level == "all":
            rows = session.execute(
                text(
                    """
                    SELECT snapshot_id, external_customer_id, customer_label, risk_level,
                           risk_score, reasons, source_fields, computed_at
                    FROM customer_risk_snapshots
                    WHERE org_id = :org_id
                    ORDER BY risk_score DESC NULLS LAST, computed_at DESC
                    LIMIT :limit
                    """
                ),
                {"org_id": ORG_ID, "limit": limit},
            ).mappings().all()
        else:
            rows = session.execute(
                text(
                    """
                    SELECT snapshot_id, external_customer_id, customer_label, risk_level,
                           risk_score, reasons, source_fields, computed_at
                    FROM customer_risk_snapshots
                    WHERE org_id = :org_id AND risk_level = :risk_level
                    ORDER BY risk_score DESC NULLS LAST, computed_at DESC
                    LIMIT :limit
                    """
                ),
                {"org_id": ORG_ID, "risk_level": risk_level, "limit": limit},
            ).mappings().all()

    return json.dumps([dict(row) for row in rows], default=str)


@mcp.tool()
async def explain_customer_risk(snapshot_id: str) -> str:
    """Explain one computed customer risk snapshot.

    Args:
        snapshot_id: The UUID of a customer_risk_snapshots row.

    Returns:
        JSON string with customer label, risk level, score, reasons, and source fields.
    """
    if not ORG_ID:
        raise RuntimeError("ORG_ID environment variable not set. Cannot read risk snapshots without tenant context.")

    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT snapshot_id, external_customer_id, customer_label, risk_level,
                       risk_score, reasons, source_fields, computed_at
                FROM customer_risk_snapshots
                WHERE org_id = :org_id AND snapshot_id = :snapshot_id
                """
            ),
            {"org_id": ORG_ID, "snapshot_id": snapshot_id},
        ).mappings().first()

    if not row:
        raise ValueError("Risk snapshot not found for this organization.")
    return json.dumps(dict(row), default=str)


if __name__ == "__main__":
    mcp.run(transport="stdio")
