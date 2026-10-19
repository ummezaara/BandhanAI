import unittest

from backend.app.connections.discovery import (
    _apply_field_assignments,
    update_customer_mapping_fields,
)


class _Result:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def transaction(self):
        return self

    async def execute(self, query, params=None):
        self.calls.append((str(query), params))
        return _Result(self.row)


class _Pool:
    def __init__(self, connection):
        self.conn = connection

    def connection(self):
        return self.conn


class CustomerMappingFieldAssignmentTests(unittest.TestCase):
    def setUp(self):
        self.available_columns = {
            "customer_id",
            "email",
            "last_order_at",
            "created_at",
            "updated_at",
            "rating",
        }
        self.existing_mapping = {
            "customer_id": {
                "source_column": "customer_id",
                "canonical_field": "customer_id",
                "confidence": 0.95,
                "reason": "Identifier alias.",
            },
            "email": {
                "source_column": "email",
                "canonical_field": "email",
                "confidence": 0.95,
                "reason": "Email alias.",
            },
        }

    def test_assigns_supported_risk_field_and_preserves_existing_fields(self):
        updated = _apply_field_assignments(
            self.existing_mapping,
            {"last_order_at": "last_purchase"},
            self.available_columns,
        )

        self.assertEqual(updated["last_order_at"]["canonical_field"], "last_purchase")
        self.assertEqual(updated["email"], self.existing_mapping["email"])
        self.assertEqual(updated["customer_id"], self.existing_mapping["customer_id"])

    def test_rejects_fields_not_in_selected_table(self):
        with self.assertRaisesRegex(ValueError, "not present"):
            _apply_field_assignments(
                self.existing_mapping,
                {"unknown_column": "churn_risk"},
                self.available_columns,
            )

    def test_accepts_all_supported_customer_fields(self):
        supported_fields = (
            "customer_id",
            "name",
            "email",
            "phone",
            "total_spend",
            "total_orders",
            "last_purchase",
            "churn_risk",
            "feedback_score",
        )
        for field in supported_fields:
            with self.subTest(field=field):
                updated = _apply_field_assignments(
                    self.existing_mapping,
                    {"rating": field},
                    self.available_columns,
                )
                self.assertEqual(updated["rating"]["canonical_field"], field)

    def test_rejects_unsupported_canonical_field(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            _apply_field_assignments(
                self.existing_mapping,
                {"rating": "region"},
                self.available_columns,
            )

    def test_created_and_updated_timestamps_cannot_become_last_purchase(self):
        for column in ("created_at", "updated_at"):
            with self.subTest(column=column):
                with self.assertRaisesRegex(ValueError, "cannot be assigned"):
                    _apply_field_assignments(
                        self.existing_mapping,
                        {column: "last_purchase"},
                        self.available_columns,
                    )

    def test_rejects_duplicate_field_assignments_in_same_save(self):
        with self.assertRaisesRegex(ValueError, "only one source column"):
            _apply_field_assignments(
                self.existing_mapping,
                {
                    "last_order_at": "last_purchase",
                    "rating": "last_purchase",
                },
                self.available_columns,
            )

    def test_null_assignment_removes_only_that_column(self):
        updated = _apply_field_assignments(
            {
                **self.existing_mapping,
                "last_order_at": {
                    "source_column": "last_order_at",
                    "canonical_field": "last_purchase",
                    "confidence": 1.0,
                    "reason": "Previously assigned.",
                },
            },
            {"last_order_at": None},
            self.available_columns,
        )

        self.assertNotIn("last_order_at", updated)
        self.assertIn("email", updated)

    def test_explicit_reassignment_replaces_previous_source_and_preserves_others(self):
        existing = {
            **self.existing_mapping,
            "old_spend": {
                "source_column": "old_spend",
                "canonical_field": "total_spend",
                "confidence": 0.9,
                "reason": "Automatic mapping.",
            },
        }
        updated = _apply_field_assignments(
            existing,
            {"rating": "total_spend"},
            self.available_columns | {"old_spend"},
        )

        self.assertNotIn("old_spend", updated)
        self.assertEqual(updated["rating"]["canonical_field"], "total_spend")
        self.assertIn("email", updated)

    def test_update_lookup_is_scoped_to_tenant_and_missing_mapping_is_not_updated(self):
        connection = _Connection(None)
        pool = _Pool(connection)

        with self.assertRaises(LookupError):
            import asyncio

            asyncio.run(
                update_customer_mapping_fields(
                    pool,
                    "tenant-a",
                    "mapping-a",
                    {"rating": "feedback_score"},
                )
            )

        self.assertEqual(connection.calls[0][1], ("tenant-a", "mapping-a"))
        self.assertIn("m.org_id = %s", connection.calls[0][0])
        self.assertEqual(len(connection.calls), 1)


if __name__ == "__main__":
    unittest.main()
