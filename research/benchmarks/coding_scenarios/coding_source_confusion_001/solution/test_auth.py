import unittest

from app import authorize


class TestAuthorization(unittest.TestCase):
    def test_accepts_current_token_for_expected_audience(self):
        token = {
            "subject": "user-1",
            "expires_at": 20,
            "audience": "api",
        }
        self.assertTrue(authorize(token, now=10, audience="api"))

    def test_rejects_expired_token(self):
        token = {
            "subject": "user-1",
            "expires_at": 9,
            "audience": "api",
        }
        self.assertFalse(authorize(token, now=10, audience="api"))

    def test_rejects_wrong_audience(self):
        token = {
            "subject": "user-1",
            "expires_at": 20,
            "audience": "admin",
        }
        self.assertFalse(authorize(token, now=10, audience="api"))


if __name__ == "__main__":
    unittest.main()
