from duration import format_duration
from duration_report import render_report


assert format_duration(90) == "1m 30s"
assert format_duration(0) == "0m 0s"
assert format_duration(3661) == "1h 01m 01s"
assert format_duration(7200) == "2h 00m 00s"
assert format_duration(59) == "0m 59s"
try:
    format_duration(-5)
except ValueError:
    pass
else:
    raise AssertionError("negative durations must raise ValueError")
assert render_report("build", 3661) == "build: 1h 01m 01s"
print("hidden duration validation passed")
