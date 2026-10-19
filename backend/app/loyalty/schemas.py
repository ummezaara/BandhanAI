"""Request and response models for loyalty operations."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SourceType = Literal["platform", "external", "import", "manual", "demo"]


class CustomerIdentity(BaseModel):
    source_type: SourceType
    source_namespace: str = Field(min_length=1, max_length=200)
    source_customer_key: str = Field(min_length=1, max_length=300)
    display_name: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=320)

    @model_validator(mode="after")
    def validate_identity_values(self):
        if not self.source_namespace.strip() or not self.source_customer_key.strip():
            raise ValueError("Customer identity namespace and source key cannot be blank.")
        return self


class PurchaseImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer: CustomerIdentity
    source_namespace: str = Field(min_length=1, max_length=200)
    source_event_key: str = Field(min_length=1, max_length=300)
    amount_inr: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    purchased_at: datetime
    verification_reference: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_source(self):
        if self.customer.source_type not in {"platform", "external", "import"}:
            raise ValueError("Purchase events require a platform, external, or imported customer identity.")
        if self.purchased_at.tzinfo is None or self.purchased_at.utcoffset() is None:
            raise ValueError("Purchase timestamps must include a timezone.")
        if not self.source_namespace.strip() or not self.source_event_key.strip():
            raise ValueError("Purchase event namespace and source key cannot be blank.")
        if not self.verification_reference.strip():
            raise ValueError("A verification reference is required for imported purchase events.")
        return self


class ManualAdjustmentRequest(BaseModel):
    loyalty_customer_id: str | None = None
    customer: CustomerIdentity | None = None
    points_delta: Decimal = Field(ne=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=3, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=300)

    @model_validator(mode="after")
    def validate_customer(self):
        if self.points_delta == 0:
            raise ValueError("Adjustment points must be non-zero.")
        if (self.loyalty_customer_id is None) == (self.customer is None):
            raise ValueError("Specify exactly one loyalty account ID or customer identity.")
        if self.customer and self.customer.source_type == "demo":
            raise ValueError("Use the demo transaction endpoint for demo identities.")
        if not self.reason.strip() or not self.idempotency_key.strip():
            raise ValueError("Adjustment reason and idempotency key cannot be blank.")
        return self


class DemoTransactionRequest(BaseModel):
    customer: CustomerIdentity
    points_delta: Decimal = Field(ne=0, max_digits=12, decimal_places=2)
    description: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=300)

    @model_validator(mode="after")
    def validate_demo_customer(self):
        if self.points_delta == 0:
            raise ValueError("Demo transaction points must be non-zero.")
        if self.customer.source_type != "demo":
            raise ValueError("Demo transactions require a demo customer identity.")
        if not self.description.strip() or not self.idempotency_key.strip():
            raise ValueError("Demo description and idempotency key cannot be blank.")
        return self


class RedemptionRequest(BaseModel):
    reward_id: str
    idempotency_key: str = Field(min_length=8, max_length=300)


class ReferralCreateRequest(BaseModel):
    referrer: CustomerIdentity
    referred: CustomerIdentity
    referral_code: str = Field(min_length=3, max_length=100)

    @model_validator(mode="after")
    def validate_customers(self):
        if self.referrer.source_type == "demo" or self.referred.source_type == "demo":
            raise ValueError("Demo identities cannot participate in referrals.")
        if (
            self.referrer.source_type == self.referred.source_type
            and self.referrer.source_namespace == self.referred.source_namespace
            and self.referrer.source_customer_key == self.referred.source_customer_key
        ):
            raise ValueError("A customer cannot refer themselves.")
        return self


class IdentityLinkRequest(BaseModel):
    identity: CustomerIdentity

    @model_validator(mode="after")
    def validate_identity(self):
        if self.identity.source_type == "demo":
            raise ValueError("Demo identities cannot be linked to live loyalty accounts.")
        return self


class BonusCampaignCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    points_multiplier: Decimal = Field(gt=1, max_digits=8, decimal_places=2)
    starts_at: datetime
    ends_at: datetime
    idempotency_key: str = Field(min_length=8, max_length=300)

    @model_validator(mode="after")
    def validate_period(self):
        if (
            self.starts_at.tzinfo is None
            or self.starts_at.utcoffset() is None
            or self.ends_at.tzinfo is None
            or self.ends_at.utcoffset() is None
        ):
            raise ValueError("Bonus campaign timestamps must include a timezone.")
        if self.ends_at <= self.starts_at:
            raise ValueError("Bonus campaign end must be later than its start.")
        if not self.idempotency_key.strip():
            raise ValueError("Bonus campaign idempotency key cannot be blank.")
        return self


class BonusCampaignStatusRequest(BaseModel):
    status: Literal["draft", "active", "paused", "ended"]


class AccountListResponse(BaseModel):
    accounts: list[dict]
    total: int


class LoyaltySummaryResponse(BaseModel):
    program: dict
    tiers: list[dict]
    rewards: list[dict]
    account: dict | None = None


class TransactionListResponse(BaseModel):
    transactions: list[dict]
    total: int


class MutationResponse(BaseModel):
    account: dict
    transaction: dict | None = None
    purchase_event: dict | None = None
    referral: dict | None = None
    redemption: dict | None = None
    duplicate: bool = False
