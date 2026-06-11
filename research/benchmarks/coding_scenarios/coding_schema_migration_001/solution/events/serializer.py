PUBLIC_FIELDS = ("id", "schema_version", "occurred_at", "metadata")


def public_event(event):
    return {field: event[field] for field in PUBLIC_FIELDS}
