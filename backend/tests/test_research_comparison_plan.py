"""Tests for the shared condition-naming/pairwise-comparison-planning module.

comparison_plan.py exists specifically to prevent experiment_protocol.py
(predeclaring comparisons before any run) and matrix_analysis.py
(resolving which rows belong to which comparison) from silently resolving
reference/treatment differently — duplicated logic across those two
modules previously caused exactly that kind of bug. These tests pin the
exact subset/permutation cases called out during review.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner.comparison_plan import (
    comparison_key,
    extra_pairwise_comparisons,
    predeclared_confirmatory_comparisons,
    reference_and_treatment_variants,
)


def test_all_five_interventions():
    variants = [
        "memory_baseline",
        "observe_only",
        "verification_only",
        "repair_only",
        "verification_and_repair",
    ]
    reference, treatments = reference_and_treatment_variants(variants)
    assert reference == "memory_baseline"
    assert set(treatments) == {
        "observe_only",
        "verification_only",
        "repair_only",
        "verification_and_repair",
    }
    comparisons = predeclared_confirmatory_comparisons(variants)
    assert comparisons == {
        "primary": "memory_baseline__vs__verification_only",
        "detector_sanity_check": "memory_baseline__vs__observe_only",
        "full_system": "memory_baseline__vs__verification_and_repair",
        "repair_increment": "verification_only__vs__verification_and_repair",
    }
    assert extra_pairwise_comparisons(variants) == [
        ("verification_only", "verification_and_repair")
    ]


def test_four_primary_interventions():
    variants = [
        "memory_baseline",
        "observe_only",
        "verification_only",
        "verification_and_repair",
    ]
    comparisons = predeclared_confirmatory_comparisons(variants)
    assert comparisons["primary"] == "memory_baseline__vs__verification_only"
    assert (
        comparisons["detector_sanity_check"]
        == "memory_baseline__vs__observe_only"
    )
    assert (
        comparisons["full_system"]
        == "memory_baseline__vs__verification_and_repair"
    )
    assert (
        comparisons["repair_increment"]
        == "verification_only__vs__verification_and_repair"
    )


def test_verification_only_and_verification_and_repair_only():
    """The subset edge case: verification_only is the reference here.

    The repair-increment comparison must still be planned even though
    verification_only can't simultaneously be a "treatment" of itself.
    """
    variants = ["verification_only", "verification_and_repair"]
    reference, treatments = reference_and_treatment_variants(variants)
    assert reference == "verification_only"
    assert treatments == ["verification_and_repair"]
    comparisons = predeclared_confirmatory_comparisons(variants)
    # "primary" and "full_system" both resolve to the same (only) treatment
    # here — there's nothing else to distinguish them in a two-condition
    # experiment where the reference itself is verification_only.
    assert comparisons["primary"] == (
        "verification_only__vs__verification_and_repair"
    )
    assert comparisons["detector_sanity_check"] is None
    assert comparisons["full_system"] == (
        "verification_only__vs__verification_and_repair"
    )
    assert comparisons["repair_increment"] == (
        "verification_only__vs__verification_and_repair"
    )
    assert extra_pairwise_comparisons(variants) == [
        ("verification_only", "verification_and_repair")
    ]


def test_legacy_baseline_and_verified():
    variants = ["baseline", "verified"]
    reference, treatments = reference_and_treatment_variants(variants)
    assert reference == "baseline"
    assert treatments == ["verified"]
    comparisons = predeclared_confirmatory_comparisons(variants)
    assert comparisons["primary"] == "baseline__vs__verified"
    assert comparisons["detector_sanity_check"] is None
    assert comparisons["full_system"] is None
    assert comparisons["repair_increment"] is None
    assert extra_pairwise_comparisons(variants) == []


def test_memory_baseline_only():
    """A single-condition manifest has no treatment at all.

    reference_and_treatment_variants falls back to a synthetic "verified"
    placeholder treatment (matching the historical legacy-mode default) so
    callers always get a non-empty treatment list; predeclared comparisons
    correctly resolve to None since there's nothing real to compare
    against.
    """
    variants = ["memory_baseline"]
    reference, treatments = reference_and_treatment_variants(variants)
    assert reference == "memory_baseline"
    assert treatments == ["verified"]
    comparisons = predeclared_confirmatory_comparisons(variants)
    assert comparisons["primary"] == "memory_baseline__vs__verified"
    assert comparisons["detector_sanity_check"] is None
    assert comparisons["full_system"] is None
    assert comparisons["repair_increment"] is None
    assert extra_pairwise_comparisons(variants) == []


def test_comparison_key_matches_separator_used_for_parsing():
    # format_model_matrix_analysis_markdown parses the treatment name back
    # out via primary_comparison.split("__vs__")[-1] — this pins the
    # separator so that parsing never silently breaks.
    key = comparison_key("memory_baseline", "verification_only")
    assert key == "memory_baseline__vs__verification_only"
    assert key.split("__vs__") == ["memory_baseline", "verification_only"]
