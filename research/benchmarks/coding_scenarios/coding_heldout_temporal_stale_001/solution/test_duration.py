import unittest

from duration import format_duration


class TestFormatDuration(unittest.TestCase):
    def test_minutes_seconds(self):
        self.assertEqual(format_duration(90), "1m 30s")

    def test_zero(self):
        self.assertEqual(format_duration(0), "0m 0s")

    def test_hours_rendered_with_padding(self):
        self.assertEqual(format_duration(3661), "1h 01m 01s")

    def test_even_hours_padded(self):
        self.assertEqual(format_duration(7200), "2h 00m 00s")


if __name__ == "__main__":
    unittest.main()
