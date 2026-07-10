import unittest

from feature_flags import is_enabled


class TestFeatureFlags(unittest.TestCase):
    def test_on_is_enabled(self):
        self.assertTrue(is_enabled("on"))


if __name__ == "__main__":
    unittest.main()
