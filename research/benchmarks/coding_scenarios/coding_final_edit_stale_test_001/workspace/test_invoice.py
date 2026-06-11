import unittest

from invoice import invoice_summary


class TestInvoice(unittest.TestCase):
    def test_integer_total(self):
        summary = invoice_summary([{"amount": 2}, {"amount": 3}])
        self.assertEqual(summary["total"], 5)


if __name__ == "__main__":
    unittest.main()
