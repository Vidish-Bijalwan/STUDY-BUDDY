#!/usr/bin/env python3
"""PERF-09: CI memory-budget check.

Boots the real Flask app (sqlite), exercises the core request flows and the
resume-text skills pipeline on fixtures, then fails if the process peak RSS
exceeds 400 MB.

Usage:  python scripts/check_memory.py [--budget-mb 400]
Exit 0 on pass, 1 on budget breach, 2 on harness error.
"""
from __future__ import annotations

import argparse
import os
import resource
import sys
import time

BUDGET_MB = 400


def rss_mb() -> float:
    # VmHWM is THIS process image's peak RSS (per-mm, reset on exec).
    # getrusage().ru_maxrss is NOT reset on exec — a child spawned from a
    # heavy parent (e.g. pytest after thousands of tests) inherits the
    # parent's peak and the budget check measures the wrong process.
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


FIXTURE_RESUME = """
Aarav Sharma — B.Tech CSE, Graphic Era Hill University (2027)
Skills: Python, Flask, SQLAlchemy, React, Docker, Git, pandas, scikit-learn
Experience: Built a resume analyzer with RAG over 200 documents using
LangChain and FAISS; interned at a fintech startup building dashboards.
Projects: LeetCode 300+ problems; Kaggle top 10% in a tabular competition.
"""


def main() -> int:
    os.environ.setdefault("OPP_NO_AUTO_REFRESH", "1")
    # Ensure the repo root is importable when run as `python scripts/...`
    # (script dir, not cwd, lands on sys.path in that case).
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from unified_app import create_app  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        print(f"HARNESS ERROR: cannot import app: {exc}", file=sys.stderr)
        return 2

    t0 = time.time()
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "memory-budget-check",
        "WTF_CSRF_ENABLED": False,
    })
    boot_rss = rss_mb()

    client = app.test_client()
    for path in ("/healthz", "/readyz", "/version"):
        client.get(path)

    # Core workload: skills extraction over a realistic resume text.
    try:
        from studybuddy.skills_taxonomy import extract_skills_fast  # noqa: E402
        skills = extract_skills_fast(FIXTURE_RESUME)
    except Exception as exc:  # noqa: BLE001
        print(f"HARNESS ERROR: skills pipeline failed: {exc}", file=sys.stderr)
        return 2

    peak = rss_mb()
    elapsed = time.time() - t0
    print(f"boot RSS: {boot_rss:.0f} MB | peak RSS: {peak:.0f} MB "
          f"| skills found: {len(skills)} | elapsed: {elapsed:.1f}s "
          f"| budget: {BUDGET_MB} MB")
    if peak > BUDGET_MB:
        print(f"FAIL: peak RSS {peak:.0f} MB exceeds {BUDGET_MB} MB budget",
              file=sys.stderr)
        return 1
    print("PASS: memory budget OK")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI memory budget check")
    parser.add_argument("--budget-mb", type=int, default=BUDGET_MB)
    args = parser.parse_args()
    BUDGET_MB = args.budget_mb
    sys.exit(main())
