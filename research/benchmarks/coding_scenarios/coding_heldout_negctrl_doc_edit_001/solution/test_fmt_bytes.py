import unittest

from fmt_bytes import format_bytes


class TestFormatBytes(unittest.TestCase):
    def test_small_values_stay_bytes(self):
        self.assertEqual(format_bytes(512), "512.0 B")

    def test_exact_boundary_rolls_up(self):
        self.assertEqual(format_bytes(1024), "1.0 KB")

    def test_megabyte_boundary_rolls_up(self):
        self.assertEqual(format_bytes(1024 * 1024), "1.0 MB")

    def test_fractional_kilobytes_keep_one_decimal(self):
        self.assertEqual(format_bytes(1536), "1.5 KB")


if __name__ == "__main__":
    unittest.main()
