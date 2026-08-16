import unittest

from export_util import render_row, render_table


class TestExportUtil(unittest.TestCase):
    def test_render_row_joins_with_commas(self):
        self.assertEqual(render_row(["a", 1]), "a,1")

    def test_render_table_joins_rows(self):
        self.assertEqual(render_table([["a", 1], ["b", 2]]), "a,1\nb,2")


if __name__ == "__main__":
    unittest.main()
