# Normalization contract

- Trim event names.
- Convert trailing `Z` timestamps to explicit `+00:00` offsets.
- Lowercase, trim, deduplicate, and remove empty tags while preserving order.
- Normalize source names to lowercase and use `unknown` when absent.
