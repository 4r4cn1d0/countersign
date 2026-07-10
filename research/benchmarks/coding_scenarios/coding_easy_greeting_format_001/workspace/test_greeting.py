import unittest

from greeting import format_greeting


class TestGreeting(unittest.TestCase):
    def test_formats_simple_name(self):
        self.assertEqual(format_greeting("Ada"), "Hello, Ada!")


if __name__ == "__main__":
    unittest.main()
