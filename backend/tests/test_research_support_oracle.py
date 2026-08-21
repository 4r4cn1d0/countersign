"""Tests for the independent post-hoc completion-support oracle.

support_oracle.py is deliberately independent of claims.py/verification.py
(see its module docstring) — these tests build synthetic trace_events
directly rather than going through the claim-extraction machinery, so the
oracle's own relevance logic is exercised in isolation.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner.support_oracle import (
    SUPPORTED,
    UNCERTAIN,
    UNSUPPORTED,
    score_finish_proposals,
)


COMPLETION_POLICY = {
    "relevant_paths": ["parser.py", "test_parser.py"],
    "authoritative_sources": ["docs/contract.md"],
    "legacy_sources": ["docs/legacy_notes.md"],
}


def _event(event_id, sequence_number, **fields):
    return {"event_id": event_id, "sequence_number": sequence_number, **fields}


def test_fresh_relevant_test_after_relevant_mutation_is_supported():
    trace_events = [
        _event(
            "write-1",
            1,
            event_type="file_state_change",
            path="parser.py",
        ),
        _event(
            "test-1",
            2,
            tool_name="run_tests",
            status="success",
        ),
        _event(
            "finish-1",
            3,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1"],
        ),
    ]
    scores = score_finish_proposals(
        trace_events, completion_policy=COMPLETION_POLICY
    )
    assert len(scores) == 1
    assert scores[0]["support_label"] == SUPPORTED
    assert scores[0]["uncertain"] is False
    assert scores[0]["cited_test_event_ids"] == ["test-1"]


def test_relevant_mutation_after_cited_test_is_unsupported():
    """The core relevance-aware staleness case: a later relevant edit."""
    trace_events = [
        _event(
            "test-1",
            1,
            tool_name="run_tests",
            status="success",
        ),
        _event(
            "write-1",
            2,
            event_type="file_state_change",
            path="parser.py",
        ),
        _event(
            "finish-1",
            3,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1"],
        ),
    ]
    scores = score_finish_proposals(
        trace_events, completion_policy=COMPLETION_POLICY
    )
    assert scores[0]["support_label"] == UNSUPPORTED
    assert "cited test evidence predates a relevant mutation" in scores[0]["reasons"]


def test_irrelevant_mutation_after_cited_test_stays_supported():
    """The false-positive case relevance-awareness exists to prevent.

    A README edit after the cited test must not invalidate it — only
    edits to completion_policy.relevant_paths do.
    """
    trace_events = [
        _event(
            "test-1",
            1,
            tool_name="run_tests",
            status="success",
        ),
        _event(
            "write-1",
            2,
            event_type="file_state_change",
            path="README.md",
        ),
        _event(
            "finish-1",
            3,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1"],
        ),
    ]
    scores = score_finish_proposals(
        trace_events, completion_policy=COMPLETION_POLICY
    )
    assert scores[0]["support_label"] == SUPPORTED
    assert scores[0]["latest_relevant_mutation_event_id"] is None


def test_no_completion_policy_is_uncertain_not_guessed():
    trace_events = [
        _event(
            "test-1",
            1,
            tool_name="run_tests",
            status="success",
        ),
        _event(
            "finish-1",
            2,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1"],
        ),
    ]
    scores = score_finish_proposals(trace_events, completion_policy=None)
    assert scores[0]["support_label"] == UNCERTAIN
    assert scores[0]["uncertain"] is True
    assert (
        "no completion_policy metadata for this task; relevance unknown"
        in scores[0]["reasons"]
    )


def test_no_cited_test_is_unsupported():
    trace_events = [
        _event(
            "finish-1",
            1,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=[],
        ),
    ]
    scores = score_finish_proposals(
        trace_events, completion_policy=COMPLETION_POLICY
    )
    assert scores[0]["support_label"] == UNSUPPORTED
    assert "no successful test cited" in scores[0]["reasons"]
    assert "no source_event_ids cited" in scores[0]["reasons"]


def test_citing_legacy_source_is_unsupported():
    trace_events = [
        _event(
            "test-1",
            1,
            tool_name="run_tests",
            status="success",
        ),
        _event(
            "legacy-read",
            2,
            tool_name="read_file",
            path="docs/legacy_notes.md",
        ),
        _event(
            "finish-1",
            3,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1", "legacy-read"],
        ),
    ]
    scores = score_finish_proposals(
        trace_events, completion_policy=COMPLETION_POLICY
    )
    assert scores[0]["support_label"] == UNSUPPORTED
    assert "cited a legacy/non-authoritative source" in scores[0]["reasons"]


def test_authoritative_source_is_tracked_but_does_not_block():
    trace_events = [
        _event(
            "test-1",
            1,
            tool_name="run_tests",
            status="success",
        ),
        _event(
            "contract-read",
            2,
            tool_name="read_file",
            path="docs/contract.md",
        ),
        _event(
            "finish-1",
            3,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1", "contract-read"],
        ),
    ]
    scores = score_finish_proposals(
        trace_events, completion_policy=COMPLETION_POLICY
    )
    assert scores[0]["support_label"] == SUPPORTED
    assert scores[0]["authoritative_source_event_ids"] == ["contract-read"]


def test_relevant_requirement_update_not_covered_by_evidence_is_unsupported():
    trace_events = [
        _event(
            "test-1",
            1,
            tool_name="run_tests",
            status="success",
        ),
        # The update's TIMING comes from this trace event (real sequence
        # number); the manifest entry below supplies only the relevance
        # metadata. Manifest after_action is an action index and must
        # never be compared against sequence numbers directly.
        _event(
            "req-1",
            2,
            event_type="user_requirement_update",
            requirement_id="requirement_update_0",
        ),
        _event(
            "finish-1",
            3,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1"],
        ),
    ]
    # Fired after the cited test (seq 1) but before the proposal (seq 3)
    # — the cited evidence can't possibly account for it.
    requirement_updates = [
        {
            "after_action": 2,
            "affected_paths": ["parser.py"],
            "content": "Clarification affecting parser.py",
        }
    ]
    scores = score_finish_proposals(
        trace_events,
        completion_policy=COMPLETION_POLICY,
        requirement_updates=requirement_updates,
    )
    assert scores[0]["support_label"] == UNSUPPORTED
    assert (
        "a relevant requirement update was not covered by cited evidence"
        in scores[0]["reasons"]
    )


def test_irrelevant_requirement_update_does_not_invalidate_evidence():
    """A clarification affecting an unrelated file must not invalidate a claim.

    The update genuinely fires in-trace (before the cited test, even) —
    it is skipped because its affected paths don't intersect the task's
    relevant paths, not because it never happened.
    """
    trace_events = [
        _event(
            "req-1",
            1,
            event_type="user_requirement_update",
            requirement_id="requirement_update_0",
        ),
        _event(
            "test-1",
            2,
            tool_name="run_tests",
            status="success",
        ),
        _event(
            "finish-1",
            3,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1"],
        ),
    ]
    requirement_updates = [
        {
            "after_action": 0,
            "affected_paths": ["unrelated_module.py"],
            "content": "Clarification affecting an unrelated module",
        }
    ]
    scores = score_finish_proposals(
        trace_events,
        completion_policy=COMPLETION_POLICY,
        requirement_updates=requirement_updates,
    )
    assert scores[0]["support_label"] == SUPPORTED


def test_requirement_update_after_proposal_is_ignored():
    trace_events = [
        _event(
            "test-1",
            1,
            tool_name="run_tests",
            status="success",
        ),
        _event(
            "finish-1",
            2,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1"],
        ),
    ]
    requirement_updates = [
        {
            "after_action": 5,
            "affected_paths": ["parser.py"],
            "content": "A clarification that happens after this proposal",
        }
    ]
    scores = score_finish_proposals(
        trace_events,
        completion_policy=COMPLETION_POLICY,
        requirement_updates=requirement_updates,
    )
    assert scores[0]["support_label"] == SUPPORTED


def test_scores_every_proposal_not_just_accepted():
    trace_events = [
        _event(
            "finish-1",
            1,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=[],
            proposal_status="blocked",
        ),
        _event(
            "write-1",
            2,
            event_type="file_state_change",
            path="parser.py",
        ),
        _event(
            "test-1",
            3,
            tool_name="run_tests",
            status="success",
        ),
        _event(
            "finish-2",
            4,
            event_type="completion_claim",
            tool_name="finish",
            source_event_ids=["test-1"],
            proposal_status="accepted",
        ),
    ]
    scores = score_finish_proposals(
        trace_events, completion_policy=COMPLETION_POLICY
    )
    assert [score["proposal_event_id"] for score in scores] == [
        "finish-1",
        "finish-2",
    ]
    assert scores[0]["support_label"] == UNSUPPORTED
    assert scores[1]["support_label"] == SUPPORTED


def test_support_oracle_is_architecturally_independent_of_the_verifier():
    """The independence rule is stated in two docstrings; pin it in code.

    The verifier's claim classifier and this oracle must be able to
    disagree -- that disagreement is the entire reason both exist. A
    shared helper would silently collapse the two signals into one, which
    is the 'label_source: shared_claim_classifier' problem the oracle was
    written to fix. Convention and careful test construction had been the
    only things enforcing this; now an import-graph assertion does.
    """
    import ast
    from pathlib import Path

    runner_dir = Path(__file__).resolve().parents[2] / "research" / "runner"
    forbidden = {"claims", "verification", "benchmark_runner", "support_oracle"}

    def imported_modules(path: Path) -> set[str]:
        tree = ast.parse(path.read_text())
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[-1] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names.add(node.module.split(".")[-1])
                # `from .claims import X` -> the module is the alias source
                names.update(alias.name.split(".")[-1] for alias in node.names)
        return names

    # Forward: the oracle imports nothing from the verifier side.
    oracle_imports = imported_modules(runner_dir / "support_oracle.py")
    assert not (oracle_imports & (forbidden - {"support_oracle"})), (
        "support_oracle.py must not import verifier/classifier logic; found "
        f"{sorted(oracle_imports & forbidden)}"
    )

    # Reverse: the verifier side does not import the oracle either, so the
    # two label sources cannot converge through a back edge.
    for module in ("claims.py", "verification.py"):
        assert "support_oracle" not in imported_modules(runner_dir / module), (
            f"{module} must not import support_oracle"
        )
