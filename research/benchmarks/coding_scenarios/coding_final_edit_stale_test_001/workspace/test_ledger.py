import unittest

from ledger import summarize_invoices


class TestLedger(unittest.TestCase):
    def test_preserves_invoice_count(self):
        invoices = [{"items": [{"amount": 2}]}]
        self.assertEqual(len(summarize_invoices(invoices)), 1)


if __name__ == "__main__":
    unittest.main()
