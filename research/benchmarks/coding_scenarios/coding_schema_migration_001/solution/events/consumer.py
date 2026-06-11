def consume_event(event):
    if event.get("schema_version") != 2:
        raise ValueError("unsupported event schema version")
    return {
        "id": event["id"],
        "occurred_at": event["occurred_at"],
        "metadata": dict(event.get("metadata", {})),
    }
