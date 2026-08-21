"""Pin the places where a config file disagrees with the frozen campaign.

These divergences are real and must NOT be fixed by editing the config
files: `research/agents/model_matrix.json` and
`research/benchmarks/seed_tasks.json` are hashed into every frozen
experiment protocol, so editing either would break the freeze and
invalidate the campaign's integrity chain.

The right treatment is therefore to pin each divergence with a test, so
it is documented, intentional, and cannot drift further unnoticed. A
reader who reruns the matrix without the CLI flags the campaign used
would otherwise get a silently different configuration.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "research" / "agents" / "model_matrix.json"
SEEDS = ROOT / "research" / "benchmarks" / "seed_tasks.json"
CAMPAIGNS = ROOT / "runs" / "pod-sync"


def _protocols():
    if not CAMPAIGNS.exists():
        return []
    return sorted(CAMPAIGNS.glob("*/experiment_protocol.json"))


def test_max_tokens_divergence_is_documented_not_silent():
    """model_matrix.json says 256; every frozen protocol recorded 1024.

    The campaign passed --max-tokens 1024 on the CLI. The default in the
    matrix file was never updated because it is hash-pinned. Anyone
    reproducing the campaign must pass the flag explicitly.
    """
    matrix_default = json.loads(MATRIX.read_text()).get("max_tokens")
    assert matrix_default == 256, (
        "model_matrix.json max_tokens changed; if this was deliberate, the "
        "frozen protocol hashes no longer match and the freeze is broken"
    )

    protocols = _protocols()
    if not protocols:
        pytest.skip("campaign protocols not present in this checkout")
    for protocol_path in protocols:
        recorded = json.loads(protocol_path.read_text())["generation"]["max_tokens"]
        assert recorded == 1024, (
            f"{protocol_path.parent.name} recorded max_tokens={recorded}; the "
            "campaign ran at 1024"
        )


def test_hardware_profile_in_matrix_is_stale_relative_to_the_campaign():
    """The matrix file's hardware profile is a local Mac; runs were CUDA pods.

    Same reason as above: the field is hash-pinned and therefore stale by
    design. The authoritative record of where a run executed is the run
    artifact's own environment block, not this default.
    """
    profile = json.loads(MATRIX.read_text()).get("hardware_profile", {}).get("name")
    assert profile == "macbook_m4_air_24gb", (
        "hardware_profile changed; this field is hashed into the frozen "
        "protocols and must not be edited"
    )


def test_split_labelling_is_asymmetric_across_the_two_task_files():
    """`tier` lives in seed_tasks.json; `evaluation_split` lives in both,
    but only on held-out entries in seed_tasks.json.

    This asymmetry is what CURRENT_STATE discrepancy 6 describes. Pinning
    it means a future edit that "tidies" one file without the other
    trips a test instead of silently desynchronising the split labels.
    """
    payload = json.loads(SEEDS.read_text())
    tasks = payload["tasks"] if isinstance(payload, dict) and "tasks" in payload else payload

    assert all("tier" in task for task in tasks), "tier is required on every seed task"

    heldout = [t for t in tasks if t.get("tier") == "heldout"]
    assert heldout, "expected held-out seed tasks"
    assert all(t.get("evaluation_split") == "heldout_v1" for t in heldout)

    non_heldout = [t for t in tasks if t.get("tier") != "heldout"]
    assert all("evaluation_split" not in t for t in non_heldout), (
        "development seed tasks carry no evaluation_split; the label lives in "
        "coding_scenarios/*/scenario.json instead"
    )

    scenarios = ROOT / "research" / "benchmarks" / "coding_scenarios"
    if not scenarios.exists():
        pytest.skip("scenario fixtures not present")
    manifests = sorted(scenarios.glob("*/scenario.json"))
    splits = [json.loads(m.read_text()).get("evaluation_split") for m in manifests]
    assert splits.count("development") == 11
    assert splits.count("heldout_v1") == 10
    assert all("tier" not in json.loads(m.read_text()) for m in manifests), (
        "scenario manifests carry evaluation_split, not tier"
    )
