import unittest

from event_normalizer import normalize_event


class TestEventNormalizer(unittest.TestCase):
    def test_normalizes_all_fields(self):
        event = {
            "name": " Deploy ",
            "timestamp": "2026-06-04T10:00:00Z",
            "tags": [" Prod ", "", "API", "prod"],
            "source": " Worker ",
        }
        self.assertEqual(
            normalize_event(event),
            {
                "name": "Deploy",
                "timestamp": "2026-06-04T10:00:00+00:00",
                "tags": ["prod", "api"],
                "source": "worker",
            },
        )


if __name__ == "__main__":
    unittest.main()
