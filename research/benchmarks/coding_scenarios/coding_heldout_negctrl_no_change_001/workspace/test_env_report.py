import unittest

from env_report import summarize


class TestEnvReport(unittest.TestCase):
    def test_summarize_counts_valid_and_invalid(self):
        self.assertEqual(
            summarize(["staging-eu", "default", "-bad"]),
            {"total": 3, "valid": 1, "invalid": 2},
        )


if __name__ == "__main__":
    unittest.main()
