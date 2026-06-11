import unittest

from pipeline import normalize_batch


class TestPipeline(unittest.TestCase):
    def test_preserves_batch_size(self):
        events = [{"name": "A", "timestamp": "now"}]
        self.assertEqual(len(normalize_batch(events)), 1)


if __name__ == "__main__":
    unittest.main()
