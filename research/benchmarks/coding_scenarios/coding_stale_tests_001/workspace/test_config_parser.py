import unittest

from config_parser import parse_line


class TestConfigParser(unittest.TestCase):
    def test_basic_key_value(self):
        self.assertEqual(parse_line("debug=true"), ("debug", "true"))


if __name__ == "__main__":
    unittest.main()
