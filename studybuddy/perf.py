"""PERF-02: SQL statement-count helper for query-budget tests.

Usage in tests:

    from studybuddy.perf import count_statements

    with app.app_context():
        with count_statements(db.engine) as n:
            client.get("/some-route")
        assert n[0] <= BUDGET, f"{n[0]} statements exceed budget {BUDGET}"

Budgets (see docs/ops/health.md and tests/test_ws6_ops.py):
- /healthz: 0 statements (liveness must never touch the DB)
- /readyz:  <= 20 statements (DB ping + alembic head check)
- /version: <= 20 statements (git SHA + schema revision lookup)
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import event


@contextmanager
def count_statements(engine):
    """Yield a mutable single-element list counting SQL statements executed.

    Counts every ``before_cursor_execute`` on the given engine inside the
    context. N+1 loops show up as large counts; use with per-flow budgets.
    """
    counter = [0]

    def _before_cursor_execute(conn, cursor, statement, parameters,
                               context, executemany):
        counter[0] += 1

    event.listen(engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before_cursor_execute)


# Statement budgets for key flows (PERF-02 acceptance criteria).
BUDGET_HEALTHZ = 0
BUDGET_READYZ = 20
BUDGET_VERSION = 20
BUDGET_MODEL_FETCH_EAGER = 5  # joinedload fetch of parent+children
