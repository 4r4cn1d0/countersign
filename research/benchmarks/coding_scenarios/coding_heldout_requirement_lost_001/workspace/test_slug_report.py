import unittest

from slug_report import describe_slug


class TestDescribeSlug(unittest.TestCase):
    def test_contains_arrow(self):
        self.assertIn(" -> ", describe_slug("Hello"))

    def test_lowercases(self):
        self.assertIn("hello", describe_slug("Hello"))


if __name__ == "__main__":
    unittest.main()
