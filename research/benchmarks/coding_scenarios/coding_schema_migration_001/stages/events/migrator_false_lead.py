def migrate_event(event):
    return {
        "id": event["id"],
        "schema_version": 2,
        "occurred_at": event["timestamp"],
        "metadata": {},
    }
