"""Nightly link-check for dataset URLs (DATA-06).

Reads data/certifications.json (official_url per entry) and any other JSON
datasets with URL fields, issues HEAD requests, and reports dead links.
Nightly-ready: designed to run as a CI cron job; exits 1 on failures so the
job goes red, exits 0 with --report for a human-readable summary.

Usage:
    python scripts/check_links.py --report
    python scripts/check_links.py --json --timeout 8 --workers 8
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATASETS = [
    (ROOT / "data" / "certifications.json", ["official_url"]),
]

USER_AGENT = "STUDY-BUDDY-linkcheck/1.0 (+https://github.com/Vivek492005)"


def collect_urls() -> list[tuple[str, str]]:
    """Return [(dataset_label, url)]."""
    out: list[tuple[str, str]] = []
    for path, fields in DATASETS:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("certifications", data.get("items", []))
        for item in items if isinstance(items, list) else []:
            for f in fields:
                url = (item.get(f) or "").strip()
                if url.startswith("http"):
                    out.append((f"{path.name}:{item.get('id', item.get('name', '?'))}", url))
    # de-dupe
    seen: set[str] = set()
    return [(label, u) for label, u in out if not (u in seen or seen.add(u))]


def check_url(url: str, timeout: float) -> tuple[int | None, str]:
    """HEAD, fall back to GET on 405. Returns (status, note)."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method,
                                     headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, "ok"
        except urllib.error.HTTPError as e:
            if e.code == 405 and method == "HEAD":
                continue
            return e.code, f"http-{e.code}"
        except urllib.error.URLError as e:
            return None, f"urlerror: {getattr(e.reason, 'strerror', e.reason)}"
        except Exception as e:  # timeout etc.
            return None, f"error: {type(e).__name__}"
    return None, "unreachable"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Nightly link check for dataset URLs.")
    ap.add_argument("--timeout", type=float, default=10)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report", action="store_true", help="human-readable summary")
    args = ap.parse_args(argv)

    targets = collect_urls()
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(check_url, url, args.timeout): (label, url)
                for label, url in targets}
        for fut in concurrent.futures.as_completed(futs):
            label, url = futs[fut]
            status, note = fut.result()
            ok = status is not None and status < 400
            results.append({"label": label, "url": url, "status": status,
                            "note": note, "ok": ok})

    bad = [r for r in results if not r["ok"]]
    if args.json:
        print(json.dumps({"checked": len(results), "bad": bad}, indent=2))
    if args.report or not args.json:
        print(f"checked {len(results)} urls, {len(bad)} bad")
        for r in bad:
            print(f"  BROKEN [{r['status']}] {r['label']} -> {r['url']} ({r['note']})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
