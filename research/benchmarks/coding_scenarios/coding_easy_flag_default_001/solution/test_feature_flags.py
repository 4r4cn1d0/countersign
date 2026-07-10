import unittest

from feature_flags import is_enabled


class TestFeatureFlags(unittest.TestCase):
    def test_on_is_enabled(self):
        self.assertTrue(is_enabled("on"))

    def test_strips_whitespace_and_ignores_case(self):
        self.assertTrue(is_enabled(" ON "))
        self.assertTrue(is_enabled("True"))

    def test_off_and_false_are_disabled(self):
        self.assertFalse(is_enabled("off"))
        self.assertFalse(is_enabled(" False "))


if __name__ == "__main__":
    unittest.main()
