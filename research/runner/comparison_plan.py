"""Condition naming and pairwise-comparison planning.

Contains only which comparisons exist and what they're called — no
statistics, no analysis. Shared by experiment_protocol.py (predeclaring
comparisons before any run) and matrix_analysis.py (resolving which rows
belong to which comparison) so the two can never silently resolve
reference/treatment differently. Duplicated reference/treatment resolution
across those two modules previously caused a real bug (the Markdown
report's headline defaulting to whichever treatment condition sorted
first instead of the predeclared primary comparison).
"""

from __future__ import annotations

#: Comparisons that don't use the reference/baseline condition — present
#: whenever both sides are in the variant set, regardless of whether
#: either one also happens to be the reference condition for other
#: comparisons. Each is its own independent paired sample, never pooled
#: with anything else.
EXTRA_PAIRWISE_COMPARISONS: tuple[tuple[str, str], ...] = (
    ("verification_only", "verification_and_repair"),
)


def comparison_key(reference: str, treatment: str) -> str:
    """Canonical name for a reference-vs-treatment comparison."""

    return f"{reference}__vs__{treatment}"


def reference_and_treatment_variants(
    variants: list[str],
) -> tuple[str, list[str]]:
    """Determine the reference/baseline condition and its treatment(s).

    Legacy two-arm manifests (variants=["baseline", "verified"]) produce
    exactly one treatment variant. Intervention-mode manifests
    (memory_baseline plus any subset of observe_only/verification_only/
    repair_only/verification_and_repair) compare every other condition
    against memory_baseline — never against the literal strings
    "baseline"/"verified", which intervention-mode run artifacts don't use
    (their "variant" field is the intervention name).
    """

    variant_list = list(variants or ["baseline", "verified"])
    variant_set = set(variant_list)
    if "memory_baseline" in variant_set:
        reference_variant = "memory_baseline"
    elif "baseline" in variant_set:
        reference_variant = "baseline"
    else:
        reference_variant = variant_list[0]
    treatment_variants = [
        variant for variant in variant_list if variant != reference_variant
    ]
    return reference_variant, treatment_variants or ["verified"]


def extra_pairwise_comparisons(
    variants: list[str],
) -> list[tuple[str, str]]:
    """Non-reference-referenced comparisons present in this variant set.

    Checked against the full variant set, not just the treatment list —
    when verification_only is itself the reference condition (e.g.
    variants=["verification_only", "verification_and_repair"]), the
    comparison must still be planned even though verification_only can't
    simultaneously appear as one of its own treatments.
    """

    variant_set = set(variants)
    return [
        (reference, treatment)
        for reference, treatment in EXTRA_PAIRWISE_COMPARISONS
        if reference in variant_set and treatment in variant_set
    ]


def predeclared_confirmatory_comparisons(variants: list[str]) -> dict:
    """Name the specific pairwise comparisons the analysis should report.

    Predeclaring these — rather than letting the report/markdown formatter
    default to whichever treatment condition happens to sort first — is
    what keeps the Markdown headline naming the intended primary
    comparison (memory_baseline vs verification_only) instead of silently
    substituting the first-sorted treatment (memory_baseline vs
    observe_only).
    """

    variant_set = set(variants)
    reference, treatments = reference_and_treatment_variants(variants)

    def _comparison(
        reference_variant: str | None, treatment: str | None
    ) -> str | None:
        if not reference_variant or not treatment:
            return None
        return comparison_key(reference_variant, treatment)

    return {
        "primary": _comparison(
            reference,
            "verification_only"
            if "verification_only" in treatments
            else (treatments[0] if treatments else None),
        ),
        "detector_sanity_check": _comparison(
            reference, "observe_only" if "observe_only" in treatments else None
        ),
        "full_system": _comparison(
            reference,
            "verification_and_repair"
            if "verification_and_repair" in treatments
            else None,
        ),
        "repair_increment": (
            comparison_key("verification_only", "verification_and_repair")
            if {"verification_only", "verification_and_repair"}.issubset(
                variant_set
            )
            else None
        ),
    }
