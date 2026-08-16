# Column Statistics Contract

- Blank cells (empty or whitespace-only) are skipped, not treated as
  zero.
- column_mean averages over the non-blank numeric values only; a
  column with no non-blank values has mean 0.0.
- column_max takes the maximum of the non-blank numeric values; a
  column with no non-blank values has max 0.0.
