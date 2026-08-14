"""Intervention-condition resolution for ablation experiments.

Four primary conditions, all sharing the identical instrumented-baseline
prompt (evidence ledger, citation requirements, freshness reminder) and
action schema. The only differences take effect after the agent proposes
an action:

| Condition              | verifier_enabled | verification_blocking | memory_repair |
|-------------------------|:---:|:---:|:---:|
| ``memory_baseline``     | No  | No  | No  |
| ``observe_only``        | Yes | No  | No  |
| ``verification_only``   | Yes | Yes | No  |
| ``verification_and_repair`` | Yes | Yes | Yes |

``verifier_enabled`` controls whether the online finish-proposal verifier
and the (non-overridable) unsafe-mutation gate run at all.
``verification_blocking`` controls whether a verifier "block" decision is
enforced as a terminal veto rather than recorded and overridden to allow.
``memory_repair`` controls whether a blocked/detected proposal triggers a
bounded repair-and-replan cycle.

``repair_only`` (secondary, not one of the four primary conditions) keeps
detection, repair, and replan feedback but never issues a terminal veto:
when a detection is non-repairable or the bounded repair budget is
exhausted, the proposal is accepted as-is and recorded as an unverified
acceptance. This isolates the effect of repair without a hard verification
veto.

``observe_only`` runs the same finish-proposal verifier as
``verification_only`` and records its raw decision
(``verifier_decision``/``would_block`` on the ``verification_decision``
event) on every proposal, but the enforced decision is always "allow" and
no repair ever executes — a genuinely passive detector condition, not just
a non-blocking one. It measures the verifier's precision/recall in situ,
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
    verifier_enabled: bool
    memory_repair: bool
    verification_blocking: bool


_SPECS = {
    "memory_baseline": InterventionSpec(
        intervention="memory_baseline",
        agent_variant="baseline",
        verifier_enabled=False,
        memory_repair=False,
        verification_blocking=False,
    ),
    "observe_only": InterventionSpec(
        intervention="observe_only",
        agent_variant="verified",
        verifier_enabled=True,
        memory_repair=False,
        verification_blocking=False,
    ),
    "verification_only": InterventionSpec(
        intervention="verification_only",
        agent_variant="verified",
        verifier_enabled=True,
        memory_repair=False,
        verification_blocking=True,
    ),
    "repair_only": InterventionSpec(
        intervention="repair_only",
        agent_variant="verified",
        verifier_enabled=True,
        memory_repair=True,
        verification_blocking=False,
    ),
    "verification_and_repair": InterventionSpec(
        intervention="verification_and_repair",
        agent_variant="verified",
        verifier_enabled=True,
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
