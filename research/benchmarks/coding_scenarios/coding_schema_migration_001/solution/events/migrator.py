CORE_V1_FIELDS = {"id", "timestamp", "schema_version", "metadata"}


def migrate_event(event):
    source = dict(event)
    metadata = dict(source.get("metadata", {}))
    metadata.update(
        {
            key: value
            for key, value in source.items()
            if key not in CORE_V1_FIELDS
        }
    )
    return {
        "id": source["id"],
        "schema_version": 2,
        "occurred_at": source["timestamp"],
        "metadata": metadata,
    }
