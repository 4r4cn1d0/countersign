import unittest

from tz_report import label_event


class TestLabelEvent(unittest.TestCase):
    def test_prefixes_name(self):
        self.assertTrue(label_event("deploy", 0).startswith("deploy @ "))

    def test_contains_date(self):
        self.assertIn("1970-01-01", label_event("build", 0))


if __name__ == "__main__":
    unittest.main()
