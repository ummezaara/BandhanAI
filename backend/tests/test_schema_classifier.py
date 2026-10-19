import unittest

from backend.app.agents.schema_discovery.classifier import classify_tables


class SchemaClassifierTests(unittest.TestCase):
    def test_classifies_common_commerce_schema(self):
        tables = [
            {"table": "public.users"},
            {"table": "public.orders"},
            {"table": "public.order_items"},
            {"table": "public.products"},
        ]
        columns = [
            {"table": "public.users", "column": "id"},
            {"table": "public.users", "column": "email"},
            {"table": "public.orders", "column": "id"},
            {"table": "public.orders", "column": "user_id"},
            {"table": "public.orders", "column": "total"},
            {"table": "public.order_items", "column": "order_id"},
            {"table": "public.order_items", "column": "product_id"},
            {"table": "public.order_items", "column": "quantity"},
            {"table": "public.products", "column": "name"},
            {"table": "public.products", "column": "price"},
        ]
        fks = [
            {"from_table": "public.orders", "to_table": "public.users"},
            {"from_table": "public.order_items", "to_table": "public.orders"},
            {"from_table": "public.order_items", "to_table": "public.products"},
        ]

        entity_map, confidence = classify_tables(tables, columns, fks)

        self.assertEqual(entity_map["customer"], "public.users")
        self.assertEqual(entity_map["order"], "public.orders")
        self.assertEqual(entity_map["order_item"], "public.order_items")
        self.assertEqual(entity_map["product"], "public.products")
        self.assertGreater(confidence, 0.5)


if __name__ == "__main__":
    unittest.main()
