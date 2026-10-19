# ADR 0003: Schema Changes via Alembic Migrations

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Vivek Bartwal (maintainer), Meta Muse (AI agent)

## Context

Early schema evolution happened through `db.create_all()` at boot — fine for
SQLite dev, destructive-by-omission for Postgres (columns are never altered,
data migrations are impossible, and two deploys can disagree about schema).

## Decision

- **Production schema is owned by Alembic migrations** (`migrations/`),
  applied as a release step (`flask db upgrade`). DDL at worker boot is
  removed for Postgres (ARC-03).
- `db.create_all()` is kept **only** for SQLite dev/test and the TESTING
  fixture so the test suite runs without a migration pass per test
  (`SKIP_DB_INIT=1` forces the skip, e.g. when generating migrations).
- Every migration is reversible (`downgrade()`), tested on SQLite, and keeps
  a single linear head. Risky conversions (e.g. Enum rewrites) are done as
  Postgres-only follow-ups with explicit value mapping, never silently.

## Consequences

- **Good:** production schema is versioned, reviewable, and reproducible;
  data migrations (backfills, type conversions like ARC-04's
  `paper_import.fetched_at`) become possible.
- **Bad:** contributors must write migrations instead of just editing models;
  SQLite/Postgres dialect differences (batch mode, `USING` clauses) need
  care in every non-trivial migration.
- **Revisit when:** never expected — this is standard practice; revisit only
  if the project outgrows Flask-Migrate.
