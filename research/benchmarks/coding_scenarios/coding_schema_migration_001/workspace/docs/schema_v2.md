# Event schema v2

- `schema_version` must equal `2`.
- `timestamp` is renamed to `occurred_at`.
- Core fields are `id`, `schema_version`, `occurred_at`, and `metadata`.
- Unknown version-one fields must be preserved under `metadata`.
- Consumers must reject versions other than `2`.
