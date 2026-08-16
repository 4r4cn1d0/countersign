import unittest

from col_stats import column_max, column_mean


class TestColumnStats(unittest.TestCase):
    def test_mean_of_dense_column(self):
        self.assertEqual(column_mean(["2", "4"]), 3.0)

    def test_blank_cells_are_skipped(self):
        self.assertEqual(column_mean(["4", "", "8"]), 6.0)

    def test_all_blank_column_means_zero(self):
        self.assertEqual(column_mean(["", "  ", ""]), 0.0)

    def test_max_ignores_blanks(self):
        self.assertEqual(column_max(["4", "", "8"]), 8.0)

    def test_empty_column_max_is_zero(self):
        self.assertEqual(column_max([]), 0.0)


if __name__ == "__main__":
    unittest.main()
