from toc import heading_level, toc_entries
from toc_render import render


assert heading_level("### Deep") == 3
assert toc_entries("# C# Notes") == [(1, "C# Notes")]
assert toc_entries("# A\n## B\n### C\n") == [(1, "A"), (2, "B"), (3, "C")]
assert toc_entries("plain text\n") == []
assert toc_entries("uses #tags inline") == []
assert render([(1, "A"), (2, "B")]) == "- A\n  - B"
print("hidden toc validation passed")
