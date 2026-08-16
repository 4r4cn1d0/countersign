"""Render byte counts for the storage dashboard.

The rendering contract lives in docs/fmt_contract.md.
"""

from fmt_units import STEP, UNITS


def format_bytes(size):
    value = float(size)
    index = 0
    while value >= STEP and index < len(UNITS) - 1:
        value /= STEP
        index += 1
    return f"{value:.1f} {UNITS[index]}"
