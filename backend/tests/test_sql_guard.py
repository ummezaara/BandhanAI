import unittest

from backend.app.agents.analytics_chat.sql_guard import validate_query


class SqlGuardTests(unittest.TestCase):
    def test_allows_select_query(self):
        is_safe, error = validate_query(
            "SELECT name, total FROM public.orders ORDER BY total DESC LIMIT 10"
        )

        self.assertTrue(is_safe)
        self.assertEqual(error, "")

    def test_blocks_mutating_query(self):
        is_safe, error = validate_query("DELETE FROM public.orders")

        self.assertFalse(is_safe)
        self.assertIn("DELETE", error)

    def test_blocks_multiple_statements(self):
        is_safe, error = validate_query("SELECT * FROM public.orders; SELECT now();")

        self.assertFalse(is_safe)
        self.assertIn("one SQL statement", error)


if __name__ == "__main__":
    unittest.main()
