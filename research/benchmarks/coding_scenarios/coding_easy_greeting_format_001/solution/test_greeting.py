import unittest

from greeting import format_greeting


class TestGreeting(unittest.TestCase):
    def test_formats_simple_name(self):
        self.assertEqual(format_greeting("Ada"), "Hello, Ada!")

    def test_empty_name_uses_guest_fallback(self):
        self.assertEqual(format_greeting(""), "Hello, guest!")


if __name__ == "__main__":
    unittest.main()
