import unittest

from dedupe import dedupe


class TestDedupe(unittest.TestCase):
    def test_removes_duplicates(self):
        self.assertEqual(dedupe(["a", "b", "a"]), ["a", "b"])

    def test_preserves_first_seen_order(self):
        self.assertEqual(dedupe(["b", "a", "b", "c"]), ["b", "a", "c"])

    def test_empty_input(self):
        self.assertEqual(dedupe([]), [])


if __name__ == "__main__":
    unittest.main()
