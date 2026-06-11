import unittest

from events.consumer import consume_event
from events.migrator import migrate_event


class TestEvents(unittest.TestCase):
    def test_sets_schema_version(self):
        event = {"id": "e1", "timestamp": "2026-01-01T00:00:00Z"}
        self.assertEqual(migrate_event(event)["schema_version"], 2)

    def test_consumer_reads_old_timestamp(self):
        event = {"id": "e1", "timestamp": "2026-01-01T00:00:00Z"}
        self.assertEqual(
            consume_event(event)["occurred_at"],
            "2026-01-01T00:00:00Z",
        )


if __name__ == "__main__":
    unittest.main()
