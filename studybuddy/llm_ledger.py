"""LLM-03: Budgets, quotas, and cost control for AI features.

What this module does:
    * ``LLMUsage`` model — one row per AI action (user_id, feature, provider,
      model, tokens_in/out, cost_estimate, created_at). Table is created by
      migration ``c3d4e5f6a7b8`` in production; ``db.create_all()`` covers
      SQLite dev/test once this module is imported.
    * Per-user daily quota (env ``LLM_DAILY_QUOTA``, default 20 actions/day).
    * Global monthly budget (env ``LLM_MONTHLY_BUDGET_USD``, 0 = unlimited).
      When the budget is exceeded, :func:`guard_llm_action` raises
      :class:`QuotaExceeded` so callers switch to rule-based mode
      automatically — the "auto rule-based fallback flag".
    * Budget alerts at 50/80/100% (logged once per level per month;
      per-process dedup — see ARC-14 notes in :mod:`studybuddy.arc_state`).
    * :func:`quota_status_line` — the "AI actions left today: N" UI string.

Wiring (thin hook — see module docstring of ``ai_gateway``; the gateway file
itself is intentionally NOT edited here):
    from studybuddy.llm_ledger import guard_llm_action, log_llm_action
    guard_llm_action(user_id, feature)   # raises QuotaExceeded -> rule-based UX
    ...
    log_llm_action(user_id, feature, provider=..., model=..., ...)

Cost estimates are rough list-price figures for budgeting math, NOT billing.
Free-tier provider usage costs $0 of server money; the ledger still records
it so quota math and fallback behavior stay honest.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

UTC = timezone.utc

DEFAULT_DAILY_QUOTA = 20
ENV_DAILY_QUOTA = "LLM_DAILY_QUOTA"
ENV_MONTHLY_BUDGET_USD = "LLM_MONTHLY_BUDGET_USD"

BUDGET_ALERT_LEVELS = (50, 80, 100)

# Rough per-1M-token list-price estimates (USD) used ONLY for budget math.
# Free-tier usage costs $0 — these numbers keep the monthly-budget cutoff
# meaningful if/when paid tiers are used. Update when provider pricing changes.
COST_PER_MTOK = {
    "gemini": {"in": 0.075, "out": 0.30},
    "groq": {"in": 0.05, "out": 0.08},
    "openrouter": {"in": 0.20, "out": 0.80},
    "local": {"in": 0.0, "out": 0.0},   # self-hosted Ollama: no per-token cost
    "byok": {"in": 0.0, "out": 0.0},    # user's own key: no server cost
}

# (month_key, level) pairs already alerted on, per process (ARC-14: not shared
# across workers — worst case a level logs twice, once per worker).
_alerted: set[tuple[str, int]] = set()

# Set once a missing table is lazily created (dev/test SQLite safety net).
_table_ensured = False


class QuotaExceeded(Exception):
    """Daily quota or monthly budget exhausted — caller shows rule-based UX."""


def _db():
    from unified_app import db
    return db


# The model is defined at import time against unified_app's db instance so
# db.create_all() (SQLite dev/test) and Alembic autogenerate see it. This
# module is never imported at unified_app module top level, so no cycle.
from unified_app import db as _flask_db  # noqa: E402  (lazy-cycle-safe position)


class LLMUsage(_flask_db.Model):
    """LLM-03 ledger: one row per AI action for quota + budget accounting."""

    __tablename__ = "llm_usage"

    id = _flask_db.Column(_flask_db.Integer, primary_key=True)
    user_id = _flask_db.Column(
        _flask_db.Integer, _flask_db.ForeignKey("user.id"), nullable=True, index=True)
    feature = _flask_db.Column(_flask_db.String(80), nullable=False, default="")
    provider = _flask_db.Column(_flask_db.String(32), nullable=False, default="")
    model = _flask_db.Column(_flask_db.String(128), nullable=False, default="")
    tokens_in = _flask_db.Column(_flask_db.Integer, nullable=False, default=0)
    tokens_out = _flask_db.Column(_flask_db.Integer, nullable=False, default=0)
    cost_estimate = _flask_db.Column(_flask_db.Float, nullable=False, default=0.0)
    created_at = _flask_db.Column(
        _flask_db.DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        _flask_db.Index("ix_llm_usage_user_created", "user_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def daily_quota() -> int:
    """Per-user daily AI-action quota (env LLM_DAILY_QUOTA, default 20)."""
    try:
        return max(1, int(os.getenv(ENV_DAILY_QUOTA, str(DEFAULT_DAILY_QUOTA))))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_QUOTA


def monthly_budget_usd() -> float:
    """Global monthly server budget in USD (env LLM_MONTHLY_BUDGET_USD).

    0 (default) means "no budget cap configured" — quota still applies.
    """
    try:
        return max(0.0, float(os.getenv(ENV_MONTHLY_BUDGET_USD, "0") or 0))
    except (TypeError, ValueError):
        return 0.0


def estimate_cost(provider: str, tokens_in: int, tokens_out: int) -> float:
    """USD cost estimate for a call (rough list-price math, not billing)."""
    rates = COST_PER_MTOK.get((provider or "").lower(), {"in": 0.0, "out": 0.0})
    return round(
        (max(0, tokens_in) / 1_000_000) * rates["in"]
        + (max(0, tokens_out) / 1_000_000) * rates["out"],
        6,
    )


def _estimate_tokens(char_count: int) -> int:
    """Rough token estimate from character count (~4 chars/token)."""
    return max(1, int(char_count) // 4) if char_count else 0


# ---------------------------------------------------------------------------
# Ledger writes
# ---------------------------------------------------------------------------

def _ensure_table() -> None:
    """Create llm_usage if missing (dev/test SQLite safety net; no-op in prod).

    Production schema is owned by migration c3d4e5f6a7b8. This only fires when
    this module was imported after create_all() already ran (e.g. the lazy
    ai_gateway hook on a dev SQLite DB).
    """
    global _table_ensured
    if _table_ensured:
        return
    db = _db()
    LLMUsage.__table__.create(db.engine, checkfirst=True)
    _table_ensured = True


def log_llm_action(user_id, feature, provider="", model="",
                   tokens_in=0, tokens_out=0,
                   prompt_chars=0, response_chars=0):
    """Record one AI action in the ledger. Returns the LLMUsage row.

    When token counts are unknown (the gateway doesn't parse usage from most
    providers), they are estimated from character counts (~4 chars/token);
    pass explicit counts when available.

    Anonymous/system calls (user_id None) are not metered: no-op.
    """
    if user_id is None:
        return None
    if not tokens_in and prompt_chars:
        tokens_in = _estimate_tokens(prompt_chars)
    if not tokens_out and response_chars:
        tokens_out = _estimate_tokens(response_chars)
    _ensure_table()
    db = _db()
    row = LLMUsage(
        user_id=user_id,
        feature=(feature or "")[:80],
        provider=(provider or "")[:32],
        model=(model or "")[:128],
        tokens_in=int(tokens_in or 0),
        tokens_out=int(tokens_out or 0),
        cost_estimate=estimate_cost(provider, int(tokens_in or 0),
                                   int(tokens_out or 0)),
        created_at=datetime.now(UTC),
    )
    db.session.add(row)
    db.session.commit()
    return row


# ---------------------------------------------------------------------------
# Quota reads
# ---------------------------------------------------------------------------

def _day_bounds_utc(now=None):
    now = now or datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def actions_used_today(user_id, now=None) -> int:
    """Number of ledger rows for user_id in the current UTC day."""
    if user_id is None:
        return 0
    _ensure_table()
    start, end = _day_bounds_utc(now)
    return (
        LLMUsage.query
        .filter(LLMUsage.user_id == user_id,
                LLMUsage.created_at >= start,
                LLMUsage.created_at < end)
        .count()
    )


def quota_remaining(user_id, now=None) -> int:
    """AI actions the user may still take today (>= 0)."""
    return max(0, daily_quota() - actions_used_today(user_id, now=now))


def quota_status_line(user_id, now=None) -> str:
    """UI string: 'AI actions left today: N'."""
    return f"AI actions left today: {quota_remaining(user_id, now=now)}"


# ---------------------------------------------------------------------------
# Monthly budget
# ---------------------------------------------------------------------------

def _month_bounds_utc(now=None):
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def month_spend_usd(now=None) -> float:
    """Sum of cost_estimate for the current UTC calendar month."""
    _ensure_table()
    start, end = _month_bounds_utc(now)
    total = (
        _db().session.query(_flask_db.func.sum(LLMUsage.cost_estimate))
        .filter(LLMUsage.created_at >= start, LLMUsage.created_at < end)
        .scalar()
    )
    return round(float(total or 0.0), 6)


def budget_exceeded(now=None) -> bool:
    """True when a monthly budget is configured AND spend reached it."""
    budget = monthly_budget_usd()
    return budget > 0 and month_spend_usd(now=now) >= budget


def rule_based_fallback_active(now=None) -> bool:
    """Auto rule-based fallback flag: True once the monthly budget is spent."""
    return budget_exceeded(now=now)


def budget_alert_level(now=None) -> int:
    """Highest alert threshold crossed this month: one of 0/50/80/100."""
    budget = monthly_budget_usd()
    if budget <= 0:
        return 0
    pct = (month_spend_usd(now=now) / budget) * 100
    level = 0
    for threshold in BUDGET_ALERT_LEVELS:
        if pct >= threshold:
            level = threshold
    return level


def maybe_alert_budget(now=None) -> int:
    """Log a warning the first time each 50/80/100% level is crossed.

    Returns the current alert level. Dedup is per process (see ARC-14 note).
    """
    level = budget_alert_level(now=now)
    if level:
        now = now or datetime.now(UTC)
        key = (now.strftime("%Y-%m"), level)
        if key not in _alerted:
            _alerted.add(key)
            log.warning(
                "LLM-03 budget alert: month spend $%.2f reached %d%% of $%.2f budget",
                month_spend_usd(now=now), level, monthly_budget_usd())
    return level


# ---------------------------------------------------------------------------
# Guard (the 3-line hook calls this)
# ---------------------------------------------------------------------------

def guard_llm_action(user_id, feature="generate") -> int:
    """Enforce quota + budget before an AI call. Returns actions remaining.

    Raises:
        QuotaExceeded: monthly budget spent (rule-based fallback) or the
            user's daily quota is exhausted. Callers catch this and render
            the rule-based UX with a clear banner (LLM-09).
    """
    if user_id is None:
        # Not logged in / system call: nothing to meter against; allow.
        return daily_quota()
    if rule_based_fallback_active():
        maybe_alert_budget()
        raise QuotaExceeded(
            "Monthly AI budget is exhausted — showing rule-based results "
            "until the budget resets.")
    remaining = quota_remaining(user_id)
    if remaining <= 0:
        raise QuotaExceeded(
            f"Daily AI quota exhausted ({daily_quota()} actions/day) — "
            "showing rule-based results. Quota resets at midnight UTC.")
    log.debug("llm_guard user=%s feature=%s remaining=%d",
              user_id, feature, remaining)
    return remaining
