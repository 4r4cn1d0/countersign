# Storage Size Formatting

Helpers for rendering byte counts on the storage dashboard.

## Quick start

    from fmt_bytes import format_bytes

    format_bytes(512)   # "512.0 B"
    format_bytes(1024)  # "1.0 KB"

The rendering contract is docs/fmt_contract.md. Historical display
conventions are collected in docs/legacy_notes.md.
