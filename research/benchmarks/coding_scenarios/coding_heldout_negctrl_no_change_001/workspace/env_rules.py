"""Reserved environment names."""

RESERVED_NAMES = frozenset({"default", "system", "internal"})


def is_reserved(name):
    return name in RESERVED_NAMES
