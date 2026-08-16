import unittest

from env_validator import is_valid_env_name


class TestEnvValidator(unittest.TestCase):
    def test_hyphenated_names_are_accepted(self):
        self.assertTrue(is_valid_env_name("staging-eu"))

    def test_plain_names_are_accepted(self):
        self.assertTrue(is_valid_env_name("prod"))

    def test_double_hyphen_is_rejected(self):
        self.assertFalse(is_valid_env_name("staging--eu"))

    def test_leading_hyphen_is_rejected(self):
        self.assertFalse(is_valid_env_name("-staging"))

    def test_trailing_hyphen_is_rejected(self):
        self.assertFalse(is_valid_env_name("staging-"))

    def test_uppercase_is_rejected(self):
        self.assertFalse(is_valid_env_name("Staging"))


if __name__ == "__main__":
    unittest.main()
