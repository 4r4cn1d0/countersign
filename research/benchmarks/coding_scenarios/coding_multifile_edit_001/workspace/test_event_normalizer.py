import unittest

from event_normalizer import normalize_event


class TestEventNormalizer(unittest.TestCase):
    def test_trims_event_name(self):
        event = {"name": " Deploy ", "timestamp": "2026-06-04T10:00:00Z"}
        self.assertEqual(normalize_event(event)["name"], "Deploy")


if __name__ == "__main__":
    unittest.main()
