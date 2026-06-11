import unittest

from config_parser import parse_line


class TestConfigParser(unittest.TestCase):
    def test_strips_key_and_value(self):
        self.assertEqual(parse_line(" debug = true "), ("debug", "true"))

    def test_ignores_blank_and_comment_lines(self):
        self.assertIsNone(parse_line("  "))
        self.assertIsNone(parse_line("  # disabled"))

    def test_rejects_malformed_line(self):
        with self.assertRaises(ValueError):
            parse_line("debug")


if __name__ == "__main__":
    unittest.main()
