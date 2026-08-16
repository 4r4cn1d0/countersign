"""Row rendering for CSV export."""


def render_row(values):
    return ",".join(str(value) for value in values)


def render_table(rows):
    return "\n".join(render_row(row) for row in rows)
