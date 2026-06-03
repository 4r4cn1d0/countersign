#!/usr/bin/env python3
"""Index repository files with special handling for .kiro specs.

Produces `index.json` at the output path (default: ./index.json).

Usage:
  python3 scripts/index_kiro.py --root . --out index.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Any


EXCLUDE_DIRS = {".git", "node_modules", "venv", "__pycache__", ".venv", "dist", "build"}


def sha1_of_file(path: Path, chunk_size: int = 8192) -> str:
    h = hashlib.sha1()
    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def read_snippet(path: Path, max_lines: int = 20) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + "\n..."


def index_repo(root: Path, out_path: Path, max_snippet: int = 20) -> Dict[str, Any]:
    entries = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs
        rel = os.path.relpath(dirpath, root)
        parts = rel.split(os.sep) if rel != "." else []
        if parts and parts[0] in EXCLUDE_DIRS:
            dirnames[:] = []
            continue
        # remove excluded children from traversal
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]

        for fname in filenames:
            try:
                fp = Path(dirpath) / fname
                relp = fp.relative_to(root).as_posix()
                stat = fp.stat()
            except Exception:
                continue

            is_kiro = ".kiro/" in relp or relp.startswith(".kiro")
            entry = {
                "path": relp,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "sha1": sha1_of_file(fp),
                "extension": fp.suffix.lower(),
                "priority": "high" if is_kiro else "normal",
            }

            # For .kiro markdown files, include the full content and a title
            if is_kiro and fp.suffix.lower() in {".md", ".markdown", ".txt"}:
                try:
                    content = fp.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    content = ""
                # extract first heading as title
                title = None
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith("#"):
                        title = line.lstrip("# ")[:200]
                        break
                entry.update({"title": title or fname, "content": content})
            else:
                entry["snippet"] = read_snippet(fp, max_lines=max_snippet)

            entries.append(entry)

    # sort: high priority first, then by mtime desc
    entries.sort(key=lambda e: (0 if e.get("priority") == "high" else 1, -e.get("mtime", 0)))

    index = {"root": str(root), "generated_by": "index_kiro.py", "entries": entries}
    try:
        out_path.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    except Exception as exc:
        print("Failed to write index:", exc)
    return index


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".", help="Repository root to index")
    p.add_argument("--out", default="index.json", help="Output JSON path")
    p.add_argument("--max-snippet-lines", type=int, default=20)
    args = p.parse_args()

    root = Path(args.root)
    out = Path(args.out)
    print(f"Indexing {root} → {out} (max snippet lines={args.max_snippet_lines})")
    idx = index_repo(root, out, max_snippet=args.max_snippet_lines)
    print(f"Indexed {len(idx['entries'])} files. Output: {out}")


if __name__ == "__main__":
    main()
