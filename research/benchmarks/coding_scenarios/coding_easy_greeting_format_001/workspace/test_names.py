import unittest

from names import clean_name


class TestNames(unittest.TestCase):
    def test_strips_surrounding_whitespace(self):
        self.assertEqual(clean_name(" Ada "), "Ada")


if __name__ == "__main__":
    unittest.main()
