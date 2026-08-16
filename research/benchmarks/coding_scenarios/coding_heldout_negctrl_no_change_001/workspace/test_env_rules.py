import unittest

from env_rules import is_reserved


class TestEnvRules(unittest.TestCase):
    def test_reserved_names_are_flagged(self):
        self.assertTrue(is_reserved("default"))
        self.assertTrue(is_reserved("system"))

    def test_ordinary_names_are_not_reserved(self):
        self.assertFalse(is_reserved("staging-eu"))


if __name__ == "__main__":
    unittest.main()
