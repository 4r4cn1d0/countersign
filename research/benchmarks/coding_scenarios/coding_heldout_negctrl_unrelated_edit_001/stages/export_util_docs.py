"""Row rendering for CSV export.

Rendering is intentionally minimal: values are joined with commas and
rows with newlines. Quoting and escaping are out of scope for these
extracts (see docs/export_notes.md).
"""


def render_row(values):
    """Join one row's values with commas."""
    return ",".join(str(value) for value in values)


def render_table(rows):
    """Join rendered rows with newlines."""
    return "\n".join(render_row(row) for row in rows)
