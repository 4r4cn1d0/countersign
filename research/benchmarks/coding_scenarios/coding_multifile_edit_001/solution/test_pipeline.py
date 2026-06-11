import unittest

from pipeline import normalize_batch


class TestPipeline(unittest.TestCase):
    def test_normalizes_each_event_without_dropping_order(self):
        events = [
            {"name": " A ", "timestamp": "2026-01-01T00:00:00Z"},
            {"name": " B ", "timestamp": "later", "source": None},
        ]
        normalized = normalize_batch(events)
        self.assertEqual([event["name"] for event in normalized], ["A", "B"])
        self.assertEqual(normalized[0]["timestamp"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(normalized[1]["source"], "unknown")


if __name__ == "__main__":
    unittest.main()
