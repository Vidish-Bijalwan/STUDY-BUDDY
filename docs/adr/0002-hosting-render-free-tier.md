# ADR 0002: Hosting on Render Free Tier

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Vivek Bartwal (maintainer), Meta Muse (AI agent)

## Context

STUDY-BUDDY needs a public deployment a student can use at zero operating
cost. Candidates were Render, Railway, and Fly.io free tiers. Constraints:
512 MB RAM, no paid add-ons, Postgres must be free, deploys from GitHub.

## Decision

Host production on **Render's free tier** (web service + free Postgres),
deployed from `main` via `render.yaml`.

## Consequences

- **Good:** $0/month; Postgres included; deploy-on-push; no credit card.
- **Bad (accepted limits):**
  - Instances **spin down** after inactivity → cold starts; background work
    cannot rely on an always-on process (see ADR 0004).
  - 512 MB RAM → no heavy ML deps in production (`torch`, `transformers`,
    `sentence-transformers` are banned from requirements; retrieval stays
    BM25/TF-IDF — see ADR 0005).
  - Ephemeral filesystem → never persist uploads/DBs/generated JSON on disk;
    user uploads go to object storage or are processed transiently.
  - Free Postgres has row/storage limits and expiry risk → keep schema lean,
    add retention purges (PRIV-01), keep backups (OPS-02).
- **Revisit when:** usage outgrows free limits, revenue starts (Paddle billing
  is the planned path), or an always-on worker becomes necessary — then move
  to a paid tier and adopt RQ/Redis (ADR 0004 already plans this).
