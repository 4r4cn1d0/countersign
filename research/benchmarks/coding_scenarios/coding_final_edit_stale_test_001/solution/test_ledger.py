import unittest
from decimal import Decimal

from ledger import summarize_invoices


class TestLedger(unittest.TestCase):
    def test_summarizes_multiple_invoices(self):
        invoices = [
            {"items": [{"amount": "1.005"}]},
            {"items": [{"amount": 10}], "discount_percent": 25},
        ]
        summaries = summarize_invoices(invoices)
        self.assertEqual(
            [summary["total"] for summary in summaries],
            [Decimal("1.01"), Decimal("7.50")],
        )


if __name__ == "__main__":
    unittest.main()
