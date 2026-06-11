import unittest

from events.migrator import migrate_event
from events.serializer import public_event


class TestSchemaContract(unittest.TestCase):
    def test_public_shape_excludes_legacy_timestamp(self):
        migrated = migrate_event(
            {"id": "e1", "timestamp": "now", "tenant": "alpha"}
        )
        self.assertEqual(
            set(public_event(migrated)),
            {"id", "schema_version", "occurred_at", "metadata"},
        )
        self.assertEqual(public_event(migrated)["metadata"]["tenant"], "alpha")


if __name__ == "__main__":
    unittest.main()
