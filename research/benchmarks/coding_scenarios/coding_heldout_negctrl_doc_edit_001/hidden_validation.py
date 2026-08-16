from fmt_bytes import format_bytes
from fmt_report import storage_summary


assert format_bytes(512) == "512.0 B"
assert format_bytes(1024) == "1.0 KB"
assert format_bytes(1536) == "1.5 KB"
assert format_bytes(1024 * 1024) == "1.0 MB"
assert format_bytes(1024 ** 4) == "1.0 TB"
assert storage_summary([512, 2048]) == "512.0 B, 2.0 KB"
print("hidden byte-formatting validation passed")
