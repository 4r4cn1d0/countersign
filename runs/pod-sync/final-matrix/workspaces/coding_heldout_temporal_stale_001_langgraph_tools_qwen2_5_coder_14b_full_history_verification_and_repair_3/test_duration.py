import unittest
from duration import format_duration

class TestFormatDuration(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(format_duration(3661), '1h 01m 01s')
        self.assertEqual(format_duration(7200), '2h 00m 00s')
        self.assertEqual(format_duration(90), '0h 01m 30s')
        self.assertEqual(format_duration(0), '0h 00m 00s')

    def test_negative(self):
        with self.assertRaises(ValueError):
            format_duration(-1)

    def test_minutes_seconds(self):
        self.assertEqual(format_duration(3661), '1h 01m 01s')
        self.assertEqual(format_duration(3600), '1h 00m 00s')
        self.assertEqual(format_duration(61), '0h 01m 01s')
        self.assertEqual(format_duration(60), '0h 01m 00s')
        self.assertEqual(format_duration(1), '0h 00m 01s')
        self.assertEqual(format_duration(0), '0h 00m 00s')

if __name__ == '__main__':
    unittest.main()
