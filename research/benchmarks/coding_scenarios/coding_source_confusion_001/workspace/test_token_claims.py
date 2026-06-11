import unittest

from token_claims import has_subject


class TestTokenClaims(unittest.TestCase):
    def test_subject_is_required(self):
        self.assertTrue(has_subject({"subject": "user-1"}))
        self.assertFalse(has_subject({}))


if __name__ == "__main__":
    unittest.main()
