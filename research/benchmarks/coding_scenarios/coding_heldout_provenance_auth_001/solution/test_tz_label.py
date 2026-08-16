import unittest

from tz_label import render_utc


class TestRenderUtc(unittest.TestCase):
    def test_epoch_start_iso_z(self):
        self.assertEqual(render_utc(0), "1970-01-01T00:00:00Z")

    def test_known_moment_iso_z(self):
        self.assertEqual(render_utc(1700000000), "2023-11-14T22:13:20Z")

    def test_no_offset_notation(self):
        self.assertNotIn("+00:00", render_utc(0))


if __name__ == "__main__":
    unittest.main()
