"""RAG-08: literature-review and gap-finder honesty.

``gap_finder`` and ``lit_review`` are heuristic engines (keyword
statistics, contrast markers, TF-IDF themes) — not expert analysis. This
module labels their outputs accordingly and attaches machine-readable
evidence summaries (which papers, which terms) so the UI — and the user —
can see exactly what each suggestion rests on.

Wrappers never mutate their input; they return labeled copies. They never
raise and never touch the network.

Note on the RAG-08 refactor ask: ``gap_finder.py`` and ``lit_review.py``
are owned by other workstreams, so they were deliberately NOT edited here.
The most complex function *this* workstream introduced —
:func:`studybuddy.rag_chunking.chunk_document` — was decomposed from the
start into small testable pieces (``estimate_tokens``,
``detect_heading``, ``detect_table_kind``, ``split_page_blocks``,
``split_table_rows``, ``split_long_block``, ``make_embedding_id``), each
covered by unit tests in ``tests/test_ws1_rag.py``.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Labels & disclaimers
# ---------------------------------------------------------------------------

#: The exact label RAG-08 requires on heuristic outputs.
HEURISTIC_METHOD_LABEL = "heuristic suggestions"

GAP_FINDER_DISCLAIMER = (
    "These gaps are heuristic suggestions, not expert analysis. They were "
    "found by keyword statistics and contrast-marker heuristics over your "
    "uploaded papers — they do not reflect peer review, citation impact, "
    "or knowledge of the wider field. Treat each gap as a starting "
    "hypothesis and verify it against the cited evidence before citing it."
)

LIT_REVIEW_DISCLAIMER = (
    "This review is a heuristic synthesis, not a scholarly literature "
    "review. Themes come from TF-IDF term statistics and every claim is an "
    "extracted sentence from your uploaded papers — no external sources "
    "were consulted and nothing was peer-reviewed. Verify coverage against "
    "the cited papers before relying on it."
)

_QUOTED_TERM_RE = re.compile(r"'([^']{2,60})'")


# ---------------------------------------------------------------------------
# 1. Evidence summaries
# ---------------------------------------------------------------------------

def _unique_sorted(values: list[Any]) -> list[str]:
    seen: list[str] = []
    for v in values:
        if isinstance(v, str) and v.strip() and v not in seen:
            seen.append(v)
    return sorted(seen)


def _terms_from_title(title: Any) -> list[str]:
    """Terms a gap title calls out: the quoted 'term' fragments."""
    if not isinstance(title, str):
        return []
    return _unique_sorted(_QUOTED_TERM_RE.findall(title))


def gap_evidence_summary(gap: dict | None) -> dict:
    """Which papers and which terms a single gap rests on. Never raises."""
    if not isinstance(gap, dict):
        return {"title": "", "papers": [], "terms": []}
    evidence = gap.get("evidence")
    papers = _unique_sorted([
        e.get("doc") for e in evidence if isinstance(e, dict)
    ]) if isinstance(evidence, list) else []
    return {
        "title": gap.get("title") if isinstance(gap.get("title"), str) else "",
        "type": gap.get("type"),
        "papers": papers,
        "terms": _terms_from_title(gap.get("title")),
    }


def review_evidence_summary(review: dict | None) -> dict:
    """Which papers and which terms a lit-review rests on. Never raises."""
    if not isinstance(review, dict):
        return {"papers": [], "theme_terms": [], "claims": 0}
    papers: list[str] = []
    theme_terms: list[str] = []
    for th in review.get("themes") or []:
        if not isinstance(th, dict):
            continue
        papers.extend(th.get("papers") or [])
        theme_terms.extend(th.get("terms") or [])
    for pp in review.get("per_paper") or []:
        if isinstance(pp, dict) and isinstance(pp.get("title"), str):
            papers.append(pp["title"])
    claims = review.get("claims_table")
    return {
        "papers": _unique_sorted(papers),
        "theme_terms": _unique_sorted(theme_terms),
        "claims": len(claims) if isinstance(claims, list) else 0,
    }


# ---------------------------------------------------------------------------
# 2. Labeling wrappers
# ---------------------------------------------------------------------------

def is_labeled(output: Any) -> bool:
    """True when an output already carries the heuristic-suggestions label."""
    return (
        isinstance(output, dict)
        and output.get("method") == "heuristic"
        and output.get("method_label") == HEURISTIC_METHOD_LABEL
    )


def label_gap_report(report: dict | None) -> dict:
    """Label a ``gap_finder.generate_gap_report`` dict as heuristic.

    Adds ``method``/``method_label``/``disclaimer`` and an
    ``evidence_summary`` (per gap: title, papers, terms). Error-shaped
    reports (``{"note": ...}``) are labeled too — honesty applies most
    when there is nothing to show. Never raises; bad input yields a
    labeled empty shape.
    """
    base = dict(report) if isinstance(report, dict) else {}
    gaps = base.get("gaps")
    summary = [gap_evidence_summary(g) for g in gaps] \
        if isinstance(gaps, list) else []
    labeled = dict(base)
    labeled["method"] = "heuristic"
    labeled["method_label"] = HEURISTIC_METHOD_LABEL
    labeled["disclaimer"] = GAP_FINDER_DISCLAIMER
    labeled["evidence_summary"] = summary
    return labeled


def label_lit_review(review: dict | None) -> dict:
    """Label a ``lit_review.generate_review`` dict as heuristic.

    Adds ``method``/``method_label``/``disclaimer`` and an
    ``evidence_summary`` (papers, theme terms, claim count). Error-shaped
    reviews (``{"error": ...}``) are labeled as well. Never raises.
    """
    base = dict(review) if isinstance(review, dict) else {}
    labeled = dict(base)
    labeled["method"] = "heuristic"
    labeled["method_label"] = HEURISTIC_METHOD_LABEL
    labeled["disclaimer"] = LIT_REVIEW_DISCLAIMER
    labeled["evidence_summary"] = review_evidence_summary(base)
    return labeled
