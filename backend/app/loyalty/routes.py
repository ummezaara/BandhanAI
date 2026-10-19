"""HTTP endpoints for the tenant owner's loyalty program."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg.errors import UniqueViolation

from backend.app.loyalty import service
from backend.app.loyalty.schemas import (
    BonusCampaignCreateRequest,
    BonusCampaignStatusRequest,
    DemoTransactionRequest,
    IdentityLinkRequest,
    ManualAdjustmentRequest,
    PurchaseImportRequest,
    RedemptionRequest,
    ReferralCreateRequest,
)
from backend.auth import get_current_user, get_org_id_for_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/loyalty", tags=["loyalty"])

_pg_pool = None


def set_pg_pool(pool):
    """Inject the application PostgreSQL pool at startup."""
    global _pg_pool
    _pg_pool = pool


def _get_pool():
    if _pg_pool is None:
        raise RuntimeError("PostgreSQL pool not initialized.")
    return _pg_pool


def _raise_loyalty_error(exc: service.LoyaltyError):
    if isinstance(exc, service.LoyaltyNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, service.InsufficientPoints):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def _tenant_context(user: dict) -> tuple[object, str, str]:
    pool = _get_pool()
    org_id = await get_org_id_for_user(user["sub"], pool)
    return pool, org_id, user["sub"]


@router.get("/summary")
async def loyalty_summary(
    loyalty_customer_id: str | None = None,
    user: dict = Depends(get_current_user),
):
    pool, org_id, _ = await _tenant_context(user)
    try:
        return await service.get_summary(pool, org_id, loyalty_customer_id)
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.get("/accounts")
async def loyalty_accounts(
    search: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_demo: bool = False,
    user: dict = Depends(get_current_user),
):
    pool, org_id, _ = await _tenant_context(user)
    return await service.list_accounts(
        pool,
        org_id,
        limit=limit,
        offset=offset,
        search=search.strip(),
        include_demo=include_demo,
    )


@router.get("/accounts/{loyalty_customer_id}")
async def loyalty_account(loyalty_customer_id: str, user: dict = Depends(get_current_user)):
    pool, org_id, _ = await _tenant_context(user)
    try:
        account = await service.get_account(pool, org_id, loyalty_customer_id)
        transactions = await service.list_transactions(pool, org_id, loyalty_customer_id, limit=50)
        return {"account": account, **transactions}
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.post("/accounts/{loyalty_customer_id}/identities")
async def link_customer_identity(
    loyalty_customer_id: str,
    req: IdentityLinkRequest,
    user: dict = Depends(get_current_user),
):
    pool, org_id, actor = await _tenant_context(user)
    try:
        return {
            "account": await service.link_identity(
                pool, org_id, loyalty_customer_id, req.identity.model_dump(), actor
            )
        }
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.get("/accounts/{loyalty_customer_id}/transactions")
async def loyalty_transactions(
    loyalty_customer_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    pool, org_id, _ = await _tenant_context(user)
    try:
        return await service.list_transactions(pool, org_id, loyalty_customer_id, limit, offset)
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.get("/expiry/upcoming")
async def loyalty_upcoming_expiries(
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    pool, org_id, _ = await _tenant_context(user)
    return {"expiries": await service.upcoming_expiries(pool, org_id, days)}


@router.post("/purchases/import")
async def import_verified_purchase(
    req: PurchaseImportRequest,
    user: dict = Depends(get_current_user),
):
    pool, org_id, actor = await _tenant_context(user)
    try:
        return await service.import_purchase(pool, org_id, req.model_dump(), actor)
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.post("/adjustments")
async def create_manual_adjustment(
    req: ManualAdjustmentRequest,
    user: dict = Depends(get_current_user),
):
    pool, org_id, actor = await _tenant_context(user)
    try:
        return await service.adjust_points(pool, org_id, req.model_dump(), actor)
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.post("/demo/transactions")
async def create_demo_transaction(
    req: DemoTransactionRequest,
    user: dict = Depends(get_current_user),
):
    pool, org_id, actor = await _tenant_context(user)
    try:
        return await service.create_demo_transaction(pool, org_id, req.model_dump(), actor)
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.get("/rewards")
async def loyalty_rewards(user: dict = Depends(get_current_user)):
    pool, org_id, _ = await _tenant_context(user)
    summary = await service.get_summary(pool, org_id)
    return {"rewards": summary["rewards"]}


@router.post("/accounts/{loyalty_customer_id}/redemptions")
async def redeem_loyalty_reward(
    loyalty_customer_id: str,
    req: RedemptionRequest,
    user: dict = Depends(get_current_user),
):
    pool, org_id, actor = await _tenant_context(user)
    try:
        return await service.redeem_reward(
            pool, org_id, loyalty_customer_id, req.reward_id, req.idempotency_key, actor
        )
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.get("/referrals")
async def loyalty_referrals(user: dict = Depends(get_current_user)):
    pool, org_id, _ = await _tenant_context(user)
    return {"referrals": await service.list_referrals(pool, org_id)}


@router.post("/referrals")
async def create_loyalty_referral(
    req: ReferralCreateRequest,
    user: dict = Depends(get_current_user),
):
    pool, org_id, actor = await _tenant_context(user)
    try:
        return await service.create_referral(pool, org_id, req.model_dump(), actor)
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)
    except UniqueViolation as exc:
        logger.exception("Failed to create loyalty referral")
        raise HTTPException(status_code=409, detail="Referral code or referred customer is already in use.") from exc


@router.get("/bonus-campaigns")
async def loyalty_bonus_campaigns(user: dict = Depends(get_current_user)):
    pool, org_id, _ = await _tenant_context(user)
    return {"campaigns": await service.list_bonus_campaigns(pool, org_id)}


@router.post("/bonus-campaigns")
async def create_loyalty_bonus_campaign(
    req: BonusCampaignCreateRequest,
    user: dict = Depends(get_current_user),
):
    pool, org_id, actor = await _tenant_context(user)
    try:
        return await service.create_bonus_campaign(pool, org_id, req.model_dump(), actor)
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.patch("/bonus-campaigns/{campaign_id}/status")
async def set_loyalty_bonus_campaign_status(
    campaign_id: str,
    req: BonusCampaignStatusRequest,
    user: dict = Depends(get_current_user),
):
    pool, org_id, actor = await _tenant_context(user)
    try:
        return await service.update_bonus_campaign_status(
            pool, org_id, campaign_id, req.status, actor
        )
    except service.LoyaltyError as exc:
        _raise_loyalty_error(exc)


@router.post("/expiry/process")
async def process_loyalty_expiries(user: dict = Depends(get_current_user)):
    pool, org_id, actor = await _tenant_context(user)
    return await service.process_expiries(pool, org_id, actor)
