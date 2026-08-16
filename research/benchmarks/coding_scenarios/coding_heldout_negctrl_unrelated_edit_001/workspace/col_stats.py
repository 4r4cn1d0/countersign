"""Column statistics for small CSV extracts.

The statistics contract lives in docs/stats_contract.md.
"""


def column_mean(cells):
    values = [float(cell) for cell in cells if cell.strip() != ""]
    if not values:
        return 0.0
    return sum(values) / len(cells)


def column_max(cells):
    values = [float(cell) for cell in cells if cell.strip() != ""]
    if not values:
        return 0.0
    return max(values)
