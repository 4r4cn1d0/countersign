"""Compose dashboard summaries from formatted sizes."""

from fmt_bytes import format_bytes


def storage_summary(sizes):
    return ", ".join(format_bytes(size) for size in sizes)
