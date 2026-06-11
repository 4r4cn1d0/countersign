import unittest

from cache import Cache


class TestCache(unittest.TestCase):
    def test_namespaces_are_isolated_and_clearable(self):
        cache = Cache()
        cache.set("alpha", "1", {"name": "Ada"})
        cache.set("beta", "1", {"name": "Grace"})
        cache.clear_namespace("alpha")

        self.assertIsNone(cache.get("alpha", "1"))
        self.assertEqual(cache.get("beta", "1"), {"name": "Grace"})


if __name__ == "__main__":
    unittest.main()
