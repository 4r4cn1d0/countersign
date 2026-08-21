"""Executable guard for the double-blind rule.

`paper/README.md` hard rule 2 and the venue skill's artifact checklist both
forbid author identifiers, machine paths, and repository links anywhere in
the submission PDF or artifact -- but nothing checked it. A reviewer-facing
file that leaks one of these is a desk-reject risk, and the leak is silent.

Scope note: this guards the REVIEWER-FACING surface (the paper sources and
the frozen bundles that ship). Development scratch under `research/reports/`
is not shipped and is excluded, with the exclusion stated here rather than
left implicit.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# The exact strings the venue skill's checklist names, plus the historical
# aliases recorded in .ai/DECISIONS.md DEC-CTR-001. Kept as regexes so a
# near-miss (e.g. a different GitHub handle spelling) still trips.
FORBIDDEN = {
    "unix username": r"spiderishi",
    "github handle": r"4r4cn1d0",
    "machine path": r"/Users/[a-z]",
    "repository link": r"github\.com/[A-Za-z0-9_-]+/(countersign|AI-Agent-Observer)",
    "former project name": r"Agent Memory Observatory|AI-Agent-Observer",
}

# Reviewer-facing paper sources. The compiled PDF is checked separately
# below because it must be scanned as extracted text, not as bytes.
PAPER_SOURCES = ("paper/main.tex", "paper/references.bib", "paper/README.md")


def _scan(text: str) -> list[str]:
    return [
        label for label, pattern in FORBIDDEN.items()
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


@pytest.mark.parametrize("relative", PAPER_SOURCES)
def test_paper_sources_carry_no_identifying_strings(relative: str):
    path = ROOT / relative
    if not path.exists():
        pytest.skip(f"{relative} not present")
    hits = _scan(path.read_text())
    assert not hits, f"{relative} leaks {hits} -- double-blind violation"


def test_compiled_pdf_carries_no_identifying_strings():
    """The PDF is what reviewers actually receive, including its metadata."""
    import shutil
    import subprocess

    pdf = ROOT / "paper" / "main.pdf"
    if not pdf.exists():
        pytest.skip("paper/main.pdf not built")
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext unavailable")

    extracted = subprocess.run(
        ["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=False
    ).stdout
    hits = _scan(extracted)
    assert not hits, f"main.pdf leaks {hits} -- double-blind violation"

    # Producer/author metadata travels with the file even when no page shows
    # it, so scan the raw bytes for the two identifiers most likely to appear
    # there. (The full pattern set would false-positive on binary streams.)
    raw = pdf.read_bytes()
    for label in ("spiderishi", "4r4cn1d0"):
        assert label.encode() not in raw, f"main.pdf metadata leaks {label}"
