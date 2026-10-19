"""Pydantic schemas for CRM feature APIs."""

from typing import Any, Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "unknown"]
RiskSourceType = Literal["connected", "local"]


class RiskSnapshot(BaseModel):
    snapshot_id: str
    org_id: str
    connection_id: str | None
    mapping_id: str | None
    source_type: RiskSourceType = "connected"
    external_customer_id: str | None
    customer_label: str | None
    risk_level: RiskLevel
    risk_score: float | None
    reasons: list[str]
    source_fields: dict[str, Any]
    computed_at: str | None


class RiskRefreshResponse(BaseModel):
    refreshed: bool
    total_scored: int
    high_risk: int
    medium_risk: int
    low_risk: int
    unknown: int


class RiskListResponse(BaseModel):
    snapshots: list[RiskSnapshot]
    total: int


class RiskRefreshRequest(BaseModel):
    limit: int = Field(default=500, ge=1, le=2000)
