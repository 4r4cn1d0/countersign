import unittest

from duration_report import render_report


class TestRenderReport(unittest.TestCase):
    def test_prefixes_name(self):
        self.assertTrue(render_report("build", 60).startswith("build: "))

    def test_renders_minutes(self):
        self.assertIn("m", render_report("deploy", 90))


if __name__ == "__main__":
    unittest.main()
