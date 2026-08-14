"""Intervention-condition resolution for ablation experiments.

Each intervention condition decouples the two safety mechanisms that the
``verified`` agent variant historically bundled together:

- verification blocking: the finish gate may veto unsafe completion proposals.
- memory repair: the memory controller may execute bounded repair actions and
  request a replan after a detection.

``repair_only`` keeps detection, repair, and replan feedback but never issues
a terminal veto: when a detection is non-repairable or the bounded repair
budget is exhausted, the proposal is accepted as-is and recorded as an
unverified acceptance. This isolates the effect of repair without a hard
verification veto.

``observe_only`` runs the same finish-proposal verifier as ``verification_only``
and records its decision on every proposal, but never blocks and never
triggers repair. It measures the verifier's precision/recall in situ,
without any behavioral feedback loop back to the agent.
"""

from __future__ import annotations

from dataclasses import dataclass


INTERVENTION_CONDITIONS = (
    "memory_baseline",
    "observe_only",
    "verification_only",
    "repair_only",
    "verification_and_repair",
)


@dataclass(frozen=True)
class InterventionSpec:
    intervention: str
    agent_variant: str
    memory_repair: bool
    verification_blocking: bool


_SPECS = {
    "memory_baseline": InterventionSpec(
        intervention="memory_baseline",
        agent_variant="baseline",
        memory_repair=False,
        verification_blocking=False,
    ),
    "observe_only": InterventionSpec(
        intervention="observe_only",
        agent_variant="verified",
        memory_repair=False,
        verification_blocking=False,
    ),
    "verification_only": InterventionSpec(
        intervention="verification_only",
        agent_variant="verified",
        memory_repair=False,
        verification_blocking=True,
    ),
    "repair_only": InterventionSpec(
        intervention="repair_only",
        agent_variant="verified",
        memory_repair=True,
        verification_blocking=False,
    ),
    "verification_and_repair": InterventionSpec(
        intervention="verification_and_repair",
        agent_variant="verified",
        memory_repair=True,
        verification_blocking=True,
    ),
}


def resolve_intervention(name: str) -> InterventionSpec:
    """Return the spec for a named intervention condition."""

    try:
        return _SPECS[name]
    except KeyError:
        raise ValueError(
            f"Unknown intervention condition: {name!r}; expected one of "
            f"{sorted(_SPECS)}"
        ) from None
