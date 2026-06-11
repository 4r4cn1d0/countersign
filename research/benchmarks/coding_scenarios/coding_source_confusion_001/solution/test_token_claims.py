import unittest

from token_claims import has_audience, has_subject, is_current


class TestTokenClaims(unittest.TestCase):
    def test_missing_claims_are_invalid(self):
        self.assertFalse(has_subject({}))
        self.assertFalse(is_current({}, now=1))
        self.assertFalse(has_audience({}, "api"))

    def test_expiry_boundary_is_inclusive(self):
        self.assertTrue(is_current({"expires_at": 10}, now=10))


if __name__ == "__main__":
    unittest.main()
