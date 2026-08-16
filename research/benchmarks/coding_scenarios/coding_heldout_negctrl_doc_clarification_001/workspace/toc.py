"""Extract table-of-contents entries from markdown text.

The heading contract lives in docs/toc_contract.md.
"""


def heading_level(line):
    return line.count("#")


def toc_entries(text):
    entries = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        level = heading_level(stripped)
        title = stripped.lstrip("#").strip()
        if title:
            entries.append((level, title))
    return entries
