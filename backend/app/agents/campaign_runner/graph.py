"""Campaign runner workflow entry points."""

from __future__ import annotations

from backend.app.agents.campaign_runner.nodes import (
    CampaignRunnerState,
    build_review_payload,
    persist_generated_emails,
)


async def review_campaign_plan(state: CampaignRunnerState) -> dict:
    """Return the payload the UI should show before campaign execution."""
    return build_review_payload(state)


async def save_email_previews(pg_pool, state: CampaignRunnerState) -> list[dict]:
    """Persist generated campaign email previews after approval."""
    return await persist_generated_emails(pg_pool, state)
