import unittest

from dedupe import dedupe


class TestDedupe(unittest.TestCase):
    def test_removes_duplicates(self):
        self.assertEqual(sorted(dedupe(["a", "b", "a"])), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
