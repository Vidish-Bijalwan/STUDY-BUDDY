"""Radon complexity ratchet for new/changed code (ARC-10).

Fails CI only when a change makes complexity WORSE: a block that is new or
whose CC grew, and now exceeds 15. Pre-existing hotspots are grandfathered
until someone touches them.

Usage: python scripts/radon_gate.py [--all]
  --all  compare the whole studybuddy/ tree against the base ref.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

CC_LIMIT = 15
TARGET_DIR = "studybuddy"


def _sh(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, check=check)


def base_ref() -> str | None:
    """Ref to compare against (None => compare worktree vs HEAD)."""
    base = os.environ.get("GITHUB_BASE_REF")  # pull_request events
    if base:
        return f"origin/{base}"
    before = os.environ.get("GITHUB_BEFORE", "")
    if before and "0000000" not in before:
        return before
    return None


def changed_py_files(base: str | None) -> list[str]:
    if base:
        out = _sh("git", "diff", "--name-only", f"{base}...HEAD").stdout
    else:
        out = _sh("git", "diff", "--name-only", "HEAD").stdout
        untracked = _sh("git", "ls-files", "--others", "--exclude-standard").stdout
        out += "\n" + untracked
    return sorted(
        {
            f
            for f in out.splitlines()
            if f.endswith(".py") and os.path.exists(f)
        }
    )


def _radon(paths: list[str]) -> dict:
    proc = _sh(sys.executable, "-m", "radon", "cc", "--min", "B", "-j", *paths)
    if proc.returncode not in (0, 1):
        print(f"radon failed:\n{proc.stderr}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        print("Could not parse radon JSON output.", file=sys.stderr)
        sys.exit(2)


def _blocks(report: dict) -> dict[str, dict[str, int]]:
    """path -> {(classname, name): complexity}."""
    out: dict[str, dict[str, int]] = {}
    for path, blks in report.items():
        out[path] = {
            (b.get("classname") or "", b.get("name")): b.get("complexity", 0)
            for b in blks
        }
    return out


def main() -> int:
    base = None if "--all" in sys.argv else base_ref()
    files = (
        sorted(
            f
            for root, _, fs in os.walk(TARGET_DIR)
            for f in (os.path.join(root, fn) for fn in fs)
            if f.endswith(".py")
        )
        if "--all" in sys.argv
        else changed_py_files(base)
    )
    files = [f for f in files if f.startswith(TARGET_DIR + "/")]
    if not files:
        print("No Python files in scope — gate passes trivially.")
        return 0
    print(f"Scope: {len(files)} file(s); base: {base or 'HEAD (worktree diff)'}")

    head_blocks = _blocks(_radon(files))

    # Materialize base versions of the same files for comparison.
    base_blocks: dict[str, dict[str, int]] = {}
    if base:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_paths, rel = [], {}
            for f in files:
                proc = _sh("git", "show", f"{base}:{f}")
                if proc.returncode != 0:
                    continue  # new file: no base version
                tp = os.path.join(tmp, f.replace("/", "_"))
                open(tp, "w").write(proc.stdout)
                tmp_paths.append(tp)
                rel[tp] = f
            if tmp_paths:
                for tp, blks in _blocks(_radon(tmp_paths)).items():
                    base_blocks[rel[tp]] = blks
    else:
        for f in files:
            proc = _sh("git", "show", f"HEAD:{f}")
            if proc.returncode == 0:
                with tempfile.NamedTemporaryFile(
                    "w", suffix=".py", delete=False
                ) as tf:
                    tf.write(proc.stdout)
                    name = tf.name
                for _tp, blks in _blocks(_radon([name])).items():
                    base_blocks[f] = blks
                os.unlink(name)

    violations = []
    for path, blocks in head_blocks.items():
        old = base_blocks.get(path, {})
        for key, cc in blocks.items():
            if cc <= CC_LIMIT:
                continue
            prev = old.get(key)
            if prev is None or cc > prev:
                kind = "new" if prev is None else f"CC {prev} -> {cc}"
                cls, name = key
                violations.append(
                    f"{path}: {(cls + '.') if cls else ''}{name} "
                    f"exceeds CC {CC_LIMIT} ({kind})"
                )
    if violations:
        print(f"COMPLEXITY RATCHET FAILED — {len(violations)} block(s):")
        for v in violations:
            print("  " + v)
        print("\nSplit the flagged function into smaller pure helpers (ARC-10).")
        return 1
    print(f"Complexity ratchet passed (no new/worsened block above CC {CC_LIMIT}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
