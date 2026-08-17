# Timestamp Label Utilities

Helpers for rendering event timestamps in exported logs.

- `tz_label.py` — `render_utc(epoch_seconds)` renders a UTC timestamp label.
- `tz_report.py` — `label_event(name, epoch_seconds)` prefixes a label for exports.
- `docs/timestamp_contract.md` — the authoritative rendering contract.
- `docs/legacy_notes.md` — older notes kept for history; may be out of date.

Run tests with `python -m unittest discover -s .`.
