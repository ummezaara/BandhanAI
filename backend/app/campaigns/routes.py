"""HTTP routes for campaign management, generation, recipient previews, and batch execution."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.audit.service import log_audit_action
from backend.app.campaigns import service
from backend.app.campaigns.schemas import (
    Campaign,
    CampaignCreate,
    CampaignGenerateRequest,
    CampaignRecipient,
    CampaignRecipientStatusRequest,
    CampaignRecipientsResponse,
    CampaignRecipientsSaveRequest,
    CampaignsListResponse,
    CampaignSendBatchRequest,
    CampaignSendBatchResponse,
)
from backend.auth import get_current_user, get_org_id_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

_pg_pool = None


def set_pg_pool(pool):
    global _pg_pool
    _pg_pool = pool


def _get_pool():
    if _pg_pool is None:
        raise RuntimeError("PostgreSQL pool not initialized.")
    return _pg_pool


# ============================================================================
# Campaign Management
# ============================================================================


@router.get("", response_model=CampaignsListResponse)
async def list_user_campaigns(
    user: dict = Depends(get_current_user),
):
    """List all marketing campaigns for the authenticated tenant."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    campaigns = await service.list_campaigns(pool, org_id)
    return {"campaigns": campaigns, "total": len(campaigns)}


@router.post("", response_model=Campaign)
async def create_user_campaign(
    req: CampaignCreate,
    user: dict = Depends(get_current_user),
):
    """Create a new marketing campaign."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        campaign = await service.create_campaign(
            pool, org_id, name=req.name, campaign_type=req.type, description=req.description
        )
        await log_audit_action(
            pool=pool,
            org_id=org_id,
            actor="user",
            action="campaign_create",
            details={"campaign_id": campaign["id"], "name": campaign["name"], "type": campaign["type"]},
        )
        return campaign
    except Exception as exc:
        logger.exception("Failed to create campaign")
        raise HTTPException(status_code=500, detail=f"Failed to create campaign: {exc}")


@router.get("/{campaign_id}", response_model=Campaign)
async def get_user_campaign(
    campaign_id: str,
    user: dict = Depends(get_current_user),
):
    """Get single campaign details and recipient stats."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        return await service.get_campaign(pool, org_id, campaign_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")


@router.delete("/{campaign_id}")
async def delete_user_campaign(
    campaign_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete a marketing campaign."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    deleted = await service.delete_campaign(pool, org_id, campaign_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return {"status": "success", "campaign_id": campaign_id}


# ============================================================================
# AI Recipient Generation & Batch Execution
# ============================================================================


@router.post("/{campaign_id}/generate", response_model=CampaignRecipientsResponse)
async def generate_recipients_for_campaign(
    campaign_id: str,
    req: CampaignGenerateRequest,
    user: dict = Depends(get_current_user),
):
    """Generate personalized HTML emails for target customers using LLM and preview them."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        saved = await service.generate_campaign_recipients(
            pool,
            org_id,
            campaign_id,
            target_prompt=req.target_prompt,
            limit=req.limit,
        )
        await log_audit_action(
            pool=pool,
            org_id=org_id,
            actor="user",
            action="campaign_recipients_generate",
            details={"campaign_id": campaign_id, "count": len(saved)},
        )
        return {"recipients": saved, "total": len(saved)}
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    except Exception as exc:
        logger.exception("Failed to generate campaign recipients")
        raise HTTPException(status_code=500, detail=f"Failed to generate campaign recipients: {exc}")


@router.post("/{campaign_id}/send", response_model=CampaignSendBatchResponse)
async def send_campaign_batch_endpoint(
    campaign_id: str,
    req: CampaignSendBatchRequest,
    user: dict = Depends(get_current_user),
):
    """Automatically send generated campaign emails to customers via Gmail API."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        res = await service.send_campaign_batch(
            pool, org_id, campaign_id, recipient_ids=req.recipient_ids
        )
        await log_audit_action(
            pool=pool,
            org_id=org_id,
            actor="user",
            action="campaign_batch_send",
            details={
                "campaign_id": campaign_id,
                "sent": res["sent"],
                "failed": res["failed"],
                "method": res["method"],
            },
        )
        return res
    except Exception as exc:
        logger.exception("Campaign batch send failed")
        raise HTTPException(status_code=500, detail=f"Campaign batch send failed: {exc}")


# ============================================================================
# Recipient Management Endpoints
# ============================================================================


@router.get("/{campaign_id}/recipients", response_model=CampaignRecipientsResponse)
async def get_campaign_recipients(
    campaign_id: str,
    user: dict = Depends(get_current_user),
):
    """Get all recipient previews for a campaign."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    recipients = await service.list_recipients(pool, org_id, campaign_id)
    return {"recipients": recipients, "total": len(recipients)}


@router.post("/{campaign_id}/recipients", response_model=CampaignRecipientsResponse)
async def save_campaign_recipients(
    campaign_id: str,
    req: CampaignRecipientsSaveRequest,
    user: dict = Depends(get_current_user),
):
    """Save or add recipient previews to a campaign."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        saved = await service.save_recipients(
            pool,
            org_id,
            campaign_id,
            [recipient.model_dump() for recipient in req.recipients],
        )
        await log_audit_action(
            pool=pool,
            org_id=org_id,
            actor="user",
            action="campaign_recipients_save",
            details={"campaign_id": campaign_id, "count": len(saved)},
        )
        return {"recipients": saved, "total": len(saved)}
    except Exception as exc:
        logger.exception("Failed to save campaign recipients")
        raise HTTPException(status_code=500, detail=f"Failed to save recipients: {exc}")


@router.post("/recipients/{recipient_id}/status", response_model=CampaignRecipient)
async def update_campaign_recipient_status(
    recipient_id: str,
    req: CampaignRecipientStatusRequest,
    user: dict = Depends(get_current_user),
):
    """Update single recipient status or body/subject content."""
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)

    try:
        return await service.update_recipient_status(
            pool, org_id, recipient_id, status=req.status, subject=req.subject, body=req.body
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign recipient not found")
