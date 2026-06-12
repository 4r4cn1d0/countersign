"""Tests for the bounded coding-agent environment."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.runner.coding_environment import (
    apply_bounded_patch,
    git_diff,
    git_status,
    infer_test_coverage,
    initialize_git_repository,
    inspect_dependency,
    read_structured_file,
    repository_snapshot_sha256,
    run_unittest,
    search_code,
)


def _write_workspace(workspace: Path) -> None:
    (workspace / "service.py").write_text(
        "def answer():\n    return 41\n",
        encoding="utf-8",
    )
    (workspace / "test_service.py").write_text(
        "import unittest\n"
        "from service import answer\n\n"
        "class ServiceTests(unittest.TestCase):\n"
        "    def test_answer(self):\n"
        "        self.assertEqual(answer(), 42)\n",
        encoding="utf-8",
    )
    (workspace / "consumer.py").write_text(
        "from service import answer\n\nRESULT = answer()\n",
        encoding="utf-8",
    )
    (workspace / "settings.json").write_text(
        json.dumps({"retries": 3, "enabled": True}),
        encoding="utf-8",
    )


def test_git_baseline_search_status_diff_and_repository_hash(tmp_path: Path):
    _write_workspace(tmp_path)

    base_commit = initialize_git_repository(tmp_path)
    initial_hash = repository_snapshot_sha256(tmp_path)

    assert len(base_commit) == 40
    baseline_status = git_status(tmp_path)
    assert baseline_status["branch"] in {"main", "master"}
    assert baseline_status["head_commit"] == base_commit
    assert baseline_status["clean"] is True
    assert baseline_status["entries"] == []
    search = search_code(tmp_path, query="return 41", path="service.py")
    assert search["match_count"] == 1
    assert search["matches"][0]["path"] == "service.py"

    (tmp_path / "service.py").write_text(
        "def answer():\n    return 42\n",
        encoding="utf-8",
    )
    (tmp_path / "notes.txt").write_text("new evidence\n", encoding="utf-8")

    status = git_status(tmp_path)
    diff = git_diff(tmp_path)
    assert status["clean"] is False
    assert {entry["path"] for entry in status["entries"]} == {
        "notes.txt",
        "service.py",
    }
    assert diff["changed_files"] == ["notes.txt", "service.py"]
    assert "return 42" in diff["diff"]
    assert "new evidence" in diff["diff"]
    assert repository_snapshot_sha256(tmp_path) != initial_hash


def test_structured_read_dependency_inspection_and_bounded_patch(tmp_path: Path):
    _write_workspace(tmp_path)
    initialize_git_repository(tmp_path)

    structured = read_structured_file(tmp_path, "settings.json")
    dependency = inspect_dependency(
        tmp_path,
        path="service.py",
        symbol="answer",
    )
    patch = (
        "--- a/service.py\n"
        "+++ b/service.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def answer():\n"
        "-    return 41\n"
        "+    return 42\n"
    )
    applied = apply_bounded_patch(tmp_path, patch)

    assert structured["parser"] == "json"
    assert structured["value"] == {"retries": 3, "enabled": True}
    assert any(
        definition["name"] == "answer"
        for definition in dependency["definitions"]
    )
    assert {item["path"] for item in dependency["dependents"]} == {
        "consumer.py",
        "test_service.py",
    }
    assert applied["changed_files"] == ["service.py"]
    assert "return 42" in (tmp_path / "service.py").read_text(
        encoding="utf-8"
    )

    with pytest.raises(ValueError, match="cannot create or delete"):
        apply_bounded_patch(
            tmp_path,
            "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+value = 1\n",
        )


def test_targeted_and_full_test_execution_use_real_unittest_results(
    tmp_path: Path,
):
    _write_workspace(tmp_path)
    initialize_git_repository(tmp_path)

    failing = run_unittest(tmp_path, targets=["test_service.py"])
    targeted_coverage = infer_test_coverage(
        tmp_path,
        failing["targets"],
    )
    assert failing["targets"] == ["test_service.py"]
    assert failing["test_count"] == 1
    assert failing["returncode"] != 0
    assert "FAILED" in failing["output"]
    assert targeted_coverage == {
        "mode": "targeted",
        "test_targets": ["test_service.py"],
        "covered_files": ["service.py", "test_service.py"],
        "covered_symbols": ["service.py:answer"],
    }

    apply_bounded_patch(
        tmp_path,
        (
            "--- a/service.py\n"
            "+++ b/service.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def answer():\n"
            "-    return 41\n"
            "+    return 42\n"
        ),
    )
    targeted = run_unittest(tmp_path, targets=["test_service.py"])
    full = run_unittest(tmp_path)

    assert targeted["returncode"] == 0
    assert targeted["test_count"] == 1
    assert full["returncode"] == 0
    assert full["test_count"] == 1
