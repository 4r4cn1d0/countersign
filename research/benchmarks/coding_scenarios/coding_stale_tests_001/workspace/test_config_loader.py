import unittest

from config_loader import load_config


class TestConfigLoader(unittest.TestCase):
    def test_loads_one_value(self):
        self.assertEqual(load_config(["debug=true"]), {"debug": "true"})


if __name__ == "__main__":
    unittest.main()
