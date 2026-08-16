import unittest

from slug import slugify


class TestSlugify(unittest.TestCase):
    def test_lowercase_hyphenated(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation_removed(self):
        self.assertEqual(slugify("Hello World!"), "hello-world")

    def test_consecutive_spaces_collapse(self):
        self.assertEqual(slugify("Release  Notes"), "release-notes")

    def test_existing_hyphens_collapse(self):
        self.assertEqual(slugify("A -- B"), "a-b")


if __name__ == "__main__":
    unittest.main()
