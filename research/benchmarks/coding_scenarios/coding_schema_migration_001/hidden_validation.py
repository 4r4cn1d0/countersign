from events.consumer import consume_event
from events.migrator import migrate_event
from events.serializer import public_event


source = {
    "id": "evt-9",
    "timestamp": "2026-06-11T10:00:00Z",
    "tenant": "alpha",
    "priority": 3,
    "metadata": {"origin": "worker"},
}
migrated = migrate_event(source)
assert migrated == {
    "id": "evt-9",
    "schema_version": 2,
    "occurred_at": "2026-06-11T10:00:00Z",
    "metadata": {
        "origin": "worker",
        "tenant": "alpha",
        "priority": 3,
    },
}
assert consume_event(migrated)["metadata"]["tenant"] == "alpha"
assert set(public_event(migrated)) == {
    "id",
    "schema_version",
    "occurred_at",
    "metadata",
}
try:
    consume_event({"id": "bad", "schema_version": 1})
except ValueError:
    pass
else:
    raise AssertionError("version-one event was not rejected")
print("hidden schema migration validation passed")
