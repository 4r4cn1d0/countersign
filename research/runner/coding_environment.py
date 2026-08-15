"""Bounded, structured tools for isolated coding-agent workspaces."""

from __future__ import annotations

import ast
import json
import plistlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python 3.9 compatibility
    import tomli as tomllib


CODING_TOOL_ACTIONS = (
    "list_files",
    "read_file",
    "search_code",
    "git_diff",
    "git_status",
    "write_file",
    "apply_patch",
    "read_test_failure",
    "run_targeted_tests",
    "run_full_tests",
    "run_tests",
    "inspect_dependency",
    "read_structured_file",
    "finish",
)

MAX_TOOL_OUTPUT_CHARS = 20_000
MAX_PATCH_CHARS = 24_000
MAX_PATCH_FILES = 3


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_relative_path(relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe workspace path: {relative_path}")
    return path


def initialize_git_repository(workspace: Path) -> str:
    """Create a committed baseline and return its exact commit SHA."""

    _run(["git", "init", "-q"], workspace)
    _run(["git", "config", "user.name", "Agent Memory Harness"], workspace)
    _run(
        ["git", "config", "user.email", "agent-memory@example.invalid"],
        workspace,
    )
    _run(["git", "add", "--all"], workspace)
    _run(
        [
            "git",
            "commit",
            "-q",
            "-m",
            "Initialize benchmark workspace",
            "--no-gpg-sign",
        ],
        workspace,
    )
    return _run(["git", "rev-parse", "HEAD"], workspace).stdout.strip()


def repository_snapshot_sha256(workspace: Path) -> str:
    digest = sha256()
    for path in sorted(workspace.rglob("*")):
        if (
            not path.is_file()
            or ".git" in path.parts
            or "__pycache__" in path.parts
            or path.suffix == ".pyc"
        ):
            continue
        relative = path.relative_to(workspace).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_status(workspace: Path) -> dict:
    result = _run(
        ["git", "status", "--short", "--untracked-files=all"],
        workspace,
    )
    entries = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        entries.append({"status": line[:2], "path": line[3:]})
    return {
        "branch": _run(
            ["git", "branch", "--show-current"],
            workspace,
        ).stdout.strip(),
        "head_commit": _run(
            ["git", "rev-parse", "HEAD"],
            workspace,
        ).stdout.strip(),
        "clean": not entries,
        "entries": entries,
    }


def git_diff(workspace: Path) -> dict:
    result = _run(
        ["git", "diff", "HEAD", "--no-ext-diff", "--no-color", "--"],
        workspace,
    )
    names = _run(
        ["git", "diff", "HEAD", "--name-only", "--"],
        workspace,
    ).stdout.splitlines()
    untracked = _run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        workspace,
    ).stdout.splitlines()
    diff_parts = [result.stdout]
    for relative_path in sorted(filter(None, untracked)):
        candidate = subprocess.run(
            [
                "git",
                "diff",
                "--no-index",
                "--no-ext-diff",
                "--no-color",
                "--",
                "/dev/null",
                relative_path,
            ],
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if candidate.returncode not in {0, 1}:
            raise RuntimeError(
                candidate.stderr.strip() or "Unable to diff untracked file"
            )
        diff_parts.append(candidate.stdout)
    full_diff = "".join(diff_parts)
    return {
        "changed_files": sorted(
            set(filter(None, names)) | set(filter(None, untracked))
        ),
        "diff": _bounded(full_diff),
        "truncated": len(full_diff) > MAX_TOOL_OUTPUT_CHARS,
    }


def search_code(
    workspace: Path,
    *,
    query: str,
    path: str | None = None,
) -> dict:
    if not query or len(query) > 500:
        raise ValueError("search_code query must contain 1-500 characters")
    command = [
        "rg",
        "--json",
        "--line-number",
        "--fixed-strings",
        "--glob",
        "!.git/**",
        query,
    ]
    if path:
        command.append(safe_relative_path(path).as_posix())
    result = subprocess.run(
        command,
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.strip() or "search_code failed")
    matches = []
    for line in result.stdout.splitlines():
        record = json.loads(line)
        if record.get("type") != "match":
            continue
        data = record["data"]
        for submatch in data.get("submatches", []):
            matches.append(
                {
                    "path": data["path"]["text"],
                    "line_number": data["line_number"],
                    "line": data["lines"]["text"].rstrip("\n"),
                    "start": submatch["start"],
                    "end": submatch["end"],
                }
            )
            if len(matches) >= 200:
                break
        if len(matches) >= 200:
            break
    return {
        "query": query,
        "scope": path or ".",
        "match_count": len(matches),
        "matches": matches,
        "truncated": len(matches) >= 200,
    }


def read_structured_file(workspace: Path, relative_path: str) -> dict:
    path = workspace / safe_relative_path(relative_path)
    suffix = path.suffix.lower()
    raw = path.read_bytes()
    if suffix == ".json":
        value = json.loads(raw.decode("utf-8"))
        parser = "json"
    elif suffix == ".toml":
        value = tomllib.loads(raw.decode("utf-8"))
        parser = "tomllib"
    elif suffix in {".plist"}:
        value = plistlib.loads(raw)
        parser = "plistlib"
    elif suffix in {".xml"}:
        value = _xml_to_dict(ET.fromstring(raw))
        parser = "xml.etree.ElementTree"
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError(
                "YAML parsing requires the installed PyYAML dependency"
            ) from exc
        value = yaml.safe_load(raw.decode("utf-8"))
        parser = "yaml.safe_load"
    else:
        raise ValueError(
            "read_structured_file supports JSON, TOML, YAML, XML, and plist"
        )
    return {
        "path": relative_path,
        "parser": parser,
        "value": value,
    }


def inspect_dependency(
    workspace: Path,
    *,
    path: str,
    symbol: str | None = None,
) -> dict:
    relative = safe_relative_path(path)
    target = workspace / relative
    source = target.read_text(encoding="utf-8")
    if target.suffix != ".py":
        raise ValueError("inspect_dependency currently supports Python files")
    tree = ast.parse(source, filename=relative.as_posix())
    imports = []
    definitions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions.append(
                {
                    "name": node.name,
                    "kind": type(node).__name__,
                    "line": node.lineno,
                }
            )
    search_symbol = symbol or target.stem
    dependents = []
    for candidate in sorted(workspace.rglob("*.py")):
        if candidate == target or ".git" in candidate.parts:
            continue
        candidate_source = candidate.read_text(encoding="utf-8")
        try:
            candidate_tree = ast.parse(
                candidate_source,
                filename=str(candidate),
            )
        except SyntaxError:
            continue
        references = [
            node.lineno
            for node in ast.walk(candidate_tree)
            if (
                isinstance(node, ast.Name)
                and node.id == search_symbol
            )
            or (
                isinstance(node, ast.Attribute)
                and node.attr == search_symbol
            )
            or (
                isinstance(node, ast.Import)
                and any(
                    alias.name == target.stem
                    or alias.name.endswith(f".{target.stem}")
                    for alias in node.names
                )
            )
            or (
                isinstance(node, ast.ImportFrom)
                and (
                    node.module == target.stem
                    or (node.module or "").endswith(f".{target.stem}")
                    or any(alias.name == search_symbol for alias in node.names)
                )
            )
        ]
        if references:
            dependents.append(
                {
                    "path": candidate.relative_to(workspace).as_posix(),
                    "lines": sorted(set(references)),
                }
            )
    return {
        "path": relative.as_posix(),
        "symbol": symbol,
        "imports": sorted(set(filter(None, imports))),
        "definitions": definitions,
        "dependents": dependents,
    }


def changed_python_symbols(before: str, after: str) -> list[str]:
    """Return top-level Python symbols whose source representation changed."""

    before_symbols = _python_symbol_fingerprints(before)
    after_symbols = _python_symbol_fingerprints(after)
    return sorted(
        name
        for name in set(before_symbols) | set(after_symbols)
        if before_symbols.get(name) != after_symbols.get(name)
    )


def infer_test_coverage(
    workspace: Path,
    targets: list[str] | None,
) -> dict:
    """Infer local file and symbol dependencies for unittest targets."""

    if not targets:
        # A full unittest run's outcome depends on the Python sources —
        # tests plus whatever they import — not on documentation or other
        # non-executable files. Listing every workspace file here made a
        # README edit "invalidate" a full test run downstream (ledger
        # dependency graphs and claim freshness both intersect against
        # this set), which is exactly the false-positive the
        # relevance-aware staleness work exists to prevent.
        return {
            "mode": "full",
            "test_targets": ["*"],
            "covered_files": sorted(
                path.relative_to(workspace).as_posix()
                for path in workspace.rglob("*.py")
                if path.is_file()
                and ".git" not in path.parts
                and "__pycache__" not in path.parts
            ),
            "covered_symbols": [],
        }

    test_files = []
    for target in targets:
        candidate = workspace / target
        if candidate.is_file() and candidate.suffix == ".py":
            test_files.append(candidate)
            continue
        module_candidate = workspace / (target.replace(".", "/") + ".py")
        if module_candidate.is_file():
            test_files.append(module_candidate)

    covered_files = {
        path.relative_to(workspace).as_posix() for path in test_files
    }
    covered_symbols = set()
    for test_file in test_files:
        try:
            tree = ast.parse(
                test_file.read_text(encoding="utf-8"),
                filename=str(test_file),
            )
        except SyntaxError:
            continue
        module_aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                local_path = workspace / (node.module.replace(".", "/") + ".py")
                if not local_path.is_file():
                    continue
                relative = local_path.relative_to(workspace).as_posix()
                covered_files.add(relative)
                for alias in node.names:
                    covered_symbols.add(f"{relative}:{alias.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    local_path = workspace / (
                        alias.name.replace(".", "/") + ".py"
                    )
                    if not local_path.is_file():
                        continue
                    relative = local_path.relative_to(workspace).as_posix()
                    covered_files.add(relative)
                    module_aliases[alias.asname or alias.name.split(".")[-1]] = (
                        relative
                    )
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in module_aliases
            ):
                covered_symbols.add(
                    f"{module_aliases[node.value.id]}:{node.attr}"
                )
    return {
        "mode": "targeted",
        "test_targets": list(targets),
        "covered_files": sorted(covered_files),
        "covered_symbols": sorted(covered_symbols),
    }


def apply_bounded_patch(workspace: Path, patch: str) -> dict:
    if not patch or len(patch) > MAX_PATCH_CHARS:
        raise ValueError(
            f"apply_patch requires 1-{MAX_PATCH_CHARS} characters"
        )
    paths = _patch_paths(patch)
    if not paths or len(paths) > MAX_PATCH_FILES:
        raise ValueError(
            f"apply_patch must modify 1-{MAX_PATCH_FILES} existing files"
        )
    for path in paths:
        safe_relative_path(path)
        if not (workspace / path).is_file():
            raise ValueError(
                "apply_patch cannot create or delete files in bounded mode"
            )
    before_sources = {
        path: (workspace / path).read_text(encoding="utf-8")
        for path in paths
        if Path(path).suffix == ".py"
    }
    check = subprocess.run(
        ["git", "apply", "--check", "--recount", "--whitespace=nowarn", "-"],
        cwd=workspace,
        input=patch,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if check.returncode:
        raise ValueError(check.stderr.strip() or "Patch check failed")
    applied = subprocess.run(
        ["git", "apply", "--recount", "--whitespace=nowarn", "-"],
        cwd=workspace,
        input=patch,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if applied.returncode:
        raise RuntimeError(applied.stderr.strip() or "Patch application failed")
    changed_symbols = {
        path: changed_python_symbols(
            before,
            (workspace / path).read_text(encoding="utf-8"),
        )
        for path, before in before_sources.items()
    }
    return {
        "changed_files": paths,
        "changed_symbols": changed_symbols,
        "patch_bytes": len(patch.encode("utf-8")),
    }


def run_unittest(
    workspace: Path,
    *,
    targets: list[str] | None = None,
    timeout: int = 45,
) -> dict:
    for cache_directory in workspace.rglob("__pycache__"):
        if cache_directory.is_dir():
            shutil.rmtree(cache_directory)
    normalized_targets = []
    for target in targets or []:
        if target.endswith(".py") or "/" in target:
            normalized_targets.append(safe_relative_path(target).as_posix())
        else:
            if not re.fullmatch(r"[A-Za-z0-9_.]+", target):
                raise ValueError(f"Unsafe unittest target: {target}")
            normalized_targets.append(target)
    command = [sys.executable, "-B", "-m", "unittest"]
    if normalized_targets:
        command.extend(normalized_targets)
    else:
        command.extend(["discover", "-s", "."])
    result = subprocess.run(
        command,
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = result.stdout + result.stderr
    count_match = re.search(r"Ran\s+(\d+)\s+tests?\b", output)
    test_count = int(count_match.group(1)) if count_match else 0
    success = result.returncode == 0 and test_count > 0
    return {
        "command": " ".join(command),
        "targets": normalized_targets,
        "returncode": 0 if success else (result.returncode or 1),
        "test_count": test_count,
        "output": _bounded(output),
        "truncated": len(output) > MAX_TOOL_OUTPUT_CHARS,
    }


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _bounded(value: str) -> str:
    if len(value) <= MAX_TOOL_OUTPUT_CHARS:
        return value
    return f"{value[:MAX_TOOL_OUTPUT_CHARS]}\n...[truncated]"


def _patch_paths(patch: str) -> list[str]:
    paths = []
    for match in re.finditer(r"^\+\+\+\s+(?:b/)?(.+)$", patch, re.MULTILINE):
        path = match.group(1).strip()
        if path == "/dev/null":
            raise ValueError("apply_patch cannot create or delete files")
        if path not in paths:
            paths.append(path)
    return paths


def _xml_to_dict(element: ET.Element) -> dict[str, Any]:
    return {
        "tag": element.tag,
        "attributes": dict(element.attrib),
        "text": (element.text or "").strip() or None,
        "children": [_xml_to_dict(child) for child in element],
    }


def _python_symbol_fingerprints(source: str) -> dict[str, str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"*": sha256(source.encode("utf-8")).hexdigest()}
    fingerprints = {}
    module_fragments = []
    for node in tree.body:
        fragment = ast.get_source_segment(source, node) or ast.dump(
            node,
            include_attributes=False,
        )
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            fingerprints[node.name] = sha256(
                fragment.encode("utf-8")
            ).hexdigest()
        else:
            module_fragments.append(fragment)
    fingerprints["__module__"] = sha256(
        "\n".join(module_fragments).encode("utf-8")
    ).hexdigest()
    return fingerprints
