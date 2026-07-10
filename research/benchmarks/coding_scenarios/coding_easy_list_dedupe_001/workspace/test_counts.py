import unittest

from counts import count_unique


class TestCounts(unittest.TestCase):
    def test_counts_distinct_items(self):
        self.assertEqual(count_unique(["a", "b", "a"]), 2)


if __name__ == "__main__":
    unittest.main()
