# Taxonomy and roadmap content governance (DATA-08)

Covers `data/skills_db.csv` (skills taxonomy), `data/learning_roadmaps.json`
(24 skills × 12 roles), and `data/certifications.json` guides.

## Review process

1. **Proposal**: open an issue or PR touching `data/taxonomy/` with a
   `taxonomy` label. Describe what changed and why (new skill, renamed alias,
   updated roadmap resource).
2. **Evidence**: roadmap resources must cite authoritative sources (official
   docs, open courses) with license notes. No paywalled-only resources as the
   *sole* reference for a stage.
3. **Reviewer**: at least one domain-knowledgeable reviewer (maintainer or a
   contributor with prior data PRs merged). Data PRs need no Python knowledge.
4. **CI gates**: `scripts/validate_data.py` schema checks, duplicate-id
   checks, and the changelog check below.
5. **Merge + stamp**: on merge, set `last_reviewed` (YYYY-MM-DD) on every
   touched record and append a row to the changelog.

## `last_reviewed` semantics

- Per-record field on taxonomy entries, roadmap stages, and cert guides.
- SLA: **365 days**. Records older than that are listed by a CI job as
  "review due" (warning, not failure) — see the freshness dashboard note in
  CONTRIBUTING-DATA.md.

## Changelog

`data/taxonomy/CHANGELOG.md` — one line per change:

```text
2026-10-19  added skill alias: 'gh actions' -> 'github-actions'  (@vivek, PR #123)
2026-10-18  roadmap 'backend-dev' stage 3: replaced dead link with official FastAPI docs
```

CI fails a taxonomy PR that changes data files without a CHANGELOG entry
(the check diffs `data/taxonomy/**` against the PR's changed files).

## Why this exists

Benchmark changes (ENG-09) must be explainable: if the readiness score's
skill matching changes because the taxonomy changed, the changelog is the
audit trail. "Our score went up because we added 40 aliases on 2026-10-19"
is a feature, not a mystery.
