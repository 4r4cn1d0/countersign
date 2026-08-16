import unittest

from toc import toc_entries


class TestTocEntries(unittest.TestCase):
    def test_simple_heading(self):
        self.assertEqual(toc_entries("## Setup"), [(2, "Setup")])

    def test_hash_in_title_does_not_change_level(self):
        self.assertEqual(toc_entries("# C# Notes"), [(1, "C# Notes")])

    def test_hash_later_in_line_is_not_a_heading(self):
        self.assertEqual(toc_entries("uses #tags inline"), [])

    def test_three_level_nesting(self):
        text = "# A\n## B\n### C\n"
        self.assertEqual(
            toc_entries(text), [(1, "A"), (2, "B"), (3, "C")]
        )


if __name__ == "__main__":
    unittest.main()
