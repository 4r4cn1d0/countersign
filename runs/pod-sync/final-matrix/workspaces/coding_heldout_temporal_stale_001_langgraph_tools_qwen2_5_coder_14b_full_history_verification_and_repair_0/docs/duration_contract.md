# Duration Formatting Contract (authoritative)

`format_duration(total_seconds)` must render:

- Durations under one hour as `"Xm Ys"` (no padding): `90 -> "1m 30s"`.
- Durations of one hour or more as `"Hh MMm SSs"` with two-digit
  zero-padded minutes and seconds: `3661 -> "1h 01m 01s"`,
  `7200 -> "2h 00m 00s"`.

This contract supersedes any older guidance in `legacy_notes.md`.
