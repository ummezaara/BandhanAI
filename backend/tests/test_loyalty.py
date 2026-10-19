from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pydantic import ValidationError

from backend.app.loyalty import service
from backend.app.loyalty.routes import router
from backend.app.loyalty.schemas import (
    BonusCampaignCreateRequest,
    CustomerIdentity,
    ManualAdjustmentRequest,
    PurchaseImportRequest,
    ReferralCreateRequest,
)


class LoyaltyCalculationTests(unittest.TestCase):
    def setUp(self):
        self.tiers = [
            {"tier": "Bronze", "min_lifetime_points": Decimal("0"), "max_lifetime_points": Decimal("499.99")},
            {"tier": "Silver", "min_lifetime_points": Decimal("500"), "max_lifetime_points": Decimal("1999.99")},
            {"tier": "Gold", "min_lifetime_points": Decimal("2000"), "max_lifetime_points": Decimal("4999.99")},
            {"tier": "Platinum", "min_lifetime_points": Decimal("5000"), "max_lifetime_points": None},
        ]

    def test_tier_boundaries_with_fractional_points(self):
        cases = [
            ("0", "Bronze"),
            ("499.99", "Bronze"),
            ("500", "Silver"),
            ("1999.99", "Silver"),
            ("2000", "Gold"),
            ("4999.99", "Gold"),
            ("5000", "Platinum"),
            ("7500.25", "Platinum"),
        ]
        for points, expected in cases:
            with self.subTest(points=points):
                tier = service.tier_for_lifetime_points(Decimal(points), self.tiers)
                self.assertEqual(tier["tier"], expected)

    def test_purchase_points_apply_tier_and_one_bonus_multiplier(self):
        base, bonus = service.calculate_purchase_points(
            Decimal("100"),
            Decimal("100"),
            Decimal("10"),
            Decimal("1.25"),
            Decimal("2"),
        )
        self.assertEqual(base, Decimal("12.50"))
        self.assertEqual(bonus, Decimal("12.50"))
        self.assertEqual(base + bonus, Decimal("25.00"))

    def test_purchase_points_round_to_two_decimal_places(self):
        base, bonus = service.calculate_purchase_points(
            Decimal("1"),
            Decimal("100"),
            Decimal("10"),
            Decimal("1"),
            Decimal("1.5"),
        )
        self.assertEqual(base, Decimal("0.10"))
        self.assertEqual(bonus, Decimal("0.05"))

    def test_expiry_uses_calendar_months(self):
        earned = datetime(2024, 2, 29, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(
            service.expiry_timestamp(earned, 12),
            datetime(2025, 2, 28, 12, 0, tzinfo=timezone.utc),
        )


class LoyaltySchemaTests(unittest.TestCase):
    def identity(self, key: str = "customer-1") -> CustomerIdentity:
        return CustomerIdentity(
            source_type="platform",
            source_namespace="platform-customers",
            source_customer_key=key,
        )

    def test_zero_adjustment_is_rejected(self):
        with self.assertRaises(ValidationError):
            ManualAdjustmentRequest(
                customer=self.identity(),
                points_delta=Decimal("0"),
                reason="Correction",
                idempotency_key="adjustment-001",
            )

    def test_purchase_import_requires_timezone_aware_timestamp(self):
        with self.assertRaises(ValidationError):
            PurchaseImportRequest(
                customer=self.identity(),
                source_namespace="pos",
                source_event_key="sale-1",
                amount_inr=Decimal("100"),
                purchased_at=datetime(2026, 1, 1),
                verification_reference="pos-import",
            )

    def test_purchase_import_does_not_accept_client_controlled_verification_flag(self):
        with self.assertRaises(ValidationError):
            PurchaseImportRequest(
                customer=self.identity(),
                source_namespace="pos",
                source_event_key="sale-1",
                amount_inr=Decimal("100"),
                purchased_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                verification_reference="pos-import",
                is_verified=False,
            )

    def test_bonus_campaign_requires_timezone_and_valid_period(self):
        with self.assertRaises(ValidationError):
            BonusCampaignCreateRequest(
                name="Weekend multiplier",
                points_multiplier=Decimal("2"),
                starts_at=datetime(2026, 1, 1),
                ends_at=datetime(2026, 1, 2),
                idempotency_key="bonus-campaign-001",
            )

    def test_referral_cannot_use_the_same_source_identity_twice(self):
        customer = self.identity()
        with self.assertRaises(ValidationError):
            ReferralCreateRequest(
                referrer=customer,
                referred=customer,
                referral_code="REF-CODE-1",
            )


class LoyaltyDemoAdjustmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_adjustment_updates_demo_balance_without_changing_tier_points(self):
        account_id = "demo-account-1"
        demo_account = {
            "loyalty_customer_id": account_id,
            "display_name": "Demo customer",
            "email": None,
            "available_points": Decimal("25.00"),
            "lifetime_eligible_points": Decimal("0.00"),
            "current_tier": "Bronze",
            "is_demo": True,
        }
        transaction = {
            "transaction_id": "demo-transaction-1",
            "loyalty_customer_id": account_id,
            "transaction_type": "manual_adjustment",
            "points_delta": Decimal("10.00"),
            "lifetime_points_delta": Decimal("0.00"),
            "description": "Testing award",
            "source_reference": "demo",
            "is_demo": True,
            "expires_at": None,
            "created_at": None,
        }
        updated_account = {
            **demo_account,
            "available_points": Decimal("35.00"),
        }

        class Result:
            def __init__(self, row):
                self.row = row

            async def fetchone(self):
                return self.row

        class AsyncContext:
            def __init__(self, value):
                self.value = value

            async def __aenter__(self):
                return self.value

            async def __aexit__(self, *_args):
                return False

        connection = Mock()
        connection.transaction.return_value = AsyncContext(None)
        executed = []

        async def execute(query, params=None):
            executed.append((query, params))
            if "SELECT * FROM public.loyalty_transactions" in query:
                return Result(None)
            if "SELECT * FROM public.loyalty_customer_accounts" in query:
                return Result(demo_account)
            if "INSERT INTO public.loyalty_transactions" in query:
                return Result(transaction)
            if "UPDATE public.loyalty_customer_accounts" in query:
                return Result(updated_account)
            return Result(None)

        connection.execute = AsyncMock(side_effect=execute)
        pool = Mock()
        pool.connection.return_value = AsyncContext(connection)

        with patch.object(service, "_audit", new_callable=AsyncMock) as audit:
            result = await service.adjust_points(
                pool,
                "tenant-1",
                {
                    "loyalty_customer_id": account_id,
                    "points_delta": Decimal("10.00"),
                    "reason": "Testing award",
                    "idempotency_key": "demo-adjustment-001",
                },
                "actor-1",
            )

        inserted_query, inserted_params = next(
            item for item in executed if "INSERT INTO public.loyalty_transactions" in item[0]
        )
        update_query, update_params = next(
            item for item in executed if "UPDATE public.loyalty_customer_accounts" in item[0]
        )
        self.assertIn("is_demo", inserted_query)
        self.assertEqual(inserted_params[4], Decimal("0.00"))
        self.assertTrue(inserted_params[9])
        self.assertIn("SET available_points = %s", update_query)
        self.assertNotIn("lifetime_eligible_points =", update_query)
        self.assertNotIn("current_tier =", update_query)
        self.assertEqual(update_params[0], Decimal("35.00"))
        self.assertEqual(result["account"]["current_balance"], 35.0)
        self.assertEqual(result["account"]["lifetime_eligible_points"], 0.0)
        self.assertEqual(result["account"]["tier"], "Bronze")
        self.assertTrue(result["transaction"]["is_demo"])
        audit.assert_awaited_once()


class LoyaltyIntegrationSurfaceTests(unittest.TestCase):
    def test_expected_api_routes_are_registered(self):
        paths = {route.path for route in router.routes}
        expected = {
            "/loyalty/summary",
            "/loyalty/accounts",
            "/loyalty/purchases/import",
            "/loyalty/adjustments",
            "/loyalty/accounts/{loyalty_customer_id}/redemptions",
            "/loyalty/referrals",
            "/loyalty/bonus-campaigns",
            "/loyalty/expiry/process",
        }
        self.assertTrue(expected.issubset(paths))

    def test_migration_has_tenant_rls_and_append_only_history(self):
        migration_path = Path(__file__).parents[1] / "migrations" / "015_loyalty.sql"
        migration = migration_path.read_text(encoding="utf-8")
        expected_tables = (
            "loyalty_program_settings",
            "loyalty_tier_rules",
            "loyalty_customer_accounts",
            "loyalty_customer_identities",
            "loyalty_rewards",
            "loyalty_transactions",
            "loyalty_purchase_events",
            "loyalty_point_allocations",
            "loyalty_redemptions",
            "loyalty_referrals",
            "loyalty_bonus_campaigns",
        )
        for table in expected_tables:
            with self.subTest(table=table):
                self.assertIn(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY", migration)
        self.assertIn("owner_auth_uid = auth.uid()", migration)
        self.assertIn("BEFORE UPDATE OR DELETE ON public.loyalty_transactions", migration)
        self.assertIn("BEFORE UPDATE OR DELETE ON public.loyalty_point_allocations", migration)
        self.assertIn("point_expiry_months INTEGER NOT NULL DEFAULT 12", migration)
        self.assertIn("499.99::NUMERIC", migration)
        self.assertIn("referrer_reward_points NUMERIC(12, 2) NOT NULL DEFAULT 200", migration)
        self.assertIn("referred_reward_points NUMERIC(12, 2) NOT NULL DEFAULT 100", migration)


if __name__ == "__main__":
    unittest.main()
