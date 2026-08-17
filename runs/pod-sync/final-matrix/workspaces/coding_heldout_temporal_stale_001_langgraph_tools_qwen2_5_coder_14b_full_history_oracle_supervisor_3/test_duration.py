import unittest
from duration import format_duration

class TestFormatDuration(unittest.TestCase):
    def test_positive_durations(self):
        self.assertEqual(format_duration(3661), '1h 01m 01s')
        self.assertEqual(format_duration(7200), '2h 00m 00s')
    
    def test_minutes_seconds(self):
        self.assertEqual(format_duration(90), '0h 01m 30s')
    
    def test_zero(self):
        self.assertEqual(format_duration(0), '0h 00m 00s')
    
    def test_negative_duration(self):
        with self.assertRaises(ValueError):
            format_duration(-1)
