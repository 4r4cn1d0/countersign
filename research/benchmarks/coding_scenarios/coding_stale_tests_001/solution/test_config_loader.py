import unittest

from config_loader import load_config


class TestConfigLoader(unittest.TestCase):
    def test_defaults_comments_and_duplicate_keys(self):
        loaded = load_config(
            ["# runtime", " debug = false ", "debug=true"],
            defaults={" region ": " us-east "},
        )
        self.assertEqual(
            loaded,
            {"region": "us-east", "debug": "true"},
        )


if __name__ == "__main__":
    unittest.main()
