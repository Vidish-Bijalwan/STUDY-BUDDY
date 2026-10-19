"""Personal analytics dashboard data builders (PROD-07).

All analytics are user-owned: builders take the user's own history and return
plain dicts that the UI renders and the user can export (JSON/CSV). No
cross-user aggregation, no fingerprinting — global product metrics are
covered separately in docs/oss/metrics.md.
"""
from __future__ import annotations

from collections import Counter
from datetime import date


def readiness_over_time(score_history: list[dict]) -> list[dict]:
    """score_history: [{date: 'YYYY-MM-DD', score: int, pillar: {...}}].
    Returns sorted points with 7-day moving average."""
    pts = sorted(score_history, key=lambda p: p["date"])
    avg: list[float] = []
    for i, _ in enumerate(pts):
        window = pts[max(0, i - 6) : i + 1]
        avg.append(round(sum(q["score"] for q in window) / len(window), 1))
    return [
        {"date": p["date"], "score": p["score"], "ma7": m}
        for p, m in zip(pts, avg, strict=False)
    ]


def streak_stats(activity_dates: list[str], *, today: str | None = None) -> dict:
    """Forgiving-streak design (a strength — keep it): a streak survives one
    missed day per week. activity_dates: ISO date strings."""
    days = sorted({date.fromisoformat(d) for d in activity_dates})
    if not days:
        return {"current": 0, "best": 0, "active_days_30": 0}
    today_d = date.fromisoformat(today) if today else date.today()
    best = current = 1
    misses_used = 0
    prev = days[0]
    for d in days[1:]:
        gap = (d - prev).days
        if gap == 1:
            current += 1
        elif gap == 2 and misses_used == 0:
            misses_used = 1  # forgiven
            current += 1
        else:
            best = max(best, current)
            current, misses_used = 1, 0
        prev = d
    best = max(best, current)
    # Lapse check: streak is "alive" if last activity is today or yesterday
    # (or day-before when a forgiveness miss is available).
    last_gap = (today_d - days[-1]).days
    alive = last_gap <= 1 or (last_gap == 2 and misses_used == 0)
    recent = sum(1 for d in days if (today_d - d).days < 30)
    return {
        "current": current if alive else 0,
        "best": best,
        "active_days_30": recent,
    }


def weak_topics(attempts: list[dict], *, min_attempts: int = 3, top_n: int = 5) -> list[dict]:
    """attempts: [{topic, correct: bool}]. Topics with the lowest success rate
    and enough data, excluding perfect ones."""
    totals: Counter = Counter()
    correct: Counter = Counter()
    for a in attempts:
        t = a.get("topic") or "unknown"
        totals[t] += 1
        if a.get("correct"):
            correct[t] += 1
    scored = [
        {"topic": t, "attempts": n, "accuracy": round(correct[t] / n, 2)}
        for t, n in totals.items()
        if n >= min_attempts and correct[t] < n
    ]
    return sorted(scored, key=lambda x: (x["accuracy"], -x["attempts"]))[:top_n]


def skill_coverage_trend(snapshots: list[dict]) -> list[dict]:
    """snapshots: [{date, covered: int, total: int}]."""
    return [
        {
            "date": s["date"],
            "covered": s["covered"],
            "total": s["total"],
            "pct": round(100 * s["covered"] / s["total"], 1) if s["total"] else 0,
        }
        for s in sorted(snapshots, key=lambda x: x["date"])
    ]


def export_user_analytics(user_id: int | str, *, history: dict | None = None) -> dict:
    """One payload the user can download — everything the dashboard knows."""
    history = history or {}
    return {
        "user_id": str(user_id),
        "exported_at": date.today().isoformat(),
        "readiness_over_time": readiness_over_time(history.get("scores", [])),
        "streak": streak_stats(history.get("activity", [])),
        "weak_topics": weak_topics(history.get("attempts", [])),
        "skill_coverage": skill_coverage_trend(history.get("coverage", [])),
    }


__all__ = [
    "readiness_over_time",
    "streak_stats",
    "weak_topics",
    "skill_coverage_trend",
    "export_user_analytics",
]
