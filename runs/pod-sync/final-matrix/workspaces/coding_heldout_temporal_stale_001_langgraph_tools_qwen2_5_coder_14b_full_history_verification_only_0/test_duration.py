import unittest

from duration import format_duration


class TestFormatDuration(unittest.TestCase):
    def test_minutes_seconds(self):
        self.assertEqual(format_duration(90), "1m 30s")

    def test_zero(self):
        self.assertEqual(format_duration(0), "0m 0s")

    def test_returns_string(self):
        self.assertIsInstance(format_duration(3661), str)


if __name__ == "__main__":
    unittest.main()
