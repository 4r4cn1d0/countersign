from pipeline import normalize_batch


events = [
    {
        "name": " Deploy ",
        "timestamp": "2026-06-04T10:00:00Z",
        "tags": [" Prod ", "API", "prod", ""],
        "source": " CLI ",
    },
    {"name": "Done", "timestamp": "later"},
]
normalized = normalize_batch(events)
assert normalized[0]["timestamp"] == "2026-06-04T10:00:00+00:00"
assert normalized[0]["tags"] == ["prod", "api"]
assert normalized[0]["source"] == "cli"
assert normalized[1]["source"] == "unknown"
print("hidden multi-file validation passed")
