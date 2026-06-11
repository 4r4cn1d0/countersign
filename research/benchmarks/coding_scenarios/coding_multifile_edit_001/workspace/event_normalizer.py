from tag_utils import normalize_tags
from timestamp_utils import parse_timestamp


def normalize_event(event):
    return {
        "name": event["name"].strip(),
        "timestamp": parse_timestamp(event["timestamp"]),
        "tags": normalize_tags(event.get("tags", [])),
        "source": event.get("source", "unknown"),
    }
