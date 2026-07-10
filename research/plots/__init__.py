"""Scientific figure generation for the research pipeline.

Requires matplotlib (see research/requirements-analysis.txt); import errors
surface a pointed install hint rather than a bare traceback.
"""

from __future__ import annotations

try:
    from .figures import FIGURE_REGISTRY, generate_figures
except ImportError as exc:  # pragma: no cover - environment guard
    raise ImportError(
        "The plotting layer needs matplotlib. Install analysis extras "
        "with: pip install -r research/requirements-analysis.txt"
    ) from exc

__all__ = ["FIGURE_REGISTRY", "generate_figures"]
