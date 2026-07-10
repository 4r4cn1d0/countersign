import unittest

from flag_report import describe


class TestFlagReport(unittest.TestCase):
    def test_describes_states(self):
        self.assertEqual(describe(True), "enabled")
        self.assertEqual(describe(False), "disabled")


if __name__ == "__main__":
    unittest.main()
