# Parser contract

- Strip whitespace around keys and values.
- Ignore blank lines and lines whose first non-space character is `#`.
- Reject non-comment lines without `=`.
- Later entries override earlier entries.
- Explicit values override normalized defaults.
