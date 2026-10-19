import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.crm import metrics, routes
from backend.auth import get_current_user


class BusinessMetricCalculationTests(unittest.TestCase):
    def test_calculates_supported_customer_metrics(self):
        result = metrics.calculate_business_metrics(
            [
                {"total_spend": "100.00", "churn_risk": "0.5"},
                {"total_spend": "200.00", "churn_risk": "0.75"},
            ],
            {"total_spend", "churn_risk"},
        )

        self.assertEqual(result["customer_count"], {"value": 2, "available": True, "reason": None})
        self.assertEqual(result["total_recorded_spend"]["value"], 300.0)
        self.assertEqual(result["average_customer_spend"]["value"], 150.0)
        self.assertEqual(result["at_risk_customer_count"]["value"], 1)

    def test_empty_data_does_not_invent_zero_spend_or_risk(self):
        result = metrics.calculate_business_metrics([], {"total_spend", "churn_risk"})

        self.assertEqual(result["customer_count"]["value"], 0)
        self.assertIsNone(result["total_recorded_spend"]["value"])
        self.assertFalse(result["total_recorded_spend"]["available"])
        self.assertIsNone(result["at_risk_customer_count"]["value"])
        self.assertFalse(result["at_risk_customer_count"]["available"])
        self.assertFalse(result["average_customer_spend"]["available"])

    def test_unsupported_metrics_are_unavailable_and_incomplete_values_are_excluded(self):
        unsupported = metrics.calculate_business_metrics([{}], set())
        incomplete = metrics.calculate_business_metrics(
            [
                {"total_spend": "25.00", "churn_risk": "0.8"},
                {"total_spend": None, "churn_risk": "NaN"},
                {"total_spend": "Infinity", "churn_risk": "invalid"},
            ],
            {"total_spend", "churn_risk"},
        )

        self.assertFalse(unsupported["total_recorded_spend"]["available"])
        self.assertFalse(unsupported["at_risk_customer_count"]["available"])
        self.assertEqual(incomplete["total_recorded_spend"]["value"], 25.0)
        self.assertEqual(incomplete["average_customer_spend"]["value"], 25.0)
        self.assertEqual(incomplete["at_risk_customer_count"]["value"], 1)
        self.assertIn("excluded", incomplete["total_recorded_spend"]["reason"])
        self.assertIn("excluded", incomplete["at_risk_customer_count"]["reason"])

    def test_only_invalid_values_make_metrics_unavailable(self):
        result = metrics.calculate_business_metrics(
            [
                {"total_spend": "NaN", "churn_risk": "Infinity"},
                {"total_spend": "invalid", "churn_risk": None},
            ],
            {"total_spend", "churn_risk"},
        )

        self.assertIsNone(result["total_recorded_spend"]["value"])
        self.assertFalse(result["total_recorded_spend"]["available"])
        self.assertIsNone(result["average_customer_spend"]["value"])
        self.assertFalse(result["average_customer_spend"]["available"])
        self.assertIsNone(result["at_risk_customer_count"]["value"])
        self.assertFalse(result["at_risk_customer_count"]["available"])

    def test_missing_tenant_data_marks_all_metrics_unavailable(self):
        result = metrics.calculate_business_metrics([], set(), data_available=False)

        self.assertEqual(
            set(result),
            {
                "customer_count",
                "total_recorded_spend",
                "average_customer_spend",
                "at_risk_customer_count",
            },
        )
        for metric in result.values():
            self.assertEqual(metric["value"], None)
            self.assertFalse(metric["available"])
            self.assertTrue(metric["reason"])

    def test_advisor_insights_summarize_only_available_metrics_and_risk_classes(self):
        response = metrics.build_business_advisor_insights(
            {
                "source": "tenant_customer_data",
                "metrics": {
                    "customer_count": {"value": 3, "available": True, "reason": None},
                    "total_recorded_spend": {"value": 250.0, "available": True, "reason": None},
                    "recorded_loyalty_purchase_spend": {
                        "value": 75.0, "available": True, "reason": None,
                    },
                    "average_customer_spend": {"value": 83.33, "available": True, "reason": None},
                    "at_risk_customer_count": {"value": 1, "available": True, "reason": None},
                    "revenue": {"value": None, "available": False, "reason": "Order data is not mapped."},
                },
            },
            [{"risk_level": "high"}, {"risk_level": "medium"}],
        )

        self.assertEqual(response["source"], "tenant_customer_data")
        self.assertIn("Customer records: 3.", response["summary"])
        self.assertIn("Total recorded customer spend: 250.00.", response["summary"])
        self.assertIn("Recorded loyalty purchase spend: 75.00.", response["summary"])
        self.assertEqual(response["risk_classifications"]["counts"]["high"], 1)
        self.assertEqual(response["risk_classifications"]["counts"]["medium"], 1)
        self.assertEqual(response["unavailable_metrics"], {"revenue": "Order data is not mapped."})
        self.assertEqual(len(response["recommendations"]), 2)

    def test_advisor_insights_mark_missing_data_unavailable_without_seed_values(self):
        unavailable = {
            "value": None,
            "available": False,
            "reason": "No tenant customer data is available.",
        }
        response = metrics.build_business_advisor_insights(
            {
                "source": "tenant_customer_data",
                "metrics": {
                    "customer_count": unavailable,
                    "total_recorded_spend": unavailable,
                    "recorded_loyalty_purchase_spend": unavailable,
                    "average_customer_spend": unavailable,
                    "at_risk_customer_count": unavailable,
                },
            },
            [],
        )

        self.assertEqual(response["metrics"]["customer_count"]["value"], None)
        self.assertFalse(response["metrics"]["customer_count"]["available"])
        self.assertEqual(response["risk_classifications"]["counts"], None)
        self.assertFalse(response["risk_classifications"]["available"])
        self.assertEqual(response["recommendations"][0]["evidence"],
                         "No persisted risk snapshots are available for this tenant.")
        self.assertEqual(set(response["unavailable_metrics"]), {
            "customer_count",
            "total_recorded_spend",
            "recorded_loyalty_purchase_spend",
            "average_customer_spend",
            "at_risk_customer_count",
        })


class BusinessMetricTenantScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_customer_queries_are_scoped_to_requested_tenant(self):
        class Result:
            def __init__(self, row=None, rows=None):
                self.row = row
                self.rows = rows or []

            async def fetchone(self):
                return self.row

            async def fetchall(self):
                return self.rows

        class AsyncContext:
            def __init__(self, value):
                self.value = value

            async def __aenter__(self):
                return self.value

            async def __aexit__(self, *_args):
                return False

        connection = Mock()
        calls = []

        async def execute(query, params=None):
            calls.append((query, params))
            if "SELECT data FROM public.customers" in query:
                return Result(rows=[
                    {"data": {"total_spend": "125", "churn_risk": "0.8"}},
                    {"data": {"total_spend": "NaN", "churn_risk": "Infinity"}},
                ])
            if "FROM public.loyalty_purchase_events" in query:
                return Result({"qualifying_purchases": 2, "total_spend": Decimal("40.00")})
            self.fail(f"Unexpected tenant metric query: {query}")

        connection.execute = AsyncMock(side_effect=execute)
        pool = Mock()
        pool.connection.return_value = AsyncContext(connection)

        with patch.object(metrics, "_approved_mapping", new_callable=AsyncMock) as mapping_lookup:
            mapping_lookup.side_effect = LookupError("No approved mapping")
            result = await metrics.get_business_metrics(pool, "tenant-a")

        self.assertEqual(result["source"], "tenant_customer_data")
        self.assertEqual(result["metrics"]["customer_count"]["value"], 2)
        self.assertEqual(result["metrics"]["total_recorded_spend"]["value"], 125.0)
        self.assertTrue(result["metrics"]["total_recorded_spend"]["available"])
        self.assertEqual(result["metrics"]["average_customer_spend"]["value"], 125.0)
        self.assertIn("excluded", result["metrics"]["total_recorded_spend"]["reason"])
        self.assertEqual(result["metrics"]["at_risk_customer_count"]["value"], 1)
        self.assertTrue(result["metrics"]["at_risk_customer_count"]["available"])
        self.assertEqual(result["metrics"]["recorded_loyalty_purchase_spend"], {
            "value": 40.0, "available": True, "reason": None,
        })
        self.assertEqual(len(calls), 2)
        for _query, params in calls:
            self.assertEqual(params, ("tenant-a",))
        customer_query = calls[0][0]
        self.assertIn("FROM public.customers", customer_query)
        self.assertIn("WHERE org_id = %s", customer_query)
        spend_query = calls[-1][0]
        self.assertIn("e.org_id = %s", spend_query)
        self.assertIn("e.is_verified = TRUE", spend_query)
        self.assertIn("e.is_demo = FALSE", spend_query)
        self.assertIn("a.org_id = e.org_id", spend_query)
        self.assertIn("a.is_demo = FALSE", spend_query)
        mapping_lookup.assert_awaited_once_with(pool, "tenant-a")

    async def test_loyalty_purchase_spend_is_unavailable_without_qualifying_records(self):
        class Result:
            async def fetchone(self):
                return {"qualifying_purchases": 0, "total_spend": None}

        class AsyncContext:
            def __init__(self, value):
                self.value = value

            async def __aenter__(self):
                return self.value

            async def __aexit__(self, *_args):
                return False

        connection = Mock()
        connection.execute = AsyncMock(return_value=Result())
        pool = Mock()
        pool.connection.return_value = AsyncContext(connection)

        metric = await metrics._recorded_loyalty_purchase_spend(pool, "tenant-b")

        self.assertIsNone(metric["value"])
        self.assertFalse(metric["available"])
        self.assertIn("No verified live loyalty purchase records", metric["reason"])
        query, params = connection.execute.await_args.args
        self.assertIn("e.org_id = %s", query)
        self.assertIn("e.is_verified = TRUE", query)
        self.assertIn("e.is_demo = FALSE", query)
        self.assertIn("a.is_demo = FALSE", query)
        self.assertEqual(params, ("tenant-b",))

    async def test_missing_data_response_marks_metrics_unavailable(self):
        with (
            patch.object(metrics, "_approved_mapping", new_callable=AsyncMock) as mapping_lookup,
            patch.object(metrics, "_local_customer_data", new_callable=AsyncMock) as local_data,
            patch.object(metrics, "_recorded_loyalty_purchase_spend", new_callable=AsyncMock) as loyalty_spend,
        ):
            mapping_lookup.side_effect = LookupError("No approved mapping")
            local_data.return_value = ([], set(), False)
            loyalty_spend.return_value = {
                "value": None,
                "available": False,
                "reason": "No verified live loyalty purchase records are available for this tenant.",
            }
            response = await metrics.get_business_metrics(Mock(), "tenant-a")

        self.assertEqual(response["source"], "tenant_customer_data")
        for metric in response["metrics"].values():
            self.assertEqual(set(metric), {"value", "available", "reason"})
            self.assertIsNone(metric["value"])
            self.assertFalse(metric["available"])
            self.assertTrue(metric["reason"])

    async def test_advisor_service_uses_tenant_metrics_and_excludes_seed_risk_fallback(self):
        metric_response = {
            "source": "tenant_customer_data",
            "metrics": {
                "customer_count": {"value": 0, "available": False, "reason": "No data."},
                "total_recorded_spend": {"value": None, "available": False, "reason": "No data."},
                "average_customer_spend": {"value": None, "available": False, "reason": "No data."},
                "at_risk_customer_count": {"value": None, "available": False, "reason": "No data."},
            },
        }
        pool = Mock()
        with (
            patch.object(metrics, "get_business_metrics", new_callable=AsyncMock) as get_metrics,
            patch.object(metrics, "list_risk_snapshots", new_callable=AsyncMock) as get_risk,
        ):
            get_metrics.return_value = metric_response
            get_risk.return_value = []
            response = await metrics.get_business_advisor_insights(pool, "tenant-a")

        get_metrics.assert_awaited_once_with(pool, "tenant-a")
        get_risk.assert_awaited_once_with(
            pool, "tenant-a", include_seed_fallback=False
        )
        self.assertFalse(response["risk_classifications"]["available"])

    def test_business_metrics_endpoint_requires_authentication(self):
        app = FastAPI()
        app.include_router(routes.router)

        response = TestClient(app).get("/crm/business-metrics")

        self.assertEqual(response.status_code, 401)

    def test_authenticated_endpoint_returns_metrics_for_resolved_tenant(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_current_user] = lambda: {"sub": "auth-user"}
        pool = Mock()
        client = TestClient(app)
        with (
            patch.object(routes, "_get_pool", return_value=pool),
            patch.object(routes, "get_org_id_for_user", new_callable=AsyncMock) as get_org,
            patch.object(metrics, "_approved_mapping", new_callable=AsyncMock) as mapping_lookup,
            patch.object(metrics, "_local_customer_data", new_callable=AsyncMock) as local_data,
            patch.object(metrics, "_recorded_loyalty_purchase_spend", new_callable=AsyncMock) as loyalty_spend,
        ):
            get_org.return_value = "tenant-a"
            mapping_lookup.side_effect = LookupError("No approved mapping")
            loyalty_spend.return_value = {"value": 80.0, "available": True, "reason": None}
            local_data.return_value = (
                [
                    {"total_spend": "100.00", "churn_risk": "0.2"},
                    {"total_spend": "250.00", "churn_risk": "0.8"},
                ],
                {"total_spend", "churn_risk"},
                True,
            )
            response = client.get("/crm/business-metrics")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "tenant_customer_data")
        self.assertEqual(body["metrics"]["customer_count"], {
            "value": 2, "available": True, "reason": None,
        })
        self.assertEqual(body["metrics"]["total_recorded_spend"]["value"], 350.0)
        self.assertEqual(body["metrics"]["recorded_loyalty_purchase_spend"]["value"], 80.0)
        self.assertEqual(body["metrics"]["average_customer_spend"]["value"], 175.0)
        self.assertEqual(body["metrics"]["at_risk_customer_count"]["value"], 1)
        get_org.assert_awaited_once_with("auth-user", pool)
        local_data.assert_awaited_once_with(pool, "tenant-a")

    def test_business_advisor_endpoint_resolves_authenticated_tenant(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_current_user] = lambda: {"sub": "auth-user"}
        pool = Mock()
        client = TestClient(app)
        expected = {
            "source": "tenant_customer_data",
            "metrics": {},
            "risk_classifications": {"available": False, "counts": None, "reason": "No persisted risk snapshots."},
            "summary": "No supported customer business metrics are currently available.",
            "recommendations": [],
            "unavailable_metrics": {},
        }
        with (
            patch.object(routes, "_get_pool", return_value=pool),
            patch.object(routes, "get_org_id_for_user", new_callable=AsyncMock) as get_org,
            patch.object(routes, "get_business_advisor_insights", new_callable=AsyncMock) as get_insights,
        ):
            get_org.return_value = "tenant-a"
            get_insights.return_value = expected
            response = client.get("/crm/business-advisor/insights")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        get_org.assert_awaited_once_with("auth-user", pool)
        get_insights.assert_awaited_once_with(pool, "tenant-a")

    def test_authenticated_endpoint_marks_missing_data_unavailable(self):
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[get_current_user] = lambda: {"sub": "auth-user"}
        pool = Mock()
        client = TestClient(app)
        with (
            patch.object(routes, "_get_pool", return_value=pool),
            patch.object(routes, "get_org_id_for_user", new_callable=AsyncMock) as get_org,
            patch.object(metrics, "_approved_mapping", new_callable=AsyncMock) as mapping_lookup,
            patch.object(metrics, "_local_customer_data", new_callable=AsyncMock) as local_data,
            patch.object(metrics, "_recorded_loyalty_purchase_spend", new_callable=AsyncMock) as loyalty_spend,
        ):
            get_org.return_value = "tenant-a"
            mapping_lookup.side_effect = LookupError("No approved mapping")
            local_data.return_value = ([], set(), False)
            loyalty_spend.return_value = {
                "value": None,
                "available": False,
                "reason": "No verified live loyalty purchase records are available for this tenant.",
            }
            response = client.get("/crm/business-metrics")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["source"], "tenant_customer_data")
        self.assertEqual(set(body["metrics"]), {
            "customer_count",
            "total_recorded_spend",
            "recorded_loyalty_purchase_spend",
            "average_customer_spend",
            "at_risk_customer_count",
        })
        for metric in body["metrics"].values():
            self.assertIsNone(metric["value"])
            self.assertFalse(metric["available"])
            self.assertTrue(metric["reason"])
        get_org.assert_awaited_once_with("auth-user", pool)
        local_data.assert_awaited_once_with(pool, "tenant-a")


if __name__ == "__main__":
    unittest.main()
