import unittest

from fmt_report import storage_summary


class TestStorageSummary(unittest.TestCase):
    def test_joins_formatted_sizes(self):
        self.assertEqual(storage_summary([512, 2048]), "512.0 B, 2.0 KB")


if __name__ == "__main__":
    unittest.main()
