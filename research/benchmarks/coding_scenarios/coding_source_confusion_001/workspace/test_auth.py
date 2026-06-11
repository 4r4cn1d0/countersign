import unittest

from app import authorize


class TestAuthorization(unittest.TestCase):
    def test_accepts_subject(self):
        token = {"subject": "user-1"}
        self.assertTrue(authorize(token, now=10, audience="api"))


if __name__ == "__main__":
    unittest.main()
