"""Small reusable campaign runner helpers.

The full LangGraph runner can build on these helpers once the frontend approval
flow is ready. They are intentionally side-effect-light except for persistence.
"""

from __future__ import annotations

from typing import TypedDict

from backend.app.campaigns.service import save_recipients


class CampaignRunnerState(TypedDict, total=False):
    campaign_id: str
    org_id: str
    campaign_intent: str
    schema_metadata: dict
    target_customers: list[dict]
    recommended_products: dict
    generated_emails: list[dict]
    approved: bool


def build_review_payload(state: CampaignRunnerState) -> dict:
    customers = state.get("target_customers", [])
    recommendations = state.get("recommended_products", {})
    return {
        "campaign_id": state.get("campaign_id"),
        "intent": state.get("campaign_intent", ""),
        "target_customer_count": len(customers),
        "recommendation_groups": len(recommendations),
        "sample_customers": customers[:5],
    }


async def persist_generated_emails(pg_pool, state: CampaignRunnerState) -> list[dict]:
    campaign_id = state["campaign_id"]
    org_id = state["org_id"]
    recipients = []
    for email in state.get("generated_emails", []):
        customer = email.get("customer") or {}
        recipients.append(
            {
                "customer_name": customer.get("name"),
                "customer_email": customer.get("email") or email.get("email"),
                "subject": email.get("subject"),
                "body": email.get("body"),
                "recommended_products": email.get("recommended_products") or [],
            }
        )
    return await save_recipients(pg_pool, org_id, campaign_id, recipients)
