"""Transactional loyalty operations backed by the platform PostgreSQL database."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from dateutil.relativedelta import relativedelta

from backend.app.audit.service import insert_audit_action

logger = logging.getLogger(__name__)
POINT = Decimal("0.01")
ZERO = Decimal("0.00")


class LoyaltyError(Exception):
    """Base exception for expected loyalty operation failures."""


class LoyaltyNotFound(LoyaltyError):
    pass


class InsufficientPoints(LoyaltyError):
    pass


def points(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(POINT, rounding=ROUND_HALF_UP)


def tier_for_lifetime_points(value: Decimal, tiers: list[dict]) -> dict:
    lifetime = points(value)
    for tier in sorted(tiers, key=lambda item: Decimal(item["min_lifetime_points"]), reverse=True):
        minimum = Decimal(tier["min_lifetime_points"])
        maximum = tier.get("max_lifetime_points")
        if lifetime >= minimum and (maximum is None or lifetime <= Decimal(maximum)):
            return tier
    raise LoyaltyError("No configured loyalty tier covers this lifetime point total.")


def calculate_purchase_points(
    amount_inr: Decimal,
    purchase_amount: Decimal,
    base_points: Decimal,
    tier_multiplier: Decimal,
    bonus_multiplier: Decimal,
) -> tuple[Decimal, Decimal]:
    """Return base award and incremental bonus award, rounded to two decimals."""
    base = points(amount_inr / purchase_amount * base_points * tier_multiplier)
    total = points(amount_inr / purchase_amount * base_points * tier_multiplier * bonus_multiplier)
    return base, max(total - base, ZERO)


def expiry_timestamp(earned_at: datetime, months: int) -> datetime:
    return earned_at + relativedelta(months=months)


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_account(row: dict | None) -> dict | None:
    if row is None:
        return None
    serialized = {
        "loyalty_customer_id": str(row["loyalty_customer_id"]),
        "customer_label": row.get("display_name"),
        "email": row.get("email"),
        "current_balance": float(row["available_points"]),
        "lifetime_eligible_points": float(row["lifetime_eligible_points"]),
        "tier": row["current_tier"],
        "is_demo": bool(row.get("is_demo", False)),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }
    if row.get("identities") is not None:
        identities = row["identities"]
        if isinstance(identities, str):
            identities = json.loads(identities)
        serialized["identities"] = identities
    return serialized


def _serialize_transaction(row: dict) -> dict:
    return {
        "transaction_id": str(row["transaction_id"]),
        "loyalty_customer_id": str(row["loyalty_customer_id"]),
        "transaction_type": row["transaction_type"],
        "points_delta": float(row["points_delta"]),
        "lifetime_points_delta": float(row.get("lifetime_points_delta", 0)),
        "description": row.get("description"),
        "source_reference": row.get("source_reference"),
        "is_demo": bool(row.get("is_demo", False)),
        "expires_at": _iso(row.get("expires_at")),
        "created_at": _iso(row.get("created_at")),
    }


def _serialize_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {key: str(value) if isinstance(value, UUID) else _iso(value) for key, value in dict(row).items()}


async def _lock_identity(conn, org_id: str, identity: dict) -> None:
    lock_key = ":".join(
        (org_id, identity["source_type"], identity["source_namespace"], identity["source_customer_key"])
    )
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))


async def _lock_idempotency(conn, org_id: str, scope: str, key: str) -> None:
    lock_key = f"{org_id}:{scope}:{key}"
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))


async def _validate_external_namespace(conn, org_id: str, identity: dict) -> None:
    if identity["source_type"] != "external":
        return
    try:
        connection_id = UUID(identity["source_namespace"])
    except ValueError as exc:
        raise LoyaltyError("External customer identities must use their saved connection ID as the namespace.") from exc
    result = await conn.execute(
        """
        SELECT 1 FROM public.tenant_data_connections
        WHERE org_id = %s AND connection_id = %s
        """,
        (org_id, str(connection_id)),
    )
    if not await result.fetchone():
        raise LoyaltyNotFound("Connected external data source not found for this tenant.")


async def _resolve_identity(conn, org_id: str, identity: dict, create: bool = True) -> dict:
    await _validate_external_namespace(conn, org_id, identity)
    await _lock_identity(conn, org_id, identity)
    result = await conn.execute(
        """
        SELECT a.*
        FROM public.loyalty_customer_identities i
        JOIN public.loyalty_customer_accounts a
          ON a.org_id = i.org_id AND a.loyalty_customer_id = i.loyalty_customer_id
        WHERE i.org_id = %s
          AND i.source_type = %s
          AND i.source_namespace = %s
          AND i.source_customer_key = %s
        """,
        (
            org_id,
            identity["source_type"],
            identity["source_namespace"],
            identity["source_customer_key"],
        ),
    )
    account = await result.fetchone()
    if account:
        return dict(account)
    if not create:
        raise LoyaltyNotFound("Loyalty customer identity not found.")

    is_demo = identity["source_type"] == "demo"
    result = await conn.execute(
        """
        INSERT INTO public.loyalty_customer_accounts (org_id, display_name, email, is_demo)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (org_id, identity.get("display_name"), identity.get("email"), is_demo),
    )
    account = dict(await result.fetchone())
    await conn.execute(
        """
        INSERT INTO public.loyalty_customer_identities (
            org_id, loyalty_customer_id, source_type, source_namespace, source_customer_key
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            org_id,
            account["loyalty_customer_id"],
            identity["source_type"],
            identity["source_namespace"],
            identity["source_customer_key"],
        ),
    )
    return account


async def _get_account(conn, org_id: str, loyalty_customer_id: str, lock: bool = False) -> dict:
    suffix = " FOR UPDATE" if lock else ""
    result = await conn.execute(
        f"""
        SELECT * FROM public.loyalty_customer_accounts
        WHERE org_id = %s AND loyalty_customer_id = %s{suffix}
        """,
        (org_id, loyalty_customer_id),
    )
    row = await result.fetchone()
    if not row:
        raise LoyaltyNotFound("Loyalty account not found.")
    return dict(row)


async def _get_tiers(conn, org_id: str) -> list[dict]:
    result = await conn.execute(
        """
        SELECT tier, min_lifetime_points, max_lifetime_points, points_multiplier
        FROM public.loyalty_tier_rules
        WHERE org_id = %s
        ORDER BY min_lifetime_points
        """,
        (org_id,),
    )
    return [dict(row) for row in await result.fetchall()]


async def _refresh_account(
    conn, org_id: str, loyalty_customer_id: str, balance: Decimal, lifetime: Decimal
) -> dict:
    balance = points(balance)
    lifetime = points(lifetime)
    if balance < ZERO or lifetime < ZERO:
        raise LoyaltyError("Loyalty balance and lifetime points cannot be negative.")
    tier = tier_for_lifetime_points(lifetime, await _get_tiers(conn, org_id))
    result = await conn.execute(
        """
        UPDATE public.loyalty_customer_accounts
        SET available_points = %s,
            lifetime_eligible_points = %s,
            current_tier = %s,
            updated_at = now()
        WHERE org_id = %s AND loyalty_customer_id = %s
        RETURNING *
        """,
        (balance, lifetime, tier["tier"], org_id, loyalty_customer_id),
    )
    return dict(await result.fetchone())


async def _insert_transaction(
    conn,
    *,
    org_id: str,
    account: dict,
    transaction_type: str,
    points_delta: Decimal,
    lifetime_delta: Decimal,
    idempotency_key: str,
    description: str,
    actor_auth_uid: str | None,
    source_reference: str | None = None,
    metadata: dict | None = None,
    expires_at: datetime | None = None,
    is_demo: bool = False,
) -> dict:
    result = await conn.execute(
        """
        INSERT INTO public.loyalty_transactions (
            org_id, loyalty_customer_id, transaction_type, points_delta,
            lifetime_points_delta, idempotency_key, source_reference,
            description, metadata, is_demo, actor_auth_uid, expires_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            org_id,
            account["loyalty_customer_id"],
            transaction_type,
            points(points_delta),
            points(lifetime_delta),
            idempotency_key,
            source_reference,
            description,
            json.dumps(metadata or {}),
            is_demo,
            actor_auth_uid,
            expires_at,
        ),
    )
    return dict(await result.fetchone())


async def _allocate_consumption(
    conn, org_id: str, account_id: str, consuming_transaction_id: str, amount: Decimal, now: datetime
) -> None:
    remaining = points(amount)
    result = await conn.execute(
        """
        SELECT t.transaction_id, t.points_delta,
               t.points_delta - COALESCE(SUM(a.points_allocated), 0) AS remaining_points
        FROM public.loyalty_transactions t
        LEFT JOIN public.loyalty_point_allocations a
          ON a.org_id = t.org_id AND a.earning_transaction_id = t.transaction_id
        WHERE t.org_id = %s
          AND t.loyalty_customer_id = %s
          AND t.points_delta > 0
          AND t.is_demo = FALSE
          AND (t.expires_at IS NULL OR t.expires_at > %s)
        GROUP BY t.transaction_id
        HAVING t.points_delta - COALESCE(SUM(a.points_allocated), 0) > 0
        ORDER BY t.expires_at ASC NULLS LAST, t.created_at ASC, t.transaction_id
        """,
        (org_id, account_id, now),
    )
    lots = await result.fetchall()
    for lot in lots:
        if remaining <= ZERO:
            break
        available = points(lot["remaining_points"])
        used = min(remaining, available)
        await conn.execute(
            """
            INSERT INTO public.loyalty_point_allocations (
                org_id, loyalty_customer_id, earning_transaction_id,
                consuming_transaction_id, points_allocated
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (org_id, account_id, lot["transaction_id"], consuming_transaction_id, used),
        )
        remaining = points(remaining - used)
    if remaining > ZERO:
        raise InsufficientPoints("Available unexpired point lots do not cover this transaction.")


async def _audit(conn, org_id: str, actor: str, action: str, details: dict) -> None:
    await insert_audit_action(conn, org_id, actor, action, details)


async def get_summary(pg_pool, org_id: str, loyalty_customer_id: str | None = None) -> dict:
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            settings_result = await conn.execute(
                """
                SELECT purchase_amount, base_points, point_expiry_months,
                       referrer_reward_points, referred_reward_points
                FROM public.loyalty_program_settings WHERE org_id = %s
                """,
                (org_id,),
            )
            settings = await settings_result.fetchone()
            if not settings:
                raise LoyaltyError("Loyalty program configuration is missing for this tenant.")
            tiers = await _get_tiers(conn, org_id)
            reward_result = await conn.execute(
                """
                SELECT reward_id, name, points_cost, reward_value, currency
                FROM public.loyalty_rewards
                WHERE org_id = %s AND is_active = TRUE
                ORDER BY points_cost
                """,
                (org_id,),
            )
            rewards = [_serialize_row(row) for row in await reward_result.fetchall()]
            account = None
            if loyalty_customer_id:
                account = await _get_account(conn, org_id, loyalty_customer_id)
    return {
        "program": _serialize_row(dict(settings)),
        "tiers": [_serialize_row(row) for row in tiers],
        "rewards": rewards,
        "account": _serialize_account(account),
    }


async def list_accounts(
    pg_pool,
    org_id: str,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    include_demo: bool = False,
) -> dict:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT loyalty_customer_id, display_name, email, available_points,
                   lifetime_eligible_points, current_tier, is_demo, created_at, updated_at
            FROM public.loyalty_customer_accounts
            WHERE org_id = %s AND (%s OR is_demo = FALSE)
              AND (%s = '' OR display_name ILIKE %s OR email ILIKE %s)
            ORDER BY updated_at DESC
            LIMIT %s OFFSET %s
            """,
            (org_id, include_demo, search, f"%{search}%", f"%{search}%", limit, offset),
        )
        accounts = [_serialize_account(dict(row)) for row in await result.fetchall()]
        total_result = await conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM public.loyalty_customer_accounts
            WHERE org_id = %s AND (%s OR is_demo = FALSE)
              AND (%s = '' OR display_name ILIKE %s OR email ILIKE %s)
            """,
            (org_id, include_demo, search, f"%{search}%", f"%{search}%"),
        )
        total = (await total_result.fetchone())["total"]
    return {"accounts": accounts, "total": total}


async def get_account(pg_pool, org_id: str, loyalty_customer_id: str) -> dict:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT a.*,
                   COALESCE(
                       jsonb_agg(jsonb_build_object(
                           'source_type', i.source_type,
                           'source_namespace', i.source_namespace,
                           'source_customer_key', i.source_customer_key
                       )) FILTER (WHERE i.identity_id IS NOT NULL),
                       '[]'::jsonb
                   ) AS identities
            FROM public.loyalty_customer_accounts a
            LEFT JOIN public.loyalty_customer_identities i
              ON i.org_id = a.org_id AND i.loyalty_customer_id = a.loyalty_customer_id
            WHERE a.org_id = %s AND a.loyalty_customer_id = %s
            GROUP BY a.loyalty_customer_id
            """,
            (org_id, loyalty_customer_id),
        )
        account = await result.fetchone()
        if not account:
            raise LoyaltyNotFound("Loyalty account not found.")
    return _serialize_account(account)


async def link_identity(pg_pool, org_id: str, loyalty_customer_id: str, identity: dict, actor: str) -> dict:
    if identity["source_type"] == "demo":
        raise LoyaltyError("Demo identities cannot be linked to live loyalty accounts.")
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            account = await _get_account(conn, org_id, loyalty_customer_id, lock=True)
            if account["is_demo"]:
                raise LoyaltyError("Demo accounts cannot be linked to live customer identities.")
            await _validate_external_namespace(conn, org_id, identity)
            await _lock_identity(conn, org_id, identity)
            result = await conn.execute(
                """
                SELECT loyalty_customer_id
                FROM public.loyalty_customer_identities
                WHERE org_id = %s AND source_type = %s
                  AND source_namespace = %s AND source_customer_key = %s
                """,
                (org_id, identity["source_type"], identity["source_namespace"], identity["source_customer_key"]),
            )
            existing = await result.fetchone()
            if existing and str(existing["loyalty_customer_id"]) != str(loyalty_customer_id):
                raise LoyaltyError("This source identity is already linked to another loyalty account.")
            if not existing:
                await conn.execute(
                    """
                    INSERT INTO public.loyalty_customer_identities (
                        org_id, loyalty_customer_id, source_type, source_namespace, source_customer_key
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (org_id, loyalty_customer_id, identity["source_type"], identity["source_namespace"], identity["source_customer_key"]),
                )
            if identity.get("display_name") or identity.get("email"):
                result = await conn.execute(
                    """
                    UPDATE public.loyalty_customer_accounts
                    SET display_name = COALESCE(display_name, %s),
                        email = COALESCE(email, %s),
                        updated_at = now()
                    WHERE org_id = %s AND loyalty_customer_id = %s
                    RETURNING *
                    """,
                    (identity.get("display_name"), identity.get("email"), org_id, loyalty_customer_id),
                )
                account = dict(await result.fetchone())
            await _audit(
                conn, org_id, actor, "loyalty_identity_link",
                {"loyalty_customer_id": str(loyalty_customer_id), "source_type": identity["source_type"]},
            )
    return _serialize_account(account)


async def list_transactions(
    pg_pool, org_id: str, loyalty_customer_id: str, limit: int = 50, offset: int = 0
) -> dict:
    async with pg_pool.connection() as conn:
        account = await _get_account(conn, org_id, loyalty_customer_id)
        is_demo = bool(account["is_demo"])
        result = await conn.execute(
            """
            SELECT * FROM public.loyalty_transactions
            WHERE org_id = %s AND loyalty_customer_id = %s AND is_demo = %s
            ORDER BY created_at DESC, transaction_id
            LIMIT %s OFFSET %s
            """,
            (org_id, loyalty_customer_id, is_demo, limit, offset),
        )
        transactions = [_serialize_transaction(dict(row)) for row in await result.fetchall()]
        count_result = await conn.execute(
            """
            SELECT COUNT(*) AS total FROM public.loyalty_transactions
            WHERE org_id = %s AND loyalty_customer_id = %s AND is_demo = %s
            """,
            (org_id, loyalty_customer_id, is_demo),
        )
        total = (await count_result.fetchone())["total"]
    return {"transactions": transactions, "total": total}


async def upcoming_expiries(pg_pool, org_id: str, days: int = 30) -> list[dict]:
    now = datetime.now(timezone.utc)
    cutoff = now + relativedelta(days=days)
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT t.transaction_id AS earning_transaction_id,
                   t.loyalty_customer_id,
                   a.display_name,
                   t.expires_at,
                   t.points_delta - COALESCE(SUM(pa.points_allocated), 0) AS points_remaining
            FROM public.loyalty_transactions t
            JOIN public.loyalty_customer_accounts a
              ON a.org_id = t.org_id AND a.loyalty_customer_id = t.loyalty_customer_id
            LEFT JOIN public.loyalty_point_allocations pa
              ON pa.org_id = t.org_id AND pa.earning_transaction_id = t.transaction_id
            WHERE t.org_id = %s AND t.is_demo = FALSE AND a.is_demo = FALSE
              AND t.points_delta > 0 AND t.expires_at > %s AND t.expires_at <= %s
            GROUP BY t.transaction_id, a.display_name
            HAVING t.points_delta - COALESCE(SUM(pa.points_allocated), 0) > 0
            ORDER BY t.expires_at, t.loyalty_customer_id
            """,
            (org_id, now, cutoff),
        )
        rows = await result.fetchall()
    return [
        {
            "earning_transaction_id": str(row["earning_transaction_id"]),
            "loyalty_customer_id": str(row["loyalty_customer_id"]),
            "customer_label": row["display_name"],
            "expires_at": _iso(row["expires_at"]),
            "points_remaining": float(row["points_remaining"]),
        }
        for row in rows
    ]


async def _load_expiry_months(conn, org_id: str) -> int:
    result = await conn.execute(
        "SELECT point_expiry_months FROM public.loyalty_program_settings WHERE org_id = %s",
        (org_id,),
    )
    row = await result.fetchone()
    if not row:
        raise LoyaltyError("Loyalty program configuration is missing for this tenant.")
    return int(row["point_expiry_months"])


async def _active_bonus_multiplier(conn, org_id: str, purchased_at: datetime) -> tuple[Decimal, dict | None]:
    result = await conn.execute(
        """
        SELECT bonus_campaign_id, name, points_multiplier
        FROM public.loyalty_bonus_campaigns
        WHERE org_id = %s AND status = 'active'
          AND starts_at <= %s AND ends_at > %s
        ORDER BY points_multiplier DESC, bonus_campaign_id
        LIMIT 1
        """,
        (org_id, purchased_at, purchased_at),
    )
    row = await result.fetchone()
    return (Decimal(row["points_multiplier"]), dict(row)) if row else (Decimal("1"), None)


async def _write_award(
    conn,
    org_id: str,
    account: dict,
    amount: Decimal,
    transaction_type: str,
    idempotency_key: str,
    description: str,
    actor: str,
    source_reference: str,
    expiry: datetime,
    metadata: dict | None = None,
    campaign_id: str | None = None,
) -> dict:
    if amount <= ZERO:
        raise LoyaltyError("An award must contain at least 0.01 points.")
    award_metadata = dict(metadata or {})
    if campaign_id:
        award_metadata["bonus_campaign_id"] = campaign_id
    transaction = await _insert_transaction(
        conn,
        org_id=org_id,
        account=account,
        transaction_type=transaction_type,
        points_delta=amount,
        lifetime_delta=amount,
        idempotency_key=idempotency_key,
        description=description,
        actor_auth_uid=actor,
        source_reference=source_reference,
        metadata=award_metadata,
        expires_at=expiry,
    )
    updated = await _refresh_account(
        conn,
        org_id,
        str(account["loyalty_customer_id"]),
        Decimal(account["available_points"]) + amount,
        Decimal(account["lifetime_eligible_points"]) + amount,
    )
    account.update(updated)
    await _audit(
        conn,
        org_id,
        actor,
        f"loyalty_{transaction_type}",
        {
            "transaction_id": str(transaction["transaction_id"]),
            "loyalty_customer_id": str(account["loyalty_customer_id"]),
            "points": str(amount),
        },
    )
    return transaction


async def _qualify_referral(
    conn, org_id: str, referred_account: dict, purchase_event_id: str, expiry_months: int, actor: str
) -> dict | None:
    result = await conn.execute(
        """
        SELECT * FROM public.loyalty_referrals
        WHERE org_id = %s AND referred_customer_id = %s AND status = 'pending'
        FOR UPDATE
        """,
        (org_id, referred_account["loyalty_customer_id"]),
    )
    referral = await result.fetchone()
    if not referral:
        return None
    referral = dict(referral)
    accounts_result = await conn.execute(
        """
        SELECT * FROM public.loyalty_customer_accounts
        WHERE org_id = %s AND loyalty_customer_id IN (%s, %s)
        ORDER BY loyalty_customer_id
        FOR UPDATE
        """,
        (org_id, referral["referrer_customer_id"], referral["referred_customer_id"]),
    )
    locked = {str(row["loyalty_customer_id"]): dict(row) for row in await accounts_result.fetchall()}
    settings_result = await conn.execute(
        """
        SELECT referrer_reward_points, referred_reward_points
        FROM public.loyalty_program_settings WHERE org_id = %s
        """,
        (org_id,),
    )
    settings = await settings_result.fetchone()
    expiry = expiry_timestamp(datetime.now(timezone.utc), expiry_months)
    referrer_id = str(referral["referrer_customer_id"])
    referred_id = str(referral["referred_customer_id"])
    referrer_tx = await _write_award(
        conn, org_id, locked[referrer_id], Decimal(settings["referrer_reward_points"]),
        "referral", f"referral:{referral['referral_id']}:referrer",
        "Successful referral reward", actor, str(referral["referral_id"]), expiry,
        {"referral_id": str(referral["referral_id"]), "role": "referrer"},
    )
    referred_tx = await _write_award(
        conn, org_id, locked[referred_id], Decimal(settings["referred_reward_points"]),
        "referral", f"referral:{referral['referral_id']}:referred",
        "Successful referred-customer reward", actor, str(referral["referral_id"]), expiry,
        {"referral_id": str(referral["referral_id"]), "role": "referred"},
    )
    await conn.execute(
        """
        UPDATE public.loyalty_referrals
        SET status = 'qualified', qualifying_purchase_event_id = %s,
            referrer_transaction_id = %s, referred_transaction_id = %s,
            qualified_at = now()
        WHERE org_id = %s AND referral_id = %s
        """,
        (
            purchase_event_id, referrer_tx["transaction_id"], referred_tx["transaction_id"],
            org_id, referral["referral_id"],
        ),
    )
    await _audit(
        conn, org_id, actor, "loyalty_referral_qualified",
        {
            "referral_id": str(referral["referral_id"]),
            "purchase_event_id": str(purchase_event_id),
        },
    )
    return {
        "referral_id": str(referral["referral_id"]),
        "status": "qualified",
        "referrer_transaction_id": str(referrer_tx["transaction_id"]),
        "referred_transaction_id": str(referred_tx["transaction_id"]),
    }


async def import_purchase(pg_pool, org_id: str, request: dict, actor: str) -> dict:
    identity = request["customer"]
    purchased_at = request["purchased_at"]
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            event_lock = f"purchase:{org_id}:{request['source_namespace']}:{request['source_event_key']}"
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (event_lock,),
            )
            result = await conn.execute(
                """
                SELECT e.*, a.*
                FROM public.loyalty_purchase_events e
                JOIN public.loyalty_customer_accounts a
                  ON a.org_id = e.org_id AND a.loyalty_customer_id = e.loyalty_customer_id
                WHERE e.org_id = %s AND e.source_namespace = %s AND e.source_event_key = %s
                """,
                (org_id, request["source_namespace"], request["source_event_key"]),
            )
            existing = await result.fetchone()
            if existing:
                existing = dict(existing)
                existing_account = await _resolve_identity(
                    conn, org_id, identity, create=False
                )
                if (
                    str(existing_account["loyalty_customer_id"]) != str(existing["loyalty_customer_id"])
                    or Decimal(existing["purchase_amount"]) != Decimal(request["amount_inr"])
                    or existing["purchased_at"] != purchased_at
                    or existing["verification_reference"] != request["verification_reference"]
                ):
                    raise LoyaltyError("Purchase event key was already imported with different event details.")
                tx_result = await conn.execute(
                    """
                    SELECT * FROM public.loyalty_transactions
                    WHERE org_id = %s AND transaction_id = %s
                    """,
                    (org_id, existing.get("transaction_id")),
                )
                existing_tx = await tx_result.fetchone()
                return {
                    "account": _serialize_account(existing),
                    "purchase_event": {"purchase_event_id": str(existing["purchase_event_id"])},
                    "transaction": _serialize_transaction(dict(existing_tx)) if existing_tx else None,
                    "duplicate": True,
                }

            if identity["source_type"] == "demo":
                raise LoyaltyError("Demo identities cannot earn from purchase imports.")
            account = await _resolve_identity(conn, org_id, identity)
            if account["is_demo"]:
                raise LoyaltyError("Demo accounts cannot earn live purchase points.")
            ref_result = await conn.execute(
                """
                SELECT referral_id, referrer_customer_id
                FROM public.loyalty_referrals
                WHERE org_id = %s AND referred_customer_id = %s AND status = 'pending'
                """,
                (org_id, account["loyalty_customer_id"]),
            )
            pending_referral = await ref_result.fetchone()
            lock_ids = {str(account["loyalty_customer_id"])}
            if pending_referral:
                lock_ids.add(str(pending_referral["referrer_customer_id"]))
            locked_result = await conn.execute(
                """
                SELECT * FROM public.loyalty_customer_accounts
                WHERE org_id = %s AND loyalty_customer_id = ANY(%s::uuid[])
                ORDER BY loyalty_customer_id
                FOR UPDATE
                """,
                (org_id, list(lock_ids)),
            )
            locked_accounts = {
                str(row["loyalty_customer_id"]): dict(row) for row in await locked_result.fetchall()
            }
            account = locked_accounts[str(account["loyalty_customer_id"])]
            settings_result = await conn.execute(
                """
                SELECT purchase_amount, base_points, point_expiry_months
                FROM public.loyalty_program_settings WHERE org_id = %s
                """,
                (org_id,),
            )
            settings = await settings_result.fetchone()
            if not settings:
                raise LoyaltyError("Loyalty program configuration is missing for this tenant.")
            tier = tier_for_lifetime_points(
                Decimal(account["lifetime_eligible_points"]), await _get_tiers(conn, org_id)
            )
            bonus_multiplier, campaign = await _active_bonus_multiplier(conn, org_id, purchased_at)
            base, bonus = calculate_purchase_points(
                Decimal(request["amount_inr"]),
                Decimal(settings["purchase_amount"]),
                Decimal(settings["base_points"]),
                Decimal(tier["points_multiplier"]),
                bonus_multiplier,
            )
            expiry = expiry_timestamp(purchased_at, int(settings["point_expiry_months"]))
            event_result = await conn.execute(
                """
                INSERT INTO public.loyalty_purchase_events (
                    org_id, loyalty_customer_id, source_namespace, source_event_key,
                    purchase_amount, purchased_at, verification_reference, is_verified,
                    is_demo, imported_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, FALSE, %s)
                RETURNING *
                """,
                (
                    org_id, account["loyalty_customer_id"], request["source_namespace"],
                    request["source_event_key"], request["amount_inr"], purchased_at,
                    request["verification_reference"], actor,
                ),
            )
            purchase = dict(await event_result.fetchone())
            earned = None
            if base > ZERO:
                earned = await _write_award(
                    conn, org_id, account, base, "earn",
                    f"purchase:{purchase['purchase_event_id']}:earn",
                    "Verified purchase loyalty points", actor,
                    str(purchase["purchase_event_id"]), expiry,
                    {"amount_inr": str(request["amount_inr"]), "tier": tier["tier"]},
                )
            if bonus > ZERO and campaign:
                await _write_award(
                    conn, org_id, account, bonus, "bonus",
                    f"purchase:{purchase['purchase_event_id']}:bonus",
                    "Loyalty bonus campaign points", actor,
                    str(purchase["purchase_event_id"]), expiry,
                    {"campaign_name": campaign["name"], "multiplier": str(bonus_multiplier)},
                    str(campaign["bonus_campaign_id"]),
                )
            if earned:
                await conn.execute(
                    """
                    UPDATE public.loyalty_purchase_events
                    SET transaction_id = %s, processed_at = now()
                    WHERE org_id = %s AND purchase_event_id = %s
                    """,
                    (earned["transaction_id"], org_id, purchase["purchase_event_id"]),
                )
            else:
                await conn.execute(
                    """
                    UPDATE public.loyalty_purchase_events SET processed_at = now()
                    WHERE org_id = %s AND purchase_event_id = %s
                    """,
                    (org_id, purchase["purchase_event_id"]),
                )
            await _audit(
                conn, org_id, actor, "loyalty_purchase_import",
                {
                    "purchase_event_id": str(purchase["purchase_event_id"]),
                    "loyalty_customer_id": str(account["loyalty_customer_id"]),
                    "amount_inr": str(request["amount_inr"]),
                    "earned_points": str(base + bonus),
                },
            )
            referral = await _qualify_referral(
                conn, org_id, account, str(purchase["purchase_event_id"]),
                int(settings["point_expiry_months"]), actor,
            )
            account = await _get_account(
                conn, org_id, str(account["loyalty_customer_id"])
            )
            return {
                "account": _serialize_account(account),
                "purchase_event": _serialize_row(purchase),
                "transaction": _serialize_transaction(earned) if earned else None,
                "referral": referral,
                "duplicate": False,
            }


async def _expire_account(conn, org_id: str, account: dict, now: datetime, actor: str) -> list[dict]:
    result = await conn.execute(
        """
        SELECT t.transaction_id, t.points_delta,
               t.points_delta - COALESCE(SUM(a.points_allocated), 0) AS remaining_points
        FROM public.loyalty_transactions t
        LEFT JOIN public.loyalty_point_allocations a
          ON a.org_id = t.org_id AND a.earning_transaction_id = t.transaction_id
        WHERE t.org_id = %s AND t.loyalty_customer_id = %s
          AND t.points_delta > 0 AND t.is_demo = FALSE
          AND t.expires_at IS NOT NULL AND t.expires_at <= %s
        GROUP BY t.transaction_id
        HAVING t.points_delta - COALESCE(SUM(a.points_allocated), 0) > 0
        ORDER BY t.expires_at, t.created_at
        """,
        (org_id, account["loyalty_customer_id"], now),
    )
    awards = await result.fetchall()
    expired_transactions = []
    for award in awards:
        amount = points(award["remaining_points"])
        key = f"expiry:{award['transaction_id']}"
        exists = await conn.execute(
            "SELECT transaction_id FROM public.loyalty_transactions WHERE org_id = %s AND idempotency_key = %s",
            (org_id, key),
        )
        if await exists.fetchone():
            continue
        tx = await _insert_transaction(
            conn,
            org_id=org_id,
            account=account,
            transaction_type="expiry",
            points_delta=-amount,
            lifetime_delta=ZERO,
            idempotency_key=key,
            description="Unused loyalty points expired",
            actor_auth_uid=actor,
            source_reference=str(award["transaction_id"]),
            metadata={"earning_transaction_id": str(award["transaction_id"])},
            is_demo=False,
        )
        await conn.execute(
            """
            INSERT INTO public.loyalty_point_allocations (
                org_id, loyalty_customer_id, earning_transaction_id,
                consuming_transaction_id, points_allocated
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (org_id, account["loyalty_customer_id"], award["transaction_id"], tx["transaction_id"], amount),
        )
        account = await _refresh_account(
            conn,
            org_id,
            str(account["loyalty_customer_id"]),
            Decimal(account["available_points"]) - amount,
            Decimal(account["lifetime_eligible_points"]),
        )
        await _audit(
            conn, org_id, actor, "loyalty_expiry",
            {
                "transaction_id": str(tx["transaction_id"]),
                "earning_transaction_id": str(award["transaction_id"]),
                "points": str(amount),
            },
        )
        expired_transactions.append(_serialize_transaction(tx))
    return expired_transactions


async def process_expiries(pg_pool, org_id: str, actor: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                """
                SELECT DISTINCT a.loyalty_customer_id
                FROM public.loyalty_customer_accounts a
                JOIN public.loyalty_transactions t
                  ON t.org_id = a.org_id AND t.loyalty_customer_id = a.loyalty_customer_id
                WHERE a.org_id = %s AND a.is_demo = FALSE
                  AND t.points_delta > 0 AND t.is_demo = FALSE
                  AND t.expires_at IS NOT NULL AND t.expires_at <= %s
                ORDER BY a.loyalty_customer_id
                """,
                (org_id, now),
            )
            ids = [str(row["loyalty_customer_id"]) for row in await result.fetchall()]
            expired = []
            for account_id in ids:
                account = await _get_account(conn, org_id, account_id, lock=True)
                expired.extend(await _expire_account(conn, org_id, account, now, actor))
    return {"expired_transactions": expired, "total_expired": len(expired)}


async def _expire_one_locked_account(conn, org_id: str, account: dict, actor: str) -> dict:
    await _expire_account(conn, org_id, account, datetime.now(timezone.utc), actor)
    return await _get_account(conn, org_id, str(account["loyalty_customer_id"]))


async def redeem_reward(
    pg_pool, org_id: str, loyalty_customer_id: str, reward_id: str, idempotency_key: str, actor: str
) -> dict:
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            await _lock_idempotency(conn, org_id, "transaction", idempotency_key)
            duplicate = await conn.execute(
                "SELECT * FROM public.loyalty_transactions WHERE org_id = %s AND idempotency_key = %s",
                (org_id, idempotency_key),
            )
            existing = await duplicate.fetchone()
            if existing:
                existing = dict(existing)
                if (
                    existing["transaction_type"] != "redeem"
                    or str(existing["loyalty_customer_id"]) != str(loyalty_customer_id)
                    or str(existing.get("source_reference")) != str(reward_id)
                ):
                    raise LoyaltyError("Idempotency key was already used for another loyalty operation.")
                account = await _get_account(conn, org_id, str(existing["loyalty_customer_id"]))
                redemption_result = await conn.execute(
                    "SELECT * FROM public.loyalty_redemptions WHERE org_id = %s AND transaction_id = %s",
                    (org_id, existing["transaction_id"]),
                )
                redemption = await redemption_result.fetchone()
                return {
                    "account": _serialize_account(account),
                    "transaction": _serialize_transaction(existing),
                    "redemption": _serialize_row(redemption),
                    "duplicate": True,
                }
            account = await _get_account(conn, org_id, loyalty_customer_id, lock=True)
            if account["is_demo"]:
                raise LoyaltyError("Demo accounts cannot redeem live rewards.")
            account = await _expire_one_locked_account(conn, org_id, account, actor)
            reward_result = await conn.execute(
                """
                SELECT * FROM public.loyalty_rewards
                WHERE org_id = %s AND reward_id = %s AND is_active = TRUE
                """,
                (org_id, reward_id),
            )
            reward = await reward_result.fetchone()
            if not reward:
                raise LoyaltyNotFound("Reward not found or inactive.")
            cost = points(reward["points_cost"])
            balance = points(account["available_points"])
            if balance < cost:
                raise InsufficientPoints("Not enough unexpired points for this reward.")
            tx = await _insert_transaction(
                conn,
                org_id=org_id,
                account=account,
                transaction_type="redeem",
                points_delta=-cost,
                lifetime_delta=ZERO,
                idempotency_key=idempotency_key,
                description=f"Redeemed {reward['name']}",
                actor_auth_uid=actor,
                source_reference=str(reward_id),
                metadata={"reward_value_inr": str(reward["reward_value"])},
            )
            await _allocate_consumption(
                conn, org_id, loyalty_customer_id, str(tx["transaction_id"]), cost, datetime.now(timezone.utc)
            )
            updated = await _refresh_account(
                conn, org_id, loyalty_customer_id, balance - cost,
                Decimal(account["lifetime_eligible_points"]),
            )
            redemption_result = await conn.execute(
                """
                INSERT INTO public.loyalty_redemptions (
                    org_id, loyalty_customer_id, reward_id, transaction_id
                )
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (org_id, loyalty_customer_id, reward_id, tx["transaction_id"]),
            )
            redemption = dict(await redemption_result.fetchone())
            await _audit(
                conn, org_id, actor, "loyalty_redemption",
                {
                    "redemption_id": str(redemption["redemption_id"]),
                    "transaction_id": str(tx["transaction_id"]),
                    "loyalty_customer_id": str(loyalty_customer_id),
                    "reward_id": str(reward_id),
                },
            )
    return {
        "account": _serialize_account(updated),
        "transaction": _serialize_transaction(tx),
        "redemption": _serialize_row(redemption),
        "duplicate": False,
    }


async def adjust_points(pg_pool, org_id: str, request: dict, actor: str) -> dict:
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            await _lock_idempotency(conn, org_id, "transaction", request["idempotency_key"])
            duplicate = await conn.execute(
                "SELECT * FROM public.loyalty_transactions WHERE org_id = %s AND idempotency_key = %s",
                (org_id, request["idempotency_key"]),
            )
            existing = await duplicate.fetchone()
            if existing:
                existing = dict(existing)
                if (
                    existing["transaction_type"] != "manual_adjustment"
                    or Decimal(existing["points_delta"]) != points(request["points_delta"])
                    or existing["description"] != request["reason"]
                ):
                    raise LoyaltyError("Idempotency key was already used for another loyalty operation.")
                if request.get("loyalty_customer_id"):
                    requested_customer_id = str(request["loyalty_customer_id"])
                else:
                    requested_customer_id = str(
                        (await _resolve_identity(conn, org_id, request["customer"], create=False))[
                            "loyalty_customer_id"
                        ]
                    )
                if str(existing["loyalty_customer_id"]) != requested_customer_id:
                    raise LoyaltyError("Idempotency key was already used for another loyalty operation.")
                account = await _get_account(conn, org_id, str(existing["loyalty_customer_id"]))
                if bool(existing.get("is_demo", False)) != bool(account.get("is_demo", False)):
                    raise LoyaltyError("Idempotency key was already used for another loyalty operation.")
                return {
                    "account": _serialize_account(account),
                    "transaction": _serialize_transaction(existing),
                    "duplicate": True,
                }
            if request.get("loyalty_customer_id"):
                account = await _get_account(
                    conn, org_id, request["loyalty_customer_id"], lock=True
                )
            else:
                account = await _resolve_identity(conn, org_id, request["customer"])
                account = await _get_account(
                    conn, org_id, str(account["loyalty_customer_id"]), lock=True
                )
            delta = points(request["points_delta"])
            balance = points(account["available_points"])

            if account["is_demo"]:
                if delta < ZERO and balance < abs(delta):
                    raise InsufficientPoints("A negative adjustment cannot exceed the available balance.")
                tx = await _insert_transaction(
                    conn,
                    org_id=org_id,
                    account=account,
                    transaction_type="manual_adjustment",
                    points_delta=delta,
                    lifetime_delta=ZERO,
                    idempotency_key=request["idempotency_key"],
                    description=request["reason"],
                    actor_auth_uid=actor,
                    source_reference="demo",
                    metadata={"reason": request["reason"]},
                    is_demo=True,
                )
                result = await conn.execute(
                    """
                    UPDATE public.loyalty_customer_accounts
                    SET available_points = %s,
                        updated_at = now()
                    WHERE org_id = %s AND loyalty_customer_id = %s
                    RETURNING *
                    """,
                    (
                        balance + delta,
                        org_id,
                        account["loyalty_customer_id"],
                    ),
                )
                updated = dict(await result.fetchone())
                await _audit(
                    conn,
                    org_id,
                    actor,
                    "loyalty_demo_manual_adjustment",
                    {
                        "transaction_id": str(tx["transaction_id"]),
                        "loyalty_customer_id": str(account["loyalty_customer_id"]),
                        "points_delta": str(delta),
                        "reason": request["reason"],
                    },
                )
                return {
                    "account": _serialize_account(updated),
                    "transaction": _serialize_transaction(tx),
                    "duplicate": False,
                }

            account = await _expire_one_locked_account(conn, org_id, account, actor)
            balance = points(account["available_points"])
            if delta < ZERO and balance < abs(delta):
                raise InsufficientPoints("A negative adjustment cannot exceed the available balance.")
            expiry = None
            if delta > ZERO:
                expiry = expiry_timestamp(
                    datetime.now(timezone.utc), await _load_expiry_months(conn, org_id)
                )
            tx = await _insert_transaction(
                conn,
                org_id=org_id,
                account=account,
                transaction_type="manual_adjustment",
                points_delta=delta,
                lifetime_delta=delta,
                idempotency_key=request["idempotency_key"],
                description=request["reason"],
                actor_auth_uid=actor,
                source_reference="manual_adjustment",
                expires_at=expiry,
                metadata={"reason": request["reason"]},
            )
            if delta < ZERO:
                await _allocate_consumption(
                    conn, org_id, str(account["loyalty_customer_id"]),
                    str(tx["transaction_id"]), abs(delta), datetime.now(timezone.utc),
                )
            updated = await _refresh_account(
                conn,
                org_id,
                str(account["loyalty_customer_id"]),
                balance + delta,
                Decimal(account["lifetime_eligible_points"]) + delta,
            )
            await _audit(
                conn, org_id, actor, "loyalty_manual_adjustment",
                {
                    "transaction_id": str(tx["transaction_id"]),
                    "loyalty_customer_id": str(account["loyalty_customer_id"]),
                    "points_delta": str(delta),
                    "reason": request["reason"],
                },
            )
    return {"account": _serialize_account(updated), "transaction": _serialize_transaction(tx), "duplicate": False}


async def create_demo_transaction(pg_pool, org_id: str, request: dict, actor: str) -> dict:
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            await _lock_idempotency(conn, org_id, "transaction", request["idempotency_key"])
            existing_result = await conn.execute(
                "SELECT * FROM public.loyalty_transactions WHERE org_id = %s AND idempotency_key = %s",
                (org_id, request["idempotency_key"]),
            )
            existing = await existing_result.fetchone()
            if existing:
                existing = dict(existing)
                if (
                    existing["transaction_type"] != "manual_adjustment"
                    or not existing["is_demo"]
                ):
                    raise LoyaltyError("Idempotency key was already used for another loyalty operation.")
                account = await _resolve_identity(conn, org_id, request["customer"], create=False)
                if str(existing["loyalty_customer_id"]) != str(account["loyalty_customer_id"]):
                    raise LoyaltyError("Idempotency key was already used for another loyalty operation.")
                if (
                    Decimal(existing["points_delta"]) != points(request["points_delta"])
                    or existing["description"] != request["description"]
                ):
                    raise LoyaltyError("Idempotency key was already used with different demo transaction details.")
                return {
                    "account": _serialize_account(account),
                    "transaction": _serialize_transaction(existing),
                    "duplicate": True,
                }
            account = await _resolve_identity(conn, org_id, request["customer"])
            if not account["is_demo"]:
                raise LoyaltyError("Demo transactions require a dedicated demo account.")
            delta = points(request["points_delta"])
            tx = await _insert_transaction(
                conn,
                org_id=org_id,
                account=account,
                transaction_type="manual_adjustment",
                points_delta=delta,
                lifetime_delta=ZERO,
                idempotency_key=request["idempotency_key"],
                description=request["description"],
                actor_auth_uid=actor,
                source_reference="demo",
                is_demo=True,
            )
            await _audit(
                conn, org_id, actor, "loyalty_demo_transaction",
                {
                    "transaction_id": str(tx["transaction_id"]),
                    "loyalty_customer_id": str(account["loyalty_customer_id"]),
                    "points_delta": str(delta),
                },
            )
    return {"account": _serialize_account(account), "transaction": _serialize_transaction(tx), "duplicate": False}


async def create_referral(pg_pool, org_id: str, request: dict, actor: str) -> dict:
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            identities = sorted(
                (request["referrer"], request["referred"]),
                key=lambda identity: (
                    identity["source_type"],
                    identity["source_namespace"],
                    identity["source_customer_key"],
                ),
            )
            resolved = {}
            for identity in identities:
                resolved[
                    (identity["source_type"], identity["source_namespace"], identity["source_customer_key"])
                ] = await _resolve_identity(conn, org_id, identity)
            referrer = resolved[
                (
                    request["referrer"]["source_type"],
                    request["referrer"]["source_namespace"],
                    request["referrer"]["source_customer_key"],
                )
            ]
            referred = resolved[
                (
                    request["referred"]["source_type"],
                    request["referred"]["source_namespace"],
                    request["referred"]["source_customer_key"],
                )
            ]
            existing_result = await conn.execute(
                "SELECT * FROM public.loyalty_referrals WHERE org_id = %s AND referral_code = %s",
                (org_id, request["referral_code"]),
            )
            existing = await existing_result.fetchone()
            if referrer["is_demo"] or referred["is_demo"]:
                raise LoyaltyError("Demo accounts cannot participate in referrals.")
            if str(referrer["loyalty_customer_id"]) == str(referred["loyalty_customer_id"]):
                raise LoyaltyError("A loyalty account cannot refer itself.")
            if existing:
                existing = dict(existing)
                if (
                    str(existing["referrer_customer_id"]) != str(referrer["loyalty_customer_id"])
                    or str(existing["referred_customer_id"]) != str(referred["loyalty_customer_id"])
                ):
                    raise LoyaltyError("This referral code is already assigned to another referral.")
                return _serialize_row(existing)
            purchase_result = await conn.execute(
                """
                SELECT 1 FROM public.loyalty_purchase_events
                WHERE org_id = %s AND loyalty_customer_id = %s AND is_verified = TRUE
                LIMIT 1
                """,
                (org_id, referred["loyalty_customer_id"]),
            )
            if await purchase_result.fetchone():
                raise LoyaltyError("A referral must be recorded before the referred customer's first verified purchase.")
            ids = sorted([str(referrer["loyalty_customer_id"]), str(referred["loyalty_customer_id"])])
            lock_result = await conn.execute(
                """
                SELECT loyalty_customer_id FROM public.loyalty_customer_accounts
                WHERE org_id = %s AND loyalty_customer_id = ANY(%s::uuid[])
                ORDER BY loyalty_customer_id FOR UPDATE
                """,
                (org_id, ids),
            )
            await lock_result.fetchall()
            result = await conn.execute(
                """
                INSERT INTO public.loyalty_referrals (
                    org_id, referrer_customer_id, referred_customer_id,
                    referral_code, created_by
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    org_id, referrer["loyalty_customer_id"], referred["loyalty_customer_id"],
                    request["referral_code"], actor,
                ),
            )
            referral = dict(await result.fetchone())
            await _audit(
                conn, org_id, actor, "loyalty_referral_create",
                {
                    "referral_id": str(referral["referral_id"]),
                    "referrer_customer_id": str(referrer["loyalty_customer_id"]),
                    "referred_customer_id": str(referred["loyalty_customer_id"]),
                },
            )
    return _serialize_row(referral)


async def list_referrals(pg_pool, org_id: str) -> list[dict]:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT r.*, ref.display_name AS referrer_name, red.display_name AS referred_name
            FROM public.loyalty_referrals r
            JOIN public.loyalty_customer_accounts ref
              ON ref.org_id = r.org_id AND ref.loyalty_customer_id = r.referrer_customer_id
            JOIN public.loyalty_customer_accounts red
              ON red.org_id = r.org_id AND red.loyalty_customer_id = r.referred_customer_id
            WHERE r.org_id = %s
            ORDER BY r.created_at DESC
            """,
            (org_id,),
        )
        return [_serialize_row(row) for row in await result.fetchall()]


async def create_bonus_campaign(pg_pool, org_id: str, request: dict, actor: str) -> dict:
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            await _lock_idempotency(
                conn, org_id, "bonus-campaign", request["idempotency_key"]
            )
            existing_result = await conn.execute(
                """
                SELECT * FROM public.loyalty_bonus_campaigns
                WHERE org_id = %s AND idempotency_key = %s
                """,
                (org_id, request["idempotency_key"]),
            )
            existing = await existing_result.fetchone()
            if existing:
                if (
                    existing["name"] != request["name"]
                    or existing["description"] != request.get("description")
                    or Decimal(existing["points_multiplier"]) != Decimal(request["points_multiplier"])
                    or existing["starts_at"] != request["starts_at"]
                    or existing["ends_at"] != request["ends_at"]
                ):
                    raise LoyaltyError("Bonus campaign idempotency key was already used with different details.")
                return _serialize_row(existing)
            result = await conn.execute(
                """
                INSERT INTO public.loyalty_bonus_campaigns (
                    org_id, name, description, points_multiplier, starts_at,
                    ends_at, status, idempotency_key, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'draft', %s, %s)
                RETURNING *
                """,
                (
                    org_id, request["name"], request.get("description"),
                    request["points_multiplier"], request["starts_at"],
                    request["ends_at"], request["idempotency_key"], actor,
                ),
            )
            campaign = dict(await result.fetchone())
            await _audit(
                conn, org_id, actor, "loyalty_bonus_campaign_create",
                {"campaign_id": str(campaign["bonus_campaign_id"]), "name": campaign["name"]},
            )
    return _serialize_row(campaign)


async def update_bonus_campaign_status(pg_pool, org_id: str, campaign_id: str, status: str, actor: str) -> dict:
    async with pg_pool.connection() as conn:
        async with conn.transaction():
            previous_result = await conn.execute(
                """
                SELECT status FROM public.loyalty_bonus_campaigns
                WHERE org_id = %s AND bonus_campaign_id = %s
                FOR UPDATE
                """,
                (org_id, campaign_id),
            )
            previous = await previous_result.fetchone()
            if not previous:
                raise LoyaltyNotFound("Bonus campaign not found.")
            if previous["status"] == status:
                current_result = await conn.execute(
                    """
                    SELECT * FROM public.loyalty_bonus_campaigns
                    WHERE org_id = %s AND bonus_campaign_id = %s
                    """,
                    (org_id, campaign_id),
                )
                return _serialize_row(await current_result.fetchone())
            result = await conn.execute(
                """
                UPDATE public.loyalty_bonus_campaigns
                SET status = %s, updated_at = now()
                WHERE org_id = %s AND bonus_campaign_id = %s
                RETURNING *
                """,
                (status, org_id, campaign_id),
            )
            campaign = await result.fetchone()
            if not campaign:
                raise LoyaltyNotFound("Bonus campaign not found.")
            campaign = dict(campaign)
            await _audit(
                conn, org_id, actor, "loyalty_bonus_campaign_status",
                {"campaign_id": str(campaign_id), "status": status},
            )
    return _serialize_row(campaign)


async def list_bonus_campaigns(pg_pool, org_id: str) -> list[dict]:
    async with pg_pool.connection() as conn:
        result = await conn.execute(
            """
            SELECT * FROM public.loyalty_bonus_campaigns
            WHERE org_id = %s ORDER BY starts_at DESC
            """,
            (org_id,),
        )
        return [_serialize_row(row) for row in await result.fetchall()]
