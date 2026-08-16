import unittest

from tz_label import render_utc


class TestRenderUtc(unittest.TestCase):
    def test_epoch_start_iso_z(self):
        self.assertEqual(render_utc(0), "1970-01-01T00:00:00Z")

    def test_returns_string(self):
        self.assertIsInstance(render_utc(1700000000), str)


if __name__ == "__main__":
    unittest.main()
