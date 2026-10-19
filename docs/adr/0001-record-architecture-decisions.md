# ADR 0001: Record Architecture Decisions

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Vivek Bartwal (maintainer), Meta Muse (AI agent)

## Context

STUDY-BUDDY grew from a student project into a large Flask monolith (800+
routes, 50+ models). Decisions about hosting, migrations, background jobs,
retrieval, privacy, and SSRF were made across many sessions and lived only in
chat history. New contributors (and future agent sessions) could not tell
*why* something was built a certain way, so the same debates recurred.

## Decision

We record significant architecture decisions as ADRs in `docs/adr/`,
one file per decision, numbered sequentially (`NNNN-short-slug.md`).
Each ADR uses the same shape:

- **Status** (Proposed / Accepted / Deprecated / Superseded)
- **Date**, **Deciders**
- **Context** — what forced the decision
- **Decision** — what we chose
- **Consequences** — what we gain, what we give up, what to revisit

Small, reversible choices don't need an ADR. Anything that constrains future
work (hosting, data storage, privacy posture, external dependencies) does.

## Consequences

- **Good:** rationale survives beyond chat history; reviewers can challenge
  the *reasoning*, not just the code; onboarding is faster.
- **Bad:** writing ADRs costs time; stale ADRs mislead — each ADR names its
  revisit trigger, and superseding (not editing history) is the norm.
- **Revisit when:** a decision's stated assumptions break (e.g. leaving the
  free tier invalidates several ADRs at once).
