import unittest

from toc import toc_entries


class TestTocEntries(unittest.TestCase):
    def test_simple_heading(self):
        self.assertEqual(toc_entries("## Setup"), [(2, "Setup")])

    def test_hash_in_title_does_not_change_level(self):
        self.assertEqual(toc_entries("# C# Notes"), [(1, "C# Notes")])


if __name__ == "__main__":
    unittest.main()
