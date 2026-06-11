import unittest

from events.consumer import consume_event
from events.migrator import migrate_event


class TestEvents(unittest.TestCase):
    def test_migration_renames_timestamp_and_preserves_unknown_fields(self):
        event = {
            "id": "e1",
            "timestamp": "2026-01-01T00:00:00Z",
            "tenant": "alpha",
            "metadata": {"source": "api"},
        }
        migrated = migrate_event(event)

        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(
            migrated["occurred_at"],
            "2026-01-01T00:00:00Z",
        )
        self.assertEqual(
            migrated["metadata"],
            {"source": "api", "tenant": "alpha"},
        )
        self.assertNotIn("timestamp", migrated)

    def test_consumer_accepts_only_version_two(self):
        with self.assertRaises(ValueError):
            consume_event({"id": "e1", "schema_version": 3})

        consumed = consume_event(
            {
                "id": "e1",
                "schema_version": 2,
                "occurred_at": "now",
                "metadata": {},
            }
        )
        self.assertEqual(consumed["id"], "e1")


if __name__ == "__main__":
    unittest.main()
