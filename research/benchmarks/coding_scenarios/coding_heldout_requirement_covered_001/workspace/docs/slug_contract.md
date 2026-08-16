# Slug Contract (authoritative)

`slugify(title)` must:

- Lowercase the title.
- Replace spaces with single hyphens.
- Remove characters other than letters, digits, spaces, and hyphens.

`"Hello World!" -> "hello-world"`. This contract supersedes any older
guidance in `legacy_notes.md`.
