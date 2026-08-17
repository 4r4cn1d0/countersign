# Timestamp Rendering Contract (authoritative)

`render_utc(epoch_seconds)` must render UTC timestamps as ISO-8601 with a
`Z` suffix and no offset notation:

- `0 -> "1970-01-01T00:00:00Z"`
- `1700000000 -> "2023-11-14T22:13:20Z"`

The `Z` suffix form is required by the export pipeline. This contract
supersedes any older guidance in `legacy_notes.md`.
