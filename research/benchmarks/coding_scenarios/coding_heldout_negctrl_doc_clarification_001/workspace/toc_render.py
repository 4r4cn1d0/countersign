"""Render TOC entries as an indented bullet list."""


def render(entries):
    lines = []
    for level, title in entries:
        indent = "  " * (level - 1)
        lines.append(f"{indent}- {title}")
    return "\n".join(lines)
