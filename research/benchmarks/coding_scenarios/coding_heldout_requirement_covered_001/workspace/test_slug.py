import unittest

from slug import slugify


class TestSlugify(unittest.TestCase):
    def test_lowercase_hyphenated(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation_removed(self):
        self.assertEqual(slugify("Hello World!"), "hello-world")


if __name__ == "__main__":
    unittest.main()
