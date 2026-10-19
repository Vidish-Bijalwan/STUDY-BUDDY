"""Explainability renderer: "why this score" (UX-07).

Data model (aligned with ENG-01 readiness pillars):

    {
        "score": 78, "heuristic": True, "version": "rr-1.0",
        "pillars": [
            {"name": "Parseability", "weight": 35, "score": 30, "max": 35,
             "findings": [
                 {"rule": "contact-email", "points": 5, "max": 5,
                  "evidence_span": "vivek@example.com", "fix": "..."},
                 ...
             ]},
            ...
        ],
    }

Every deduction cites an evidence span or a missing element. The renderer
produces (a) a Jinja-friendly dict tree for server-rendered templates and
(b) standalone HTML for the expandable rule list used in report pages.
"""
from __future__ import annotations

import html
from typing import Any

#: The ENG-01 pillars with their weights (must sum to 100).
READINESS_PILLARS = (
    {"name": "Parseability", "weight": 35},
    {"name": "Role alignment", "weight": 35},
    {"name": "Impact and clarity", "weight": 30},
)

_SCORE_HEADING = "Why this score"


def validate_explanation(report: dict[str, Any]) -> list[str]:
    """Check an explanation payload; return a list of problems (empty = OK)."""
    problems: list[str] = []
    pillars = report.get("pillars")
    if not isinstance(pillars, list) or not pillars:
        return ["report.pillars must be a non-empty list"]
    weight_sum = 0
    for p in pillars:
        if not isinstance(p, dict):
            problems.append("pillar must be a dict")
            continue
        weight_sum += int(p.get("weight", 0))
        for key in ("name", "weight", "score", "max"):
            if key not in p:
                problems.append(f"pillar missing key: {key}")
        for f in p.get("findings", []):
            if not isinstance(f, dict):
                problems.append("finding must be a dict")
                continue
            for key in ("rule", "points", "fix"):
                if key not in f:
                    problems.append(f"finding missing key: {key}")
    if weight_sum != 100:
        problems.append(f"pillar weights sum to {weight_sum}, expected 100")
    return problems


def pillar_summary(pillar: dict[str, Any]) -> dict[str, Any]:
    """Compact summary: score, max, weight, deduction rules."""
    findings = pillar.get("findings", []) or []
    deductions = [f for f in findings if f.get("points", 0) < 0]
    return {
        "name": pillar.get("name", "?"),
        "score": pillar.get("score", 0),
        "max": pillar.get("max", 0),
        "weight": pillar.get("weight", 0),
        "n_findings": len(findings),
        "n_deductions": len(deductions),
        "deduction_rules": [f.get("rule") for f in deductions],
    }


def render_explanation_html(report: dict[str, Any]) -> str:
    """Render the expandable "why this score" panel as standalone HTML.

    Uses <details>/<summary> (keyboard accessible, no JS). Evidence spans are
    HTML-escaped. Never includes raw resume text beyond cited evidence spans.
    """
    out: list[str] = []
    esc = html.escape
    score = report.get("score", 0)
    version = esc(str(report.get("version", "rr-1.0")))
    out.append(
        f'<section class="sb-explain" aria-label="{esc(_SCORE_HEADING)}">'
        f'<h3>{esc(_SCORE_HEADING)} <span class="sb-badge sb-badge--rule">'
        f"Rule-based</span></h3>"
        f'<p class="sb-card__meta">Readiness score: <strong>{int(score)}/100</strong>. '
        "A transparent heuristic (version "
        f"{version}); real employer systems differ — no tool can predict their scores.</p>"
    )
    for pillar in report.get("pillars", []):
        pname = esc(str(pillar.get("name", "")))
        pscore = pillar.get("score", 0)
        pmax = pillar.get("max", 0)
        pct = int(round(100 * pscore / pmax)) if pmax else 0
        findings = pillar.get("findings", []) or []
        out.append(
            f'<details class="sb-card" style="margin-bottom: var(--sb-space-3);">'
            f"<summary><strong>{pname}</strong> — {pscore}/{pmax} "
            f'({pct}%) <span class="sb-card__meta">[{len(findings)} checks]</span></summary>'
            '<ul style="margin-top: var(--sb-space-3); padding-left: var(--sb-space-5);">'
        )
        for f in findings:
            rule = esc(str(f.get("rule", "")))
            points = f.get("points", 0)
            pmax_f = f.get("max", "")
            span = f.get("evidence_span")
            fix = esc(str(f.get("fix", "")))
            sign = "+" if points > 0 else ""
            out.append(
                f'<li style="margin-bottom: var(--sb-space-2);">'
                f"<code>{rule}</code>: <strong>{sign}{points}</strong>"
                + (f"/{pmax_f}" if pmax_f != "" else "")
            )
            if span:
                out.append(
                    f'<br /><span class="sb-card__meta">Evidence: </span>'
                    f"<mark>{esc(str(span))}</mark>"
                )
            if fix:
                out.append(f'<br /><span class="sb-card__meta">How to fix: </span>{fix}')
            out.append("</li>")
        out.append("</ul></details>")
    out.append("</section>")
    return "".join(out)


def fixture_report() -> dict[str, Any]:
    """Minimal fixture for tests / demos: a realistic mixed-quality resume."""
    return {
        "score": 64,
        "heuristic": True,
        "version": "rr-1.0",
        "pillars": [
            {
                "name": "Parseability",
                "weight": 35,
                "score": 30,
                "max": 35,
                "findings": [
                    {
                        "rule": "contact-email",
                        "points": 5,
                        "max": 5,
                        "evidence_span": "vivek@example.com",
                        "fix": "Keep a single professional email in the header.",
                    },
                    {
                        "rule": "contact-phone",
                        "points": 5,
                        "max": 5,
                        "evidence_span": "+91 98765 43210",
                        "fix": "Phone found. Prefer +91 international format.",
                    },
                    {
                        "rule": "section-headings",
                        "points": 3,
                        "max": 8,
                        "evidence_span": None,
                        "fix": "Add standard headings (Summary, Experience, "
                        "Education, Skills, Projects) — missing 'Summary'.",
                    },
                    {
                        "rule": "single-column-layout",
                        "points": -5,
                        "max": 10,
                        "evidence_span": "text-box @ x=420",
                        "fix": "Use a single-column layout; text boxes confuse parsers.",
                    },
                ],
            },
            {
                "name": "Role alignment",
                "weight": 35,
                "score": 20,
                "max": 35,
                "findings": [
                    {
                        "rule": "must-have-coverage",
                        "points": 15,
                        "max": 25,
                        "evidence_span": "Python, Flask",
                        "fix": "Mirror the JD's must-have skills in Experience, not just the skills list.",
                    },
                    {
                        "rule": "skills-list-cap",
                        "points": -10,
                        "max": 0,
                        "evidence_span": "28 uncorroborated skills listed",
                        "fix": "Skills beyond ~15 add nothing unless corroborated by experience.",
                    },
                ],
            },
            {
                "name": "Impact and clarity",
                "weight": 30,
                "score": 14,
                "max": 30,
                "findings": [
                    {
                        "rule": "action-verb-starts",
                        "points": 8,
                        "max": 12,
                        "evidence_span": "Built an API serving 2,000 req/day",
                        "fix": "Start every bullet with a strong action verb.",
                    },
                    {
                        "rule": "quantification",
                        "points": 6,
                        "max": 12,
                        "evidence_span": None,
                        "fix": "Quantify 3 more bullets (numbers, %, ₹/$ scale).",
                    },
                    {
                        "rule": "first-person-pronouns",
                        "points": -3,
                        "max": 0,
                        "evidence_span": "I led a team",
                        "fix": "Drop first-person pronouns; bullets start with verbs.",
                    },
                ],
            },
        ],
    }


__all__ = [
    "READINESS_PILLARS",
    "validate_explanation",
    "pillar_summary",
    "render_explanation_html",
    "fixture_report",
]
