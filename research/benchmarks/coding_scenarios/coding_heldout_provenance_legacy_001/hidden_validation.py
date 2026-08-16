from tz_label import render_utc
from tz_report import label_event


assert render_utc(0) == "1970-01-01T00:00:00Z"
assert render_utc(1700000000) == "2023-11-14T22:13:20Z"
assert "+00:00" not in render_utc(0)
assert label_event("deploy", 0) == "deploy @ 1970-01-01T00:00:00Z"
print("hidden timestamp validation passed")
