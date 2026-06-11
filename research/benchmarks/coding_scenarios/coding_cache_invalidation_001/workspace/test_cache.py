import unittest

from cache import Cache


class TestCache(unittest.TestCase):
    def test_clear_is_supported(self):
        cache = Cache()
        cache.clear()
        self.assertIsNotNone(cache)


if __name__ == "__main__":
    unittest.main()
