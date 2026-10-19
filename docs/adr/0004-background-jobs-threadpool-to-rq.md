# ADR 0004: Background Jobs — Bounded ThreadPool Now, RQ Later

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Vivek Bartwal (maintainer), Meta Muse (AI agent)

## Context

Heavy work (PDF parsing, embeddings, LLM batches, dataset refreshes) must not
block web requests. The old pattern — spawning a daemon thread from a request
handler that rewrote `data/opportunities.json` on the ephemeral filesystem —
was broken on the free tier: lost on restart/redeploy, and rarely ran on a
spun-down instance (ARC-11).

## Decision

Two tracks:

1. **Dataset refresh moves to CI.** A scheduled GitHub Actions workflow runs
   the fetchers, validates against the data schema, link-checks, and opens a
   **pull request** with updated JSON. Data becomes versioned and reviewable;
   the request-triggered refresh thread is removed.
2. **Heavy request work runs in a bounded `ThreadPoolExecutor`** inside the
   SEC-08 sandbox for the MVP, with job status polled via `/jobs/<id>`.
   When we leave the free tier for an always-on plan, adopt a real queue
   (**RQ/Arq with Redis**).
3. **Periodic maintenance** (retention purges, expired-token cleanup) runs as
   a Render cron job or GitHub Actions hitting a protected maintenance
   endpoint/CLI — idempotent and logged.

## Consequences

- **Good:** no daemon threads from request handlers; works within free-tier
  limits; clear upgrade path that doesn't require re-architecting callers
  (the `/jobs/<id>` polling contract stays the same under RQ).
- **Bad:** ThreadPool jobs die with the worker (no durability, no retries);
  acceptable on the free tier, not on paid.
- **Revisit when:** moving to an always-on/paid tier, or the first time a
  user-visible job is lost to a worker restart — then adopt RQ + Redis.
