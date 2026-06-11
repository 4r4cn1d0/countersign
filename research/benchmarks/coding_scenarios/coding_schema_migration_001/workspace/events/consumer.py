def consume_event(event):
    return {
        "id": event["id"],
        "occurred_at": event.get("occurred_at", event.get("timestamp")),
        "metadata": event.get("metadata", {}),
    }
