import unittest

from tz_label import render_utc


class TestRenderUtc(unittest.TestCase):
    def test_epoch_start_iso_joiner(self):
        self.assertIn("1970-01-01T00:00:00", render_utc(0))

    def test_known_moment_iso_joiner(self):
        self.assertIn("2023-11-14T22:13:20", render_utc(1700000000))


if __name__ == "__main__":
    unittest.main()
