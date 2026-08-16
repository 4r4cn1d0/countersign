import unittest

from toc_render import render


class TestRender(unittest.TestCase):
    def test_indents_by_level(self):
        self.assertEqual(
            render([(1, "A"), (2, "B")]),
            "- A\n  - B",
        )

    def test_empty_entries_render_empty(self):
        self.assertEqual(render([]), "")


if __name__ == "__main__":
    unittest.main()
