import unittest
from decimal import Decimal

from invoice import invoice_summary


class TestInvoice(unittest.TestCase):
    def test_decimal_discount_and_display(self):
        summary = invoice_summary(
            [{"amount": "2.10"}, {"amount": "3.235"}],
            discount_percent="10",
        )
        self.assertEqual(summary["total"], Decimal("4.80"))
        self.assertEqual(summary["display_total"], "$4.80")
        self.assertEqual(summary["discount_percent"], "10")


if __name__ == "__main__":
    unittest.main()
