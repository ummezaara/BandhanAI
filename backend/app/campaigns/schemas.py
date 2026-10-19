"""Pydantic models for campaign management, generation, and recipient workflows."""

from typing import Any, Literal
from pydantic import BaseModel, Field

RecipientStatus = Literal["pending", "approved", "excluded", "sent", "failed"]


class CampaignRecipient(BaseModel):
    recipient_id: str
    campaign_id: str
    org_id: str
    customer_name: str | None = None
    customer_email: str
    subject: str | None = None
    body: str | None = None
    recommended_products: list[dict[str, Any]] = Field(default_factory=list)
    status: RecipientStatus
    sent_at: str | None = None
    created_at: str | None = None


class CampaignRecipientCreate(BaseModel):
    customer_name: str | None = None
    customer_email: str = Field(..., min_length=3)
    subject: str | None = None
    body: str | None = None
    recommended_products: list[dict[str, Any]] = Field(default_factory=list)
    status: RecipientStatus = "pending"


class CampaignRecipientsSaveRequest(BaseModel):
    recipients: list[CampaignRecipientCreate]


class CampaignRecipientsResponse(BaseModel):
    recipients: list[CampaignRecipient]
    total: int


class CampaignRecipientStatusRequest(BaseModel):
    status: RecipientStatus
    subject: str | None = None
    body: str | None = None


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    type: str = Field(
        ...,
        description="Campaign type: loyalty, referral, re-engagement, at risk, new customer, champion, about to sleep, lost, potential loyalist",
    )
    description: str | None = None
    target_criteria: str | None = None


class Campaign(BaseModel):
    id: str
    org_id: str
    name: str
    type: str
    description: str | None = None
    status: str
    created_at: str | None = None
    total_recipients: int = 0
    sent_recipients: int = 0
    pending_recipients: int = 0


class CampaignsListResponse(BaseModel):
    campaigns: list[Campaign]
    total: int


class CampaignGenerateRequest(BaseModel):
    target_prompt: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class CampaignSendBatchRequest(BaseModel):
    recipient_ids: list[str] | None = Field(
        default=None,
        description="Optional specific recipient IDs to send. If omitted/empty, sends all pending/approved recipients.",
    )


class CampaignSendBatchResponse(BaseModel):
    total: int
    sent: int
    failed: int
    method: str
    message: str
    details: list[dict[str, Any]] = Field(default_factory=list)
