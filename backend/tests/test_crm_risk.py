import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from backend.app.crm import risk


class RiskRefreshSourceFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_mapping_lookup_error_does_not_fall_back_to_local_customers(self):
        pool = Mock()

        with (
            patch.object(risk, "_approved_mapping", new_callable=AsyncMock) as mapping,
            patch.object(risk, "_local_customer_rows", new_callable=AsyncMock) as local_data,
            patch.object(risk, "_score_customer") as score,
            patch(
                "backend.app.crm.routes._get_tenant_customers_data",
                new_callable=AsyncMock,
            ) as fallback,
        ):
            mapping.side_effect = RuntimeError("mapping database unavailable")
            with self.assertRaisesRegex(ValueError, "approved customer mapping"):
                await risk.refresh_risk_snapshots(pool, "tenant-a")

        mapping.assert_awaited_once_with(pool, "tenant-a")
        local_data.assert_not_awaited()
        score.assert_not_called()
        fallback.assert_not_awaited()
        pool.connection.assert_not_called()

    async def test_no_approved_mapping_uses_tenant_scoped_local_customers(self):
        local_rows = [
            {
                "customer_id": "customer-1",
                "data": {
                    "name": "Rhea",
                    "churn_risk": "0.8",
                    "last_purchase": "2026-01-01",
                    "feedback_score": "2",
                    "total_spend": "125.50",
                },
            },
            {
                "customer_id": "customer-2",
                "data": {
                    "name": "Sam",
                    "churn_risk": "NaN",
                    "last_purchase": "not-a-date",
                    "feedback_score": "invalid",
                    "total_spend": "Infinity",
                },
            },
        ]

        class Result:
            async def fetchall(self):
                return local_rows

        class AsyncContext:
            def __init__(self, value=None):
                self.value = value

            async def __aenter__(self):
                return self.value

            async def __aexit__(self, *_args):
                return False

        database_connection = Mock()
        calls = []

        async def execute(query, params=None):
            calls.append((query, params))
            return Result()

        database_connection.execute = AsyncMock(side_effect=execute)
        database_connection.transaction.return_value = AsyncContext()
        pool = Mock()
        pool.connection.return_value = AsyncContext(database_connection)

        with (
            patch.object(risk, "_approved_mapping", new_callable=AsyncMock) as mapping,
            patch.object(risk, "_score_customer", wraps=risk._score_customer) as score,
        ):
            mapping.side_effect = LookupError("No approved mapping")
            result = await risk.refresh_risk_snapshots(pool, "tenant-a")

        self.assertTrue(result["refreshed"])
        self.assertEqual(result["total_scored"], 2)
        self.assertEqual(result["high_risk"], 1)
        self.assertEqual(result["unknown"], 1)
        mapping.assert_awaited_once_with(pool, "tenant-a")
        self.assertEqual(score.call_count, 2)
        local_query, params = calls[0]
        self.assertIn("FROM public.customers", local_query)
        self.assertIn("WHERE org_id = %s", local_query)
        self.assertEqual(params, ("tenant-a", 500))
        self.assertEqual(len(calls), 4)
        self.assertIn("DELETE FROM customer_risk_snapshots", calls[1][0])
        insert_query, insert_values = calls[2]
        self.assertIn("source_type", insert_query)
        self.assertEqual(insert_values[0:5], ("tenant-a", None, None, "local", "customer-1"))
        stored_fields = json.loads(insert_values[9])
        self.assertEqual(stored_fields["churn_risk"], 0.8)
        self.assertEqual(stored_fields["feedback_score"], 2.0)
        self.assertEqual(stored_fields["total_spend"], 125.5)
        second_stored_fields = json.loads(calls[3][1][9])
        self.assertEqual(second_stored_fields, {})

    async def test_loyalty_mapping_without_crm_risk_fields_uses_local_customer_source(self):
        local_rows = [
            {
                "customer_id": "crm-customer-1",
                "data": {
                    "name": "Actual CRM Customer",
                    "churn_risk": "0.82",
                    "last_purchase": "2026-01-10",
                    "feedback_score": "2",
                    "total_spend": "415.75",
                },
            }
        ]

        class Result:
            async def fetchall(self):
                return local_rows

        class AsyncContext:
            def __init__(self, value=None):
                self.value = value

            async def __aenter__(self):
                return self.value

            async def __aexit__(self, *_args):
                return False

        database_connection = Mock()
        calls = []

        async def execute(query, params=None):
            calls.append((query, params))
            return Result()

        database_connection.execute = AsyncMock(side_effect=execute)
        database_connection.transaction.return_value = AsyncContext()
        pool = Mock()
        pool.connection.return_value = AsyncContext(database_connection)
        loyalty_mapping = {
            "mapping_id": "loyalty-mapping",
            "connection_id": "connection-a",
            "table_name": "loyalty_customer_accounts",
            "field_map": {
                "loyalty_customer_id": {"canonical_field": "customer_id"},
                "name": {"canonical_field": "name"},
            },
        }

        with (
            patch.object(risk, "_approved_mapping", new_callable=AsyncMock) as mapping,
            patch.object(risk.psycopg.AsyncConnection, "connect", new_callable=AsyncMock) as connected_source,
        ):
            mapping.return_value = loyalty_mapping
            result = await risk.refresh_risk_snapshots(pool, "tenant-a")

        self.assertTrue(result["refreshed"])
        self.assertEqual(result["total_scored"], 1)
        self.assertEqual(result["high_risk"], 1)
        connected_source.assert_not_awaited()
        self.assertIn("FROM public.customers", calls[0][0])
        self.assertEqual(calls[0][1], ("tenant-a", 500))
        self.assertIn("DELETE FROM customer_risk_snapshots", calls[1][0])
        self.assertEqual(calls[2][1][0:5], (
            "tenant-a",
            None,
            None,
            "local",
            "crm-customer-1",
        ))

    async def test_empty_local_source_does_not_delete_existing_snapshots(self):
        class Result:
            async def fetchall(self):
                return []

        class AsyncContext:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

        connection = Mock()
        connection.execute = AsyncMock(return_value=Result())
        pool = Mock()
        pool.connection.return_value = AsyncContext()

        with (
            patch.object(risk, "_approved_mapping", new_callable=AsyncMock) as mapping,
            patch.object(risk, "_local_customer_rows", new_callable=AsyncMock, return_value=[]) as local_data,
        ):
            mapping.side_effect = LookupError("No approved mapping")
            with self.assertRaisesRegex(ValueError, "no usable customer records"):
                await risk.refresh_risk_snapshots(pool, "tenant-a")

        local_data.assert_awaited_once_with(pool, "tenant-a", 500)
        pool.connection.assert_not_called()

    async def test_local_source_read_failure_does_not_delete_existing_snapshots(self):
        pool = Mock()

        with (
            patch.object(risk, "_approved_mapping", new_callable=AsyncMock) as mapping,
            patch.object(risk, "_local_customer_rows", new_callable=AsyncMock) as local_data,
            patch.object(risk, "_score_customer") as score,
        ):
            mapping.side_effect = LookupError("No approved mapping")
            local_data.side_effect = RuntimeError("local database unavailable")
            with self.assertRaisesRegex(ValueError, "local tenant customer data"):
                await risk.refresh_risk_snapshots(pool, "tenant-a")

        local_data.assert_awaited_once_with(pool, "tenant-a", 500)
        score.assert_not_called()
        pool.connection.assert_not_called()

    async def test_connected_source_read_failure_does_not_score_or_persist_fallback_data(self):
        pool = Mock()
        mapping_value = {
            "mapping_id": "mapping-a",
            "connection_id": "connection-a",
            "encrypted_readonly_uri": "encrypted",
            "schema_name": "public",
            "table_name": "customers",
            "field_map": {
                "id": {"canonical_field": "customer_id"},
                "risk_value": {"canonical_field": "churn_risk"},
            },
        }

        with (
            patch.object(risk, "_approved_mapping", new_callable=AsyncMock) as mapping,
            patch.object(risk, "decrypt_token", return_value="redacted-uri"),
            patch.object(risk.psycopg.AsyncConnection, "connect", new_callable=AsyncMock) as connect,
            patch.object(risk, "_score_customer") as score,
            patch(
                "backend.app.crm.routes._get_tenant_customers_data",
                new_callable=AsyncMock,
            ) as fallback,
        ):
            mapping.return_value = mapping_value
            connect.side_effect = RuntimeError("connected source unavailable")

            with self.assertRaisesRegex(ValueError, "connected customer data"):
                await risk.refresh_risk_snapshots(pool, "tenant-a")

        score.assert_not_called()
        fallback.assert_not_awaited()
        pool.connection.assert_not_called()


class RiskRefreshPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_connected_data_is_scored_and_persisted(self):
        mapping_value = {
            "mapping_id": "mapping-a",
            "connection_id": "connection-a",
            "encrypted_readonly_uri": "encrypted",
            "schema_name": "public",
            "table_name": "customers",
            "field_map": {
                "id": {"canonical_field": "customer_id"},
                "risk_value": {"canonical_field": "churn_risk"},
            },
        }
        external_row = {"id": "customer-a", "risk_value": 1.0}

        class Result:
            async def fetchall(self):
                return [external_row]

        class AsyncContext:
            def __init__(self, value):
                self.value = value

            async def __aenter__(self):
                return self.value

            async def __aexit__(self, *_args):
                return False

        external_connection = Mock()
        external_connection.execute = AsyncMock(return_value=Result())
        external_connection.execute.side_effect = [
            Mock(),
            Result(),
        ]
        database_connection = Mock()
        database_connection.transaction.return_value = AsyncContext(None)
        database_connection.execute = AsyncMock()
        pool = Mock()
        pool.connection.return_value = AsyncContext(database_connection)

        with (
            patch.object(risk, "_approved_mapping", new_callable=AsyncMock) as mapping,
            patch.object(risk, "decrypt_token", return_value="redacted-uri"),
            patch.object(
                risk.psycopg.AsyncConnection,
                "connect",
                new_callable=AsyncMock,
                return_value=AsyncContext(external_connection),
            ),
        ):
            mapping.return_value = mapping_value
            result = await risk.refresh_risk_snapshots(pool, "tenant-a")

        self.assertTrue(result["refreshed"])
        self.assertEqual(result["total_scored"], 1)
        self.assertEqual(result["high_risk"], 1)
        self.assertEqual(database_connection.execute.await_count, 2)
        insert_call = database_connection.execute.await_args_list[1]
        self.assertEqual(insert_call.args[1][0:5], (
            "tenant-a",
            "connection-a",
            "mapping-a",
            "connected",
            "customer-a",
        ))


if __name__ == "__main__":
    unittest.main()
