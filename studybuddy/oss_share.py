"""Privacy-safe shareable score cards (OSS-09).

Cards contain ONLY pillar scores — never resume text, names, or contact
fields. Generation is opt-in (the caller passes an explicit consent flag).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


def build_score_card(
    report: dict,
    *,
    opt_in: bool,
    project_name: str = "STUDY-BUDDY",
    project_url: str = "https://github.com/Vivek492005",
) -> dict:
    """Build a privacy-safe score-card payload.

    Raises PermissionError when opt_in is False. The payload includes pillar
    name/score/max only; findings and evidence spans are deliberately
    excluded.
    """
    if not opt_in:
        raise PermissionError("score-card sharing requires explicit opt-in")
    pillars = [
        {
            "name": p.get("name", ""),
            "score": p.get("score", 0),
            "max": p.get("max", 0),
        }
        for p in report.get("pillars", [])
    ]
    card = {
        "project": project_name,
        "project_url": project_url,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "score": report.get("score", 0),
        "version": report.get("version", "rr-1.0"),
        "pillars": pillars,
        "label": "A transparent heuristic — real employer systems differ.",
    }
    return card


def assert_no_pii(card: dict, report: dict) -> list[str]:
    """Test helper: scan the card for any finding text/evidence from report."""
    blob = json.dumps(card).lower()
    leaks: list[str] = []
    for p in report.get("pillars", []):
        for f in p.get("findings", []):
            for key in ("evidence_span", "fix", "rule"):
                val = f.get(key)
                if val and len(str(val)) > 6 and str(val).lower() in blob:
                    leaks.append(f"{key}: {val!r}")
    return leaks


def card_fingerprint(card: dict) -> str:
    return hashlib.sha256(
        json.dumps(card, sort_keys=True).encode()
    ).hexdigest()[:16]


__all__ = ["build_score_card", "assert_no_pii", "card_fingerprint"]
