"""ENG-10: Outcome feedback loop — opt-in, privacy-preserving, never causal.

Users may record per-application outcomes (applied / interview / offer /
rejected). Records are aggregated ANONYMOUSLY: published cohorts are grouped
by a coarse, non-identifying cohort label, any cohort with fewer than
``K_MIN`` (20) records is suppressed entirely (k-anonymity), and every
published aggregate carries its sample size and a confidence interval.

Aggregates are correlations only. The module's vocabulary is policed:
"associated with", "observed alongside" — never "causes", "boosts", "leads
to". There is no causal analysis anywhere in this module.

Storage is the caller's responsibility (in-memory dict in tests / a
database table in the app); this module never touches user identities in
its aggregate output.
"""

import math
from datetime import date

OUTCOME_STAGES = ("applied", "interview", "offer", "rejected")
K_MIN = 20  # minimum cohort size for k-anonymity

CORRELATION_DISCLAIMER = (
    "These are observed associations, not causal effects. Interview rates "
    "differ across cohorts for many uncontrolled reasons (market, timing, "
    "role fit, referral source). Do not treat these numbers as proof that "
    "one factor produces another."
)


class OptInRequired(PermissionError):
    """Raised when an outcome is recorded without explicit opt-in."""


def record_outcome(store, app_id, stage, *, opted_in, cohort_label=None,
                   occurred_on=None):
    """Record one application outcome. ``store`` is a caller-owned dict.

    - ``opted_in`` must be truthy or ``OptInRequired`` is raised.
    - ``stage`` must be one of ``OUTCOME_STAGES``.
    - The stored record keeps NO user id — only ``app_id`` (the caller's
      opaque key), the stage, a coarse cohort label, and the date.
    """
    if not opted_in:
        raise OptInRequired(
            "Outcome tracking is opt-in. Pass opted_in=True after the user "
            "explicitly consents; the record is stored anonymously.")
    if stage not in OUTCOME_STAGES:
        raise ValueError(f"stage must be one of {OUTCOME_STAGES}, got {stage!r}")
    if not isinstance(store, dict):
        raise TypeError("store must be a dict")
    store[str(app_id)] = {
        "app_id": str(app_id),
        "stage": stage,
        "cohort_label": str(cohort_label or "unspecified"),
        "occurred_on": occurred_on or date.today().isoformat(),
    }
    return store[str(app_id)]


def withdraw_outcome(store, app_id):
    """Delete a previously recorded outcome (right to be forgotten)."""
    return store.pop(str(app_id), None) is not None


def wilson_interval(hits, n, z=1.96):
    """Wilson score 95% confidence interval for a proportion.

    Returns (low, high) clamped to [0, 1]. ``(0.0, 0.0)`` for n == 0.
    """
    if n <= 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    low = max(0.0, (center - spread) / denom)
    high = min(1.0, (center + spread) / denom)
    return (round(low, 4), round(high, 4))


def _funnel(records):
    """Count how far each application progressed: applied -> interview -> offer."""
    n = len(records)
    interviews = sum(1 for r in records if r["stage"] in ("interview", "offer"))
    offers = sum(1 for r in records if r["stage"] == "offer")
    return n, interviews, offers


def aggregate_outcomes(store, k_min=K_MIN):
    """Aggregate outcomes into publishable, k-anonymous cohort statistics.

    Groups records by their coarse cohort label (e.g. readiness score band).
    Cohorts with fewer than ``k_min`` records are SUPPRESSED — returned in
    ``suppressed`` with their count, never published.

    Every published cohort includes sample sizes and Wilson 95% confidence
    intervals for interview and offer rates, plus the correlation disclaimer.
    No user identifiers appear anywhere in the output.
    """
    by_cohort = {}
    for rec in (store or {}).values():
        by_cohort.setdefault(rec.get("cohort_label", "unspecified"), []).append(rec)

    published, suppressed = [], []
    for cohort in sorted(by_cohort):
        records = by_cohort[cohort]
        n, interviews, offers = _funnel(records)
        if n < k_min:
            suppressed.append({"cohort": cohort, "n": n,
                               "reason": f"below k-anonymity minimum ({k_min})"})
            continue
        interview_rate = interviews / n
        offer_rate = offers / n
        published.append({
            "cohort": cohort,
            "n": n,
            "n_interviews": interviews,
            "n_offers": offers,
            "interview_rate": round(interview_rate, 4),
            "interview_rate_ci95": wilson_interval(interviews, n),
            "offer_rate": round(offer_rate, 4),
            "offer_rate_ci95": wilson_interval(offers, n),
            "reading": ("Cohorts with this label were observed alongside a "
                        f"{interview_rate:.0%} interview rate in this sample."),
        })
    return {"published": published, "suppressed": suppressed,
            "k_min": k_min, "disclaimer": CORRELATION_DISCLAIMER}


def cohort_label_for_score(score):
    """Coarse, non-identifying readiness band for a 0-100 match score."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "unspecified"
    if s >= 75:
        return "readiness 75+"
    if s >= 55:
        return "readiness 55-74"
    return "readiness <55"
