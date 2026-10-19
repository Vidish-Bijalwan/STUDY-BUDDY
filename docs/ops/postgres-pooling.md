# PERF-08: Postgres connection pooling for serverless DBs

Neon free **scales to zero** after 5 min idle; the first query after resume
wakes it in <1 s but any pooled connection held across the sleep is **dead**.
Supabase free pauses after 1 week. Pool settings must assume connections die.

## Recommended engine options

```python
engine_options = {
    "pool_pre_ping": True,    # validate a connection before use; dead ones are
                              # transparently replaced (the single most important flag)
    "pool_recycle": 300,      # recycle connections every 5 min — never hold one
                              # across Neon's scale-to-zero window
    "pool_size": 3,           # small: 1 gthread worker × 4 threads + headroom
    "max_overflow": 5,        # burst allowance; total ceiling = 8 connections
    "pool_timeout": 30,        # fail fast instead of queueing forever
    "connect_args": {"connect_timeout": 10, "options": "-c statement_timeout=30000"},
}
```

Why these numbers: the app runs **one gunicorn worker with 4 threads**
(OPS-09) — `pool_size=3` covers steady state, `max_overflow=5` covers bursts,
and the hard ceiling of 8 stays far under Neon's free connection limits.

## Cold-resume retry

Even with `pool_pre_ping`, the *first* query after a Neon wake can race the
resume. Wrap DB access at request scope with **one** retry on
`sqlalchemy.exc.OperationalError`:

```python
from sqlalchemy.exc import OperationalError

def with_resume_retry(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except OperationalError:
        db.session.rollback()
        return fn(*args, **kwargs)  # single retry, then let it raise
```

## Wiring (REPORTED — needs app config edit)

In `create_app`, merge `engine_options` into `SQLALCHEMY_ENGINE_OPTIONS`.
Do not set `poolclass=NullPool` — it re-opens a TCP+TLS connection per
request and makes cold starts worse.

## Monitoring

Alert when `pool.checkedin` stays at max (pool exhaustion) or when
`OperationalError` retries exceed ~1% of requests — both signal the pool is
too small for the traffic, i.e. time for Stage B.
